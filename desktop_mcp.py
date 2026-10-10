"""Dependency-free local MCP server; official UI messages are sent by the host."""
from __future__ import annotations
import json
import socket
import sys
import threading
import uuid
from pathlib import Path

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))
from shuangli.transport import encode,read_message,unprotect

URI='ui://shuangli/desktop-chat.html'

def tool(name,description,properties=None,required=None,ui=None):
    result=dict(name=name,description=description,inputSchema=dict(type='object',properties=properties or {},additionalProperties=False))
    if required:result['inputSchema']['required']=required
    if ui:result['_meta']={'ui':ui}
    return result

TOOLS=[
    tool('open_shuangli','Open Shuangli desktop companion panel in THIS ChatGPT conversation. Use Chat mode, keeping the current account/personality/memory. Once the panel sends a user request with a Shuangli request ID, answer that request normally, then call publish_reply with the same ID and the actual reply text. Do not adopt or invent another persona.',ui={'resourceUri':URI,'visibility':['model','app']}),
    tool('poll_desktop','Receive a pending desktop user message and report the UI transport state.',
         {'binding':{'type':'string'},'event':{'type':'string'},'id':{'type':'string'},'message':{'type':'string'}},['binding'],{'visibility':['app']}),
    tool('publish_reply','Deliver your actual answer to the desktop after a Shuangli request. The request ID must match the pending message; keep your normal personality and conversation context. This publishes the reply, not a separate model generation.',
         {'id':{'type':'string'},'text':{'type':'string'},'done':{'type':'boolean','default':True}},['id','text'])
]

class Relay:
    def __init__(self):
        self.client=None;self.binding='';self.pending=None;self.dispatched=False
        self.lock=threading.RLock();self.closed=False

    def connect(self):
        if self.client:return
        candidates=[ROOT/'dist/ShuangliCompanion/data/bridge-session.json',ROOT/'data/bridge-session.json']
        for file in candidates:
            if not file.exists():continue
            session=json.loads(file.read_text(encoding='utf-8'))
            if session.get('origin')!='shuangli-desktop-plugin':continue
            port=int(session['port'])
            if not 1024<=port<=65535:continue
            client=socket.create_connection(('127.0.0.1',port),timeout=3)
            client.settimeout(None)
            client.sendall(encode(dict(type='hello',origin=session['origin'],key=unprotect(session['pairing_key']))))
            self.client=client
            threading.Thread(target=self.receive,args=(client,),daemon=True).start()
            return
        raise ValueError('霜璃桌宠尚未启动，或聊天入口未选桌面端。')

    def receive(self,client):
        try:
            with client.makefile('rb') as stream:
                while not self.closed:
                    message=read_message(stream)
                    with self.lock:
                        if self.client is not client:return
                        if message.get('type')=='send':
                            self.pending=message;self.dispatched=False
        except (OSError,ValueError,EOFError):pass
        finally:
            with self.lock:
                if self.client is client:self.client=None
            client.close()

    def emit(self,kind,**values):
        self.connect()
        self.client.sendall(encode(dict(type=kind,url='desktop://'+self.binding,**values)))

    def call(self,name,args):
        with self.lock:
            if name=='open_shuangli':
                if self.pending:raise ValueError('请先完成桌宠当前这条消息。')
                self.binding=uuid.uuid4().hex
                return {'binding':self.binding,'connected':False,'instruction':'Open this panel in ChatGPT Chat. Real connection begins after UI capability negotiation.'}
            if name=='poll_desktop':
                if not self.binding or args['binding']!=self.binding:raise ValueError('This panel is no longer bound.')
                self.connect()
                event=args.get('event','')
                if event=='ready':
                    self.emit('bound');self.emit('status',state='idle',compatible=True)
                elif event in ('sent','error'):
                    if not self.pending or args.get('id')!=self.pending['id']:raise ValueError('Request ID does not match.')
                    if event=='sent':
                        self.emit('sent',id=self.pending['id']);self.emit('status',state='generating',compatible=True)
                    else:
                        self.emit('error',message=args.get('message','MCP App send failed'),uncertain=True)
                        self.pending=None
                self.emit('heartbeat')
                if not event and self.pending and not self.dispatched:
                    self.dispatched=True
                    return {'request':self.pending}
                return {'request':None}
            if name=='publish_reply':
                if not self.pending or args['id']!=self.pending['id']:raise ValueError('No matching desktop request is pending.')
                text=args['text']
                if not isinstance(text,str) or not text.strip() or len(text)>100000:raise ValueError('Invalid reply text.')
                done=args.get('done',True) is True
                self.emit('reply',id='reply-'+args['id'],text=text,done=done)
                if done:self.pending=None
                return {'delivered':True,'done':done}
            raise ValueError('Unknown tool')

def main():
    relay=Relay()
    for raw in sys.stdin.buffer:
        request=None
        try:
            request=json.loads(raw)
            if 'id' not in request:continue
            method=request['method'];params=request.get('params',{})
            if method=='initialize':
                result=dict(protocolVersion='2025-11-25',serverInfo=dict(name='shuangli-desktop',version='1.0.0'),capabilities={'tools':{},'resources':{},'experimental':{'io.modelcontextprotocol/ui':{'mimeTypes':['text/html;profile=mcp-app']}}})
            elif method=='ping':result={}
            elif method=='tools/list':result={'tools':TOOLS}
            elif method=='resources/list':result={'resources':[dict(uri=URI,name='霜璃桌宠',mimeType='text/html;profile=mcp-app')]}
            elif method=='resources/read':
                if params['uri']!=URI:raise ValueError('Unknown resource')
                result={'contents':[dict(uri=URI,mimeType='text/html;profile=mcp-app',text=(ROOT/'plugins/shuangli-desktop/panel.html').read_text(encoding='utf-8'),_meta={'ui':{'prefersBorder':True,'csp':{'connectDomains':[],'resourceDomains':[]}}})]}
            elif method=='tools/call':
                try:
                    value=relay.call(params['name'],params.get('arguments',{}))
                    result={'content':[{'type':'text','text':json.dumps(value,ensure_ascii=False)}],'structuredContent':value}
                except (ValueError,OSError,KeyError) as error:
                    result={'isError':True,'content':[{'type':'text','text':str(error)}]}
            else:
                response={'jsonrpc':'2.0','id':request['id'],'error':{'code':-32601,'message':'Method not found'}}
                sys.stdout.buffer.write((json.dumps(response)+'\n').encode());sys.stdout.buffer.flush();continue
            response={'jsonrpc':'2.0','id':request['id'],'result':result}
        except (ValueError,KeyError,TypeError) as error:
            response={'jsonrpc':'2.0','id':request.get('id') if isinstance(request,dict) else None,'error':{'code':-32602,'message':str(error)}}
        sys.stdout.buffer.write((json.dumps(response,ensure_ascii=False)+'\n').encode('utf-8'));sys.stdout.buffer.flush()
    relay.closed=True
    if relay.client:relay.client.close()

if __name__=='__main__':main()
