from __future__ import annotations

import hmac
import json
import logging
import os
import queue
import re
import secrets
import socket
import threading
import time
import uuid
import webbrowser
from enum import Enum
from urllib.parse import urlsplit, urlunsplit, urlencode

from PySide6.QtCore import QObject, QTimer, Signal

from .config import DATA, atomic_json
from .transport import encode, read_message, protect


def conversation_url(url):
    try:
        parsed = urlsplit(url.strip())
        if parsed.scheme != 'https' or parsed.netloc != 'chatgpt.com': return ''
        if not re.fullmatch(r'/(?:g/[A-Za-z0-9_-]+/)?c/[A-Za-z0-9_-]+/?', parsed.path): return ''
        return urlunsplit(('https','chatgpt.com',parsed.path.rstrip('/'),'',''))
    except (ValueError, AttributeError): return ''


class ChatState(str, Enum):
    DISCONNECTED = '未连接'
    IDLE = '待机'
    SENDING = '发送中'
    GENERATING = '生成中'
    COMPLETED = '已完成'
    FAILED = '失败'


class ConversationBridge(QObject):
    state_changed = Signal(str, str)
    history = Signal(list)
    reply = Signal(str, str, bool)
    request_observed = Signal(str, str)

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.state = ChatState.DISCONNECTED
        self.detail = '主人可以先打开原会话。'

    def set_state(self, state, detail=''):
        self.state, self.detail = state, detail
        try:
            atomic_json(DATA/'chat-status.json',dict(state=state.value,detail=detail,
                target=self.config['chat_target'],ready=bool(getattr(self,'ready',False)),updated=time.time()))
        except OSError:logging.exception('Chat status write failed')
        self.state_changed.emit(state.value, detail)

    def open_conversation(self):
        if self.config['chat_target']=='desktop':
            return DesktopChatGPTLauncher.open()
        url = conversation_url(self.config['conversation_url'])
        if not url:
            self.set_state(ChatState.DISCONNECTED, '请先在设置里选定原会话。')
            return False
        return webbrowser.open(url)

    def send(self, text): raise NotImplementedError


class OfficialIntegration:
    """No unsupported API claims: only a capability record and official links."""
    supported = False
    reason = ('桌面 Chat 中的霜璃 MCP App 通过 ui/message 发送，GPT 用 publish_reply 回传真实回答。插件需在这条聊天里打开。')
    docs = ['https://learn.chatgpt.com/docs/app/commands',
            'https://developers.openai.com/plugins/build/extensions',
            'https://learn.chatgpt.com/docs/windows/windows-app']


class DesktopChatGPTLauncher:
    """OS protocol activation, using the installed app's verified Chat mode.

    codex://new?mode=chat is accepted by bootstrap's newThread parser in
    OpenAI.Codex 26.930.2377.0. It prefills, but does not submit, a Chat draft.
    codex://launch resumes the current desktop surface. Neither returns replies.
    """
    @staticmethod
    def open(text='',new=False):
        url='codex://launch'
        if new:
            query={'mode':'chat'}
            # Long messages use the clipboard instead of exceeding URI limits.
            if text and len(urlencode({'prompt':text}))<1500:query['prompt']=text
            url='codex://new?'+urlencode(query)
        try:
            if os.name=='nt':os.startfile(url)
            else:return False
            return True
        except OSError:
            logging.exception('ChatGPT desktop activation failed')
            return False


class ChatGPTLauncher(ConversationBridge):
    def send(self, text):
        self.set_state(ChatState.DISCONNECTED, '当前是原会话入口；主人可复制草稿，在原会话中发送。')
        self.open_conversation()
        return False


