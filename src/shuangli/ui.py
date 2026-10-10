from __future__ import annotations

import html
import json
import sys
import time
import webbrowser
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl, Signal, QRect
from PySide6.QtGui import QColor, QPainter, QPainterPath, QFont, QDesktopServices, QTextDocument, QCursor
from PySide6.QtWidgets import (QApplication,QWidget,QDialog,QVBoxLayout,QHBoxLayout,QLabel,
    QPushButton,QTextBrowser,QPlainTextEdit,QTabWidget,QFormLayout,QCheckBox,QComboBox,
    QDoubleSpinBox,QSpinBox,QLineEdit,QFileDialog,QMessageBox,QListWidget,QListWidgetItem,
    QGroupBox,QScrollArea,QFrame)

from .config import ROOT,HOME,DATA
from .bridge import ChatState,OfficialIntegration,conversation_url,DesktopChatGPTLauncher
from .installation import install_host,uninstall_host
from .platform_win import startup
from .plugins import import_pack

STYLE = '''
QWidget { color:#574866; font: 10pt "Microsoft YaHei UI"; }
QDialog { background:#f8f5ff; }
QLabel#title {font-size:17pt; font-weight:600; color:#7d60a8;}
QLabel#subtitle {color:#9885ab; font-size:9pt;}
QPushButton {background:#efe8f8; border:1px solid #e0d4ef; border-radius:10px; padding:8px 16px;}
QPushButton:hover {background:#e5d8f6; border-color:#b89bd7;}
QPushButton:disabled {color:#b4a8c1; background:#f2edf8;}
QPushButton#primary {background:#9875c8; color:white; border-color:#9875c8;}
QPushButton#primary:hover {background:#8764b9;}
QPlainTextEdit,QTextBrowser,QLineEdit,QListWidget {background:#ffffff; border:1px solid #e4daee; border-radius:12px; padding:10px; selection-background-color:#d6c1ed;}
QComboBox,QSpinBox,QDoubleSpinBox {background:#fff; border:1px solid #e4daee; border-radius:7px; padding:7px; min-height:22px;}
QComboBox::drop-down {border:0; width:24px;}
QTabWidget::pane {border:1px solid #e4daee; border-radius:12px; background:#fff;}
QTabBar::tab {background:#efe9f8; padding:10px 12px; margin:2px; border-radius:8px;}
QTabBar::tab:selected {background:#dac8ef; color:#654684;}
QCheckBox {spacing:9px; padding:4px;}
QCheckBox::indicator {width:17px; height:17px; border:1px solid #bba5d2; border-radius:5px; background:#fff;}
QCheckBox::indicator:checked {background:#a581d0;}
QScrollBar:vertical {width:8px; background:transparent; margin:8px 0;}
QScrollBar::handle:vertical {background:#d5c4e8; border-radius:4px; min-height:28px;}
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical {height:0;}
QGroupBox {border:1px solid #e5daef; border-radius:10px; margin-top:16px; padding:12px;}
QGroupBox::title {subcontrol-origin:margin; left:12px; color:#9272b5;}
QToolTip {background:#f7f1ff;color:#715590;border:1px solid #dbc7ed;padding:6px;}
'''


def open_desktop_plugin():
    import os
    from urllib.parse import quote
    marketplace=ROOT/'.agents/plugins/marketplace.json'
    os.startfile('codex://plugins/shuangli-desktop?marketplacePath='+quote(str(marketplace),safe=''))


class SafeBrowser(QTextBrowser):
    def loadResource(self, resource_type, name):
        # Chat Markdown must never fetch remote images or read file:// links.
        return None


class ChatInput(QLineEdit):
    submitted=Signal()
    def __init__(self):
        super().__init__()
        self.returnPressed.connect(self.submitted.emit)

    def toPlainText(self):
        return self.text()