class AuthorizedWebBridge(ConversationBridge):
    """Authenticated native transport for desktop MCP App or optional DOM host."""
    def __init__(self, config):
        super().__init__(config)
        self.events = queue.Queue(maxsize=128)
        self.listener = None
        self.client = None
        self.lock = threading.Lock()
        self.key = ''
        self.generation = 0
        self.ready = False
        self.desktop = False
        self.desktop_binding = ''
        self.origin = ''
        self.pending = None
        self.last_seen = 0
        self.uncertain = False
        self.timer = QTimer(self); self.timer.timeout.connect(self.poll); self.timer.start(100)

    def start(self):
        self.stop()
        self.uncertain = False
        self.desktop=self.config['chat_target']=='desktop'
        self.desktop_binding=''
        if not self.desktop and not self.config['bridge_enabled']:
            detail='GPT 桌面入口 · 草稿待发送' if self.config['chat_target']=='desktop' else '原会话入口 · 网页桥接未启用'
            self.set_state(ChatState.DISCONNECTED, detail)
            return
        if not self.desktop and not re.fullmatch('[a-p]{32}',self.config['extension_id']):
            self.set_state(ChatState.DISCONNECTED, '主人还未登记浏览器扩展。')
            return
        self.generation += 1
        generation = self.generation
        self.key = secrets.token_urlsafe(48)
        self.origin='shuangli-desktop-plugin' if self.desktop else f'chrome-extension://{self.config["extension_id"]}/'
        listener = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        listener.bind(('127.0.0.1',0)); listener.listen(2); listener.settimeout(1)
        self.listener = listener
        atomic_json(DATA/'bridge-session.json',dict(port=listener.getsockname()[1],
                    pairing_key=protect(self.key), origin=self.origin))
        threading.Thread(target=self.accept, args=(listener,generation), daemon=True).start()
        self.set_state(ChatState.DISCONNECTED,'等待 GPT 桌面聊天打开霜璃插件' if self.desktop else '等待主人在 ChatGPT 页面点“绑定此会话”。')

    def put_event(self, value):
        try: self.events.put_nowait(value)
        except queue.Full: pass

    def accept(self, listener, generation):
        while generation == self.generation:
            try: client, address = listener.accept()
            except socket.timeout: continue
            except OSError: return
            if address[0] != '127.0.0.1': client.close(); continue
            threading.Thread(target=self.session,args=(client,generation),daemon=True).start()

    def session(self, client, generation):
        try:
            client.settimeout(4)
            with client.makefile('rb') as stream:
                hello = read_message(stream)
                origin = self.origin
                if hello.get('type') != 'hello' or not hmac.compare_digest(str(hello.get('key','')),self.key) or hello.get('origin') != origin:
                    return
                with self.lock:
                    if generation != self.generation or self.client is not None: return
                    self.client = client
                client.settimeout(35)
                client.sendall(encode(dict(type='target',url=self.desktop_binding if self.desktop else conversation_url(self.config['conversation_url']))))
                while generation == self.generation:
                    event = read_message(stream)
                    if event.get('type') in ('heartbeat','snapshot','status','reply','sent','error','bound','unbind'):
                        event['_generation'] = generation
                        self.put_event(event)
        except (OSError,ValueError,EOFError): pass
        finally:
            with self.lock:
                was_active = self.client is client
                if was_active: self.client = None
            client.close()
            if was_active: self.put_event(dict(type='disconnect',_generation=generation))

    def command(self, value):
        with self.lock:
            if not self.client: return False
            try: self.client.sendall(encode(value)); return True
            except OSError: return False

    def send(self, text, new=False):
        text = text.strip()
        if not text or len(text)>20000: return False
        if not self.ready or self.pending or self.uncertain or self.state == ChatState.GENERATING:
            self.set_state(ChatState.FAILED,'连接未准备好，或上一条发送结果需要主人回原页面确认。')
            return False
        request = uuid.uuid4().hex
        self.pending = dict(id=request,text=text,start=time.monotonic(),observed=False)
        if not self.command(dict(type='send',id=request,text=text,new=new,url=self.desktop_binding if self.desktop else conversation_url(self.config['conversation_url']))):
            self.pending = None; self.ready=False
            self.set_state(ChatState.DISCONNECTED,'网页连接已断开；草稿保留在这里。')
            return False
        self.set_state(ChatState.SENDING,'等待原页面确认消息。')
        return True

    def poll(self):
        now = time.monotonic()
        for _ in range(32):
            try: event = self.events.get_nowait()
            except queue.Empty: break
            if event.get('_generation') != self.generation: continue
            kind = event['type']
            if kind == 'disconnect':
                self.ready = False
                if self.pending: self.uncertain=True
                self.pending = None
                self.set_state(ChatState.DISCONNECTED,'网页连接已断开，请回原会话确认最后一条消息。')
                continue
            if kind == 'heartbeat':
                self.last_seen = now
                continue
            raw=event.get('url','')
            url = raw if self.desktop and isinstance(raw,str) and re.fullmatch(r'desktop://[0-9a-f]{32}',raw) else conversation_url(raw)
            target = self.desktop_binding if self.desktop else conversation_url(self.config['conversation_url'])
            if kind == 'bound' and url:
                # Binding occurs only after the user clicks in the extension popup.
                if self.pending:
                    self.set_state(ChatState.FAILED,'请先在原页面确认当前发送，再切换会话。'); continue
                if self.desktop:self.desktop_binding=url
                else:self.config['conversation_url']=url; self.config.save()
                self.uncertain=False
                self.command(dict(type='target',url=url))
                target = url
            if not url or url != target: continue
            self.last_seen = now
            if kind == 'unbind':
                self.ready=False
                self.set_state(ChatState.DISCONNECTED,'主人已取消这页的授权。')
            elif kind == 'snapshot':
                messages=[]
                for m in event.get('messages',[])[:40]:
                    if isinstance(m,dict) and m.get('role') in ('user','assistant') and isinstance(m.get('text'),str):
                        messages.append(dict(role=m['role'],text=m['text'][:100000],id=str(m.get('id',''))[:100]))
                self.history.emit(messages)
            elif kind == 'status':
                self.ready = bool(event.get('compatible'))
                observed = event.get('state')
                if not self.ready:
                    self.set_state(ChatState.FAILED,'原页面控件不兼容，请打开完整会话继续。')
                elif observed == 'generating': self.set_state(ChatState.GENERATING,'原页面正在生成回复。')
                elif observed == 'idle' and not self.pending:
                    self.set_state(ChatState.IDLE,'已连接 GPT 桌面聊天 · MCP App' if self.desktop else '已连接主人授权的原会话 · 非官方网页桥接')
            elif kind == 'sent' and self.pending and event.get('id') == self.pending['id']:
                self.pending['observed']=True
                self.request_observed.emit(self.pending['id'], self.pending['text'])
            elif kind == 'reply':
                ident = str(event.get('id',''))[:100]; text=event.get('text','')
                if not isinstance(text,str): continue
                done = event.get('done') is True
                self.reply.emit(ident,text[:100000],done)
                if done:
                    self.pending=None; self.uncertain=False
                    self.set_state(ChatState.COMPLETED,'原页面已显示完成的回复。')
            elif kind == 'error':
                uncertain=event.get('uncertain') is True
                self.uncertain |= uncertain
                self.pending=None
                self.set_state(ChatState.FAILED,str(event.get('message','网页操作失败。'))[:250])
        if self.ready and self.last_seen and now-self.last_seen>30:
            self.ready=False
            self.set_state(ChatState.DISCONNECTED,'原页面暂时没有回应；请打开会话检查。')
        if self.pending and now-self.pending['start']>120 and not self.pending['observed']:
            self.pending=None; self.uncertain=True
            self.set_state(ChatState.FAILED,'发送结果未确认；请检查原会话，不会自动重发。')
        elif self.desktop and self.pending and self.pending['observed'] and now-self.pending['start']>300:
            self.pending=None;self.uncertain=True
            self.set_state(ChatState.FAILED,'GPT 尚未回传回答，请在桌面聊天确认这条消息。')

    def resolve_uncertain(self):
        self.uncertain=False; self.pending=None
        self.set_state(ChatState.IDLE if self.ready else ChatState.DISCONNECTED,
                       '主人已检查原页面，下一条会使用新的发送编号。')

    def stop(self):
        self.generation+=1
        with self.lock:
            if self.client:
                try: self.client.shutdown(socket.SHUT_RDWR)
                except OSError: pass
                self.client.close(); self.client=None
        if self.listener: self.listener.close(); self.listener=None
        self.ready=False
        if self.pending: self.uncertain=True
        self.pending=None
        try: (DATA/'bridge-session.json').unlink(missing_ok=True)
        except OSError: pass