class ChatPanel(QDialog):
    def __init__(self,bridge,settings_callback):
        super().__init__(None,Qt.WindowType.Tool|Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.bridge=bridge
        self.setWindowTitle('霜璃 · 主人的原会话')
        self.setFixedSize(320,54)
        self.setStyleSheet(STYLE)
        self.pet=None;self.leave_since=None;self.lift=0;self.anchor=None;self.attached=None;self.hover_origin=None
        self.answers=ReplyBubble()
        self.messages=[]
        self.pending_text=''
        self.last_render=0
        layout=QHBoxLayout(self);layout.setContentsMargins(8,6,8,6);layout.setSpacing(5)
        self.status=QLabel('·');self.status.setFixedWidth(12);layout.addWidget(self.status)
        self.input=ChatInput();self.input.setPlaceholderText('主人，霜璃在听……')
        self.input.submitted.connect(self.send);layout.addWidget(self.input,1)
        self.send_button=QPushButton('↑');self.send_button.setObjectName('primary');self.send_button.setFixedWidth(36)
        self.send_button.setToolTip('发送 · Enter');self.send_button.clicked.connect(self.send);layout.addWidget(self.send_button)
        self.input.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        def input_menu(point):
            menu=self.input.createStandardContextMenu();menu.addSeparator()
            menu.addAction('打开 GPT',bridge.open_conversation)
            menu.addAction('连接桌宠插件',self.open_plugin)
            menu.addAction('新聊天',self.new_desktop_chat)
            if bridge.uncertain:menu.addAction('已确认原聊天，解除锁定',bridge.resolve_uncertain)
            menu.addAction('设置',settings_callback);menu.exec(self.input.mapToGlobal(point))
        self.input.customContextMenuRequested.connect(input_menu)
        bridge.state_changed.connect(self.state_changed)
        bridge.history.connect(self.history)
        bridge.reply.connect(self.reply)
        bridge.request_observed.connect(self.sent)
        self.render()
        self.state_changed(bridge.state.value,bridge.detail)

    def open_plugin(self):
        open_desktop_plugin()

    def open_link(self,url):
        if url.scheme() in ('http','https'):QDesktopServices.openUrl(url)

    def send(self):
        text=self.input.toPlainText().strip()
        if not text:return
        if not self.bridge.ready:
            QApplication.clipboard().setText(text)
            opened=self.bridge.open_conversation()
            self.notice('草稿已复制，GPT 聊天还没有连接。' if opened else '草稿留在这里，GPT 暂时打不开。')
            return
        if self.bridge.send(text):
            self.pending_text=text
            self.input.setReadOnly(True)

    def new_desktop_chat(self):
        text=self.input.toPlainText().strip()
        if self.bridge.ready and self.bridge.desktop and text:
            if self.bridge.send(text,new=True):
                self.pending_text=text;self.input.setReadOnly(True)
            return
        if text:QApplication.clipboard().setText(text)
        opened=DesktopChatGPTLauncher.open(text,new=True)
        self.notice('新聊天已打开，草稿待主人发送。' if opened else 'GPT 暂时打不开，草稿留在这里。')

    def sent(self,_id,text):
        if text==self.pending_text:
            if self.bridge.desktop:
                self.messages.append(dict(role='user',text=text,id=_id));self.render()
            self.input.clear();self.pending_text='';self.input.setReadOnly(False)

    def state_changed(self,state,detail):
        self.status.setText('●' if self.bridge.ready else '○')
        self.status.setToolTip(detail);self.input.setToolTip(detail)
        sending=state in (ChatState.SENDING.value,ChatState.GENERATING.value)
        self.send_button.setEnabled(not sending and not self.bridge.uncertain)
        self.send_button.setText('…' if sending else '↑')
        self.send_button.setToolTip('发送 · Enter' if self.bridge.ready else '复制草稿并打开 GPT')
        if state in (ChatState.FAILED.value,ChatState.DISCONNECTED.value):
            self.input.setReadOnly(False)
        elif state==ChatState.COMPLETED.value and self.pending_text:
            self.sent('',self.pending_text)

    def history(self,messages):
        self.messages=messages
        self.render()

    def reply(self,ident,text,done):
        existing=next((m for m in self.messages if m.get('id')==ident),None)
        if existing:existing['text']=text
        else:self.messages.append(dict(role='assistant',text=text,id=ident))
        self.render()

    def render(self):
        latest=next((m for m in reversed(self.messages) if m['role']=='assistant'),None)
        if latest and self.pet:
            self.pet.bubble.hide()
            self.answers.say(latest['text'],self.pet)

    def notice(self,text):
        if self.pet:self.answers.say(text,self.pet,title='霜璃')

    def copy(self):
        selected=self.answers.view.textCursor().selectedText()
        text=selected or (self.messages[-1]['text'] if self.messages else self.input.toPlainText())
        QApplication.clipboard().setText(text)

    def reposition(self,pet):
        screen=pet.screen().availableGeometry()
        x=pet.x()+pet.width()//2-self.width()//2
        self.move(max(screen.left(),min(screen.right()-self.width()+1,x)),pet.y()+pet.height()+6)

    def show_near(self,pet,focus=True):
        self.pet=pet
        if not self.isVisible():
            self.hover_origin=pet.frameGeometry().adjusted(-12,-12,12,20)
            screen=pet.screen().availableGeometry()
            self.lift=max(0,pet.y()+pet.height()+self.height()+6-screen.bottom()-1)
            pet.dock_reserve=self.height()+6 if self.lift else 0
            pet.dock_lift=self.lift
            if self.lift:
                self.attached=(pet.attached,pet.attached_rect)
                pet.attached=None;pet.attached_rect=None
                pet.ypos-=self.lift;pet.place()
            self.anchor=(pet.x(),pet.y())
            self.reposition(pet);self.show();self.raise_()
        if focus:self.activateWindow();self.input.setFocus()
        else:self.input.clearFocus();self.send_button.clearFocus()
        self.leave_since=None

    def hideEvent(self,event):
        if self.pet:
            self.pet.dock_reserve=0;self.pet.dock_lift=0;self.pet.dock_open=False
            if self.lift and self.anchor==(self.pet.x(),self.pet.y()) and not self.pet.dragging:
                self.pet.ypos+=self.lift;self.pet.place()
                if self.attached:self.pet.attached,self.pet.attached_rect=self.attached
            self.lift=0;self.anchor=None
            self.attached=None
            self.hover_origin=None
        super().hideEvent(event)

    def update_hover(self,pet,blocked=False):
        self.pet=pet
        if blocked or not pet.isVisible() or pet.config['click_through'] or pet.dragging:
            if self.isVisible():self.hide()
            return
        cursor=QCursor.pos()
        margin=max(16,round(pet.width()*.08))
        near=pet.frameGeometry().adjusted(-margin,-margin,margin,margin).contains(cursor)
        inside=self.isVisible() and self.frameGeometry().adjusted(-12,-14,12,12).contains(cursor)
        transit=(self.isVisible() and self.lift>0 and self.anchor==(pet.x(),pet.y())
                 and self.hover_origin is not None and self.hover_origin.contains(cursor))
        if near or inside or transit:
            if not self.isVisible():self.show_near(pet,focus=False)
            self.leave_since=None
        elif self.isVisible():
            now=time.monotonic()
            if self.leave_since is None:self.leave_since=now
            elif now-self.leave_since>.25:self.hide()
        if self.isVisible():self.reposition(pet)
        if self.answers.isVisible():self.answers.reposition(pet)
        pet.dock_open=self.isVisible()


class Bubble(QWidget):
    def __init__(self):
        super().__init__(None,Qt.WindowType.Tool|Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint|Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        layout=QVBoxLayout(self);layout.setContentsMargins(14,10,14,10)
        self.label=QLabel();self.label.setWordWrap(True)
        self.label.setStyleSheet('color:#795d94;font:9pt "Microsoft YaHei UI";background:transparent;')
        self.label.setMaximumWidth(210);layout.addWidget(self.label)
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.timeout.connect(self.hide)

    def say(self,text,pet,seconds=4):
        if getattr(pet,'reply_bubble',None) and pet.reply_bubble.isVisible():return
        self.label.setText(text);self.adjustSize();self.reposition(pet)
        self.show();self.timer.start(int(seconds*1000))

    def reposition(self,pet):
        screen=pet.screen().availableGeometry()
        self.move(max(screen.left(),min(screen.right()-self.width()+1,pet.x()+pet.width()//2-self.width()//2)),
                  max(screen.top(),pet.y()-self.height()-5))

    def paintEvent(self,_):
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor('#dac7ee'));painter.setBrush(QColor(252,249,255,240))
        painter.drawRoundedRect(self.rect().adjusted(1,1,-1,-1),13,13)


class ReplyBubble(Bubble):
    def __init__(self):
        QWidget.__init__(self,None,Qt.WindowType.Tool|Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setStyleSheet(STYLE)
        self.resize(320,200);self.raw=''
        layout=QVBoxLayout(self);layout.setContentsMargins(12,8,12,12);layout.setSpacing(4)
        row=QHBoxLayout();self.title=QLabel('ChatGPT');row.addWidget(self.title);row.addStretch()
        for caption,callback in [('复制',lambda:QApplication.clipboard().setText(self.view.textCursor().selectedText() or self.raw)),('×',self.hide)]:
            button=QPushButton(caption);button.setStyleSheet('padding:2px 7px;border:0;background:transparent;')
            button.clicked.connect(callback);row.addWidget(button)
        layout.addLayout(row)
        self.view=SafeBrowser();self.view.setOpenExternalLinks(False)
        self.view.setStyleSheet('QTextBrowser{background:transparent;border:0;padding:0;}')
        self.view.anchorClicked.connect(lambda url:QDesktopServices.openUrl(url) if url.scheme() in ('https','http') else None)
        layout.addWidget(self.view)

    def say(self,text,pet,title='ChatGPT'):
        self.raw=text;self.title.setText(title)
        bar=self.view.verticalScrollBar();position=bar.value();at_bottom=position>=bar.maximum()-24
        self.view.setMarkdown(text)
        self.view.document().setTextWidth(self.width()-28)
        height=min(260,max(86,int(self.view.document().size().height())+54))
        self.resize(320,height);self.reposition(pet);self.show()
        if at_bottom:bar.setValue(bar.maximum())
        else:bar.setValue(position)


class Settings(QDialog):
    applied=Signal()
    def __init__(self,config,bridge):
        super().__init__()
        self.config=config;self.bridge=bridge;self.controls={}
        self.setWindowTitle('霜璃 · 小小的设置');self.resize(690,630);self.setStyleSheet(STYLE)
        root=QVBoxLayout(self);root.setContentsMargins(22,20,22,18)
        title=QLabel('陪在主人身边');title.setObjectName('title');root.addWidget(title)
        tabs=QTabWidget();root.addWidget(tabs,1)
        forms={}
        for name in ('形象','动画','互动','聊天连接','通知','隐私','快捷键','启动'):
            widget=QWidget();form=QFormLayout(widget);form.setContentsMargins(20,20,20,20);form.setSpacing(14)
            forms[name]=form;tabs.addTab(widget,name)
        self.combo(forms['形象'],'renderer','显示方式',[('live2d','Live2D · 基础绑定'),('sprite','2D 原图 · 安静陪伴')])
        self.number(forms['形象'],'scale','大小',.5,2.5,.1)
        self.number(forms['形象'],'opacity','透明度',.25,1,.05)
        self.line(forms['形象'],'live2d_path','自选模型')
        choose=QPushButton('选择授权的 .model3.json');choose.clicked.connect(self.choose_model);forms['形象'].addRow(choose)
        note=QLabel('严格依照主人指定的 Q 版原图。手办与工作桌造型仅归档。');note.setObjectName('subtitle');forms['形象'].addRow(note)
        self.number(forms['动画'],'fps','帧率',10,60,1,True)
        self.check(forms['动画'],'reduced_motion','减少动作幅度')
        self.check(forms['动画'],'spontaneous_actions','自然互动与闲置小动作')
        packs=[('default','霜璃 · 指定 Q 版')]+[(p.name,p.name) for p in (DATA/'packs').glob('*') if (p/'pack.json').exists()]
        self.combo(forms['动画'],'pack','动作皮肤',packs)
        import_button=QPushButton('导入动作皮肤 ZIP');import_button.clicked.connect(self.import_skin);forms['动画'].addRow(import_button)
        self.combo(forms['互动'],'mode','陪伴方式',[('fixed','待在这里'),('follow','跟随鼠标'),('roam','自由漫游')])
        for key,label in [('gravity','拖放后自然落下'),('window_standing','停在普通窗口顶部'),('click_through','鼠标穿透'),('topmost','置顶'),('quiet','安静陪伴')]:self.check(forms['互动'],key,label)
        self.line(forms['聊天连接'],'conversation_url','原会话链接')
        self.combo(forms['聊天连接'],'chat_target','聊天入口',[('desktop','GPT 桌面端'),('browser','浏览器原会话')])
        desktop_plugin=QPushButton('打开霜璃桌宠插件');desktop_plugin.clicked.connect(open_desktop_plugin);forms['聊天连接'].addRow(desktop_plugin)
        desktop_note=QLabel('在 Chat 里打开霜璃插件的连接面板。连上后，脚下输入，头顶看回答。')
        desktop_note.setWordWrap(True);forms['聊天连接'].addRow(desktop_note)
        self.check(forms['聊天连接'],'bridge_enabled','启用授权网页桥接（可选）')
        self.line(forms['聊天连接'],'extension_id','扩展编号')
        help_label=QLabel('以下为可选浏览器组件；GPT 桌面聊天使用上面的霜璃插件。')
        help_label.setWordWrap(True);help_label.setObjectName('subtitle');forms['聊天连接'].addRow(help_label)
        folder=QPushButton('打开扩展文件夹');folder.clicked.connect(lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(str(HOME/'extension'))));forms['聊天连接'].addRow(folder)
        registration=QPushButton('登记到当前用户的 Chrome / Edge');registration.clicked.connect(self.register_host);forms['聊天连接'].addRow(registration)
        uninstall=QPushButton('移除本程序的桥接登记');uninstall.clicked.connect(self.unregister_host);forms['聊天连接'].addRow(uninstall)
        official=QLabel('官方集成：'+OfficialIntegration.reason);official.setWordWrap(True);official.setObjectName('subtitle');forms['聊天连接'].addRow(official)
        self.number(forms['通知'],'reminder_minutes','休息提醒（分钟，0 关闭）',0,240,5,True)
        hint=QLabel('提醒默认为关闭。只提醒，不自动打开录音。');hint.setObjectName('subtitle');forms['通知'].addRow(hint)
        self.todo=QListWidget()
        for todo in config['todos']:
            if isinstance(todo,dict):self.add_todo(todo.get('text',''),todo.get('done',False))
        forms['通知'].addRow('本地待办',self.todo)
        self.todo_input=QLineEdit();self.todo_input.setPlaceholderText('给主人记一件事');forms['通知'].addRow(self.todo_input)
        row=QHBoxLayout();add=QPushButton('记下');add.clicked.connect(lambda:self.add_todo(self.todo_input.text()));row.addWidget(add)
        remove=QPushButton('删掉所选');remove.clicked.connect(lambda:self.todo.takeItem(self.todo.currentRow()));row.addWidget(remove);forms['通知'].addRow(row)
        privacy=QLabel('设置、位置、触摸状态与待办只存在本机。\n聊天面板仅在内存中显示网页传来的消息，退出后不留聊天副本。\n不读取 Cookie、Token、隐藏推理、桌面截图或窗口标题。\n本机桥接只监听 127.0.0.1，使用每次启动更新的本机配对密钥。\n语音接口留待主人主动安装和启用。')
        privacy.setWordWrap(True);forms['隐私'].addRow(privacy)
        data=QPushButton('打开本地设置目录');data.clicked.connect(lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(str(DATA))));forms['隐私'].addRow(data)
        clear=QPushButton('清空本地待办和互动状态');clear.clicked.connect(self.clear_local);forms['隐私'].addRow(clear)
        self.line(forms['快捷键'],'hotkey_show','显示 / 解除穿透')
        self.line(forms['快捷键'],'hotkey_chat','打开聊天')
        self.check(forms['启动'],'startup','随 Windows 登录启动')
        desc=QLabel('便携程序，不需要管理员权限。\n移除桥接登记并关闭开机启动后，可以直接移走程序目录。');desc.setWordWrap(True);forms['启动'].addRow(desc)
        self.feedback=QLabel();self.feedback.setWordWrap(True);self.feedback.setObjectName('subtitle');root.addWidget(self.feedback)
        bottom=QHBoxLayout();bottom.addStretch();close=QPushButton('收起');close.clicked.connect(self.hide);bottom.addWidget(close)
        save=QPushButton('保存');save.setObjectName('primary');save.clicked.connect(self.save);bottom.addWidget(save);root.addLayout(bottom)

    def line(self,form,key,label):
        value=QLineEdit(str(self.config[key]));self.controls[key]=value;form.addRow(label,value)
    def check(self,form,key,label):
        value=QCheckBox(label);value.setChecked(bool(self.config[key]));self.controls[key]=value;form.addRow(value)
    def number(self,form,key,label,low,high,step,integer=False):
        value=QSpinBox() if integer else QDoubleSpinBox();value.setRange(low,high);value.setSingleStep(step);value.setValue(int(self.config[key]) if integer else self.config[key]);self.controls[key]=value;form.addRow(label,value)
    def combo(self,form,key,label,options):
        value=QComboBox()
        for code,text in options:value.addItem(text,code)
        value.setCurrentIndex(max(0,value.findData(self.config[key])));self.controls[key]=value;form.addRow(label,value)
    def choose_model(self):
        file,_=QFileDialog.getOpenFileName(self,'选择主人的模型','','Live2D (*.model3.json)')
        if file:self.controls['live2d_path'].setText(file)
    def import_skin(self):
        file,_=QFileDialog.getOpenFileName(self,'导入动作皮肤','','Pet pack (*.zip)')
        if file:
            try:
                name=import_pack(file);self.controls['pack'].addItem(name,name);self.controls['pack'].setCurrentIndex(self.controls['pack'].findData(name));self.feedback.setText('皮肤已保存在本机，保存后应用。')
            except Exception as e:self.feedback.setText(str(e))
    def register_host(self):
        try:
            ident=self.controls['extension_id'].text().strip();install_host(ident)
            self.config['extension_id']=ident;self.config['bridge_enabled']=True;self.config.save()
            self.controls['bridge_enabled'].setChecked(True)
            self.bridge.start();self.feedback.setText('已登记本机桥接。主人可以去原会话绑定这一页了。')
        except Exception as e:self.feedback.setText(str(e))
    def unregister_host(self):
        try:
            self.bridge.stop();uninstall_host();self.config['bridge_enabled']=False;self.config.save();self.controls['bridge_enabled'].setChecked(False);self.feedback.setText('本程序的桥接登记已移除。')
        except Exception as e:self.feedback.setText(str(e))
    def add_todo(self,text,done=False):
        text=str(text).strip()[:500]
        if not text:return
        item=QListWidgetItem(text);item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable);item.setCheckState(Qt.CheckState.Checked if done else Qt.CheckState.Unchecked);self.todo.addItem(item)
        if hasattr(self,'todo_input'):self.todo_input.clear()
    def clear_local(self):
        self.todo.clear();self.config['mood']=0;self.config['touch_count']=0;self.config['todos']=[];self.config.save();self.feedback.setText('本地待办和触摸状态已经清空。')
    def save(self):
        values={}
        for key,control in self.controls.items():
            if isinstance(control,QLineEdit):values[key]=control.text().strip()
            elif isinstance(control,QCheckBox):values[key]=control.isChecked()
            elif isinstance(control,QComboBox):values[key]=control.currentData()
            else:values[key]=control.value()
        if values['conversation_url'] and not conversation_url(values['conversation_url']):
            self.feedback.setText('请给主人填入 https://chatgpt.com/c/… 的已有会话链接。');return
        if values['bridge_enabled'] and not __import__('re').fullmatch('[a-p]{32}',values['extension_id']):
            self.feedback.setText('桥接还需要有效的浏览器扩展编号。');return
        if values['startup']!=self.config['startup']:
            if not getattr(sys,'frozen',False):self.feedback.setText('开机启动请在打包后的程序中设置。');return
            try:startup(values['startup'],sys.executable)
            except OSError as e:self.feedback.setText(str(e));return
        reconnect=any(values[k]!=self.config[k] for k in ('bridge_enabled','extension_id','conversation_url','chat_target'))
        self.config.values.update(values)
        self.config['todos']=[dict(text=self.todo.item(i).text(),done=self.todo.item(i).checkState()==Qt.CheckState.Checked) for i in range(self.todo.count())]
        try:
            self.config.save()
            if reconnect:self.bridge.start()
            self.applied.emit();self.feedback.setText('保存好了，主人。')
        except Exception as e:self.feedback.setText(str(e))
