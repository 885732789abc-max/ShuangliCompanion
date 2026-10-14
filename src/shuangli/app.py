from __future__ import annotations

import ctypes
import logging
import os
import sys
from ctypes import wintypes

from PySide6.QtCore import QTimer,Qt
from PySide6.QtGui import QIcon,QSurfaceFormat,QPixmapCache
from PySide6.QtNetwork import QLocalServer,QLocalSocket
from PySide6.QtWidgets import QApplication,QSystemTrayIcon,QMessageBox

from .config import Config,ROOT,DATA,setup_logging
from .bridge import DesktopConversationBridge
from .pet import Pet
from .platform_win import Hotkeys
from .ui import ChatPanel,Settings
from .plugins import PluginRegistry


class Application:
    def __init__(self,app):
        self.app=app;self.config=Config()
        self.bridge=DesktopConversationBridge(self.config)
        self.pet=Pet(self.config,self.bridge)
        self.settings=Settings(self.config,self.bridge)
        self.chat=ChatPanel(self.bridge,self.show_settings)
        self.pet.reply_bubble=self.chat.answers
        self.plugins=PluginRegistry();self.pet.plugin_commands=self.plugins.commands
        self.pet.chat_requested.connect(self.show_chat)
        self.pet.settings_requested.connect(self.show_settings)
        self.pet.exit_requested.connect(app.quit)
        self.settings.applied.connect(self.apply)
        self.tray=QSystemTrayIcon(QIcon(str(ROOT/'assets/shuangli.ico')),app)
        self.tray.setToolTip('霜璃 · 双击回来陪主人')
        self.tray.setContextMenu(self.pet.menu())
        self.tray.activated.connect(self.tray_activated)
        self.tray.show()
        self.hotkeys=Hotkeys([self.pet.recover,self.show_chat]);app.installNativeEventFilter(self.hotkeys)
        self.configure_hotkeys()
        self.save_timer=QTimer();self.save_timer.timeout.connect(self.save);self.save_timer.start(30000)
        self.ui_timer=QTimer();self.ui_timer.timeout.connect(self.update_ui_state);self.ui_timer.start(100)
        app.aboutToQuit.connect(self.shutdown)
        self.bridge.start()
        if self.config.problem:self.pet.bubble.say(self.config.problem,self.pet)

    def configure_hotkeys(self):
        failed=self.hotkeys.configure(self.config['hotkey_show'],self.config['hotkey_chat'])
        if failed:self.settings.feedback.setText('这些快捷键暂时不能登记：'+', '.join(failed)+'。托盘仍可唤回霜璃。')
    def tray_activated(self,reason):
        if reason in (QSystemTrayIcon.ActivationReason.DoubleClick,QSystemTrayIcon.ActivationReason.Trigger):self.pet.recover()
    def show_chat(self):
        self.pet.wake();self.chat.show_near(self.pet)
    def show_settings(self):
        self.settings.controls['conversation_url'].setText(self.config['conversation_url'])
        self.settings.show();self.settings.raise_();self.settings.activateWindow()
    def apply(self):
        self.pet.apply_settings();self.configure_hotkeys()
        self.tray.setContextMenu(self.pet.menu())
    def update_ui_state(self):
        self.chat.update_hover(self.pet,blocked=self.settings.isVisible() or self.pet.paused)
        self.pet.chat_open=(self.chat.isVisible() and ((self.chat.input.hasFocus() and self.chat.isActiveWindow()) or bool(self.chat.input.toPlainText().strip()) or self.bridge.pending is not None)) or self.settings.isVisible()
        if not self.pet.isVisible() or self.pet.paused:self.chat.answers.hide()
    def save(self):
        try:self.pet.persist()
        except OSError:logging.exception('Settings save failed')
    def shutdown(self):
        self.save_timer.stop();self.ui_timer.stop();self.hotkeys.close()
        self.bridge.stop();self.bridge.timer.stop()
        self.chat.messages.clear();self.chat.answers.close();self.chat.close();self.settings.close()
        self.pet.shutdown();self.tray.hide()
        (DATA/'running.json').unlink(missing_ok=True)


def main():
    os.environ.setdefault('QSG_RHI_BACKEND','opengl')
    setup_logging()
    fmt=QSurfaceFormat();fmt.setAlphaBufferSize(8);fmt.setVersion(2,1)
    fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CompatibilityProfile)
    QSurfaceFormat.setDefaultFormat(fmt)
    app=QApplication(sys.argv);app.setApplicationName('ShuangliCompanion');app.setQuitOnLastWindowClosed(False)
    QPixmapCache.setCacheLimit(2048)
    if sys.platform=='win32':
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('Shuangli.Companion.1')
    probe=QLocalSocket();probe.connectToServer('ShuangliCompanion-v1')
    if probe.waitForConnected(250):
        probe.write(b'show');probe.waitForBytesWritten(250);return 0
    server=QLocalServer();server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
    if not server.listen('ShuangliCompanion-v1'):
        QMessageBox.information(None,'霜璃','另一只霜璃已经在陪主人了。');return 0
    config=Config()
    marker=DATA/'running.json'
    if marker.exists():
        # A previous unclean shutdown enters safe 2D mode. It never opens another model backend.
        config['renderer']='sprite';config['reduced_motion']=True;config.save()
    from .config import atomic_json
    atomic_json(marker,dict(pid=os.getpid()))
    application=Application(app)
    if '--inspect-runtime' in sys.argv:
        # Explicit diagnostic launch: same production application/model, targetable window and local captures.
        import time,json
        directory=DATA/'diagnostics';directory.mkdir(exist_ok=True)
        application.pet.setWindowFlag(Qt.WindowType.Tool,False)
        application.pet.setWindowFlag(Qt.WindowType.Window,True)
        application.pet.show()
        started=time.monotonic();samples=[]
        def capture_frame():
            live=application.pet.live
            if live and live.frame_cost:samples.append(dict(live.frame_cost))
        sampling=QTimer(app);sampling.timeout.connect(capture_frame);sampling.start(33)
        def capture_result():
            application.pet.grab().save(str(directory/'pet-release.png'))
            live=application.pet.live
            if live:live.image.save(str(directory/'frame-release.png'))
            values=sorted(v['total_ms'] for v in samples)
            (directory/'render.json').write_text(json.dumps({'samples':len(values),
                'median_frame_ms':values[len(values)//2] if values else None,
                'max_frame_ms':max(values) if values else None,
                'renderer_loaded':bool(live and live.model),'elapsed_seconds':time.monotonic()-started,
                'model':str(live.path) if live else ''}),encoding='utf-8')
        QTimer.singleShot(10000,capture_result)
        def capture_sleep_pose():
            pet=application.pet
            pet.chat_open=True
            pet.vx=pet.vy=0
            pet.sleeping=True
            pet.player.play('sleep',5,True)
        QTimer.singleShot(12000,capture_sleep_pose)
        QTimer.singleShot(14000,lambda:application.pet.grab().save(str(directory/'pet-release-closed.png')))
        QTimer.singleShot(30000,app.quit)
    def activate():
        while server.hasPendingConnections():
            socket=server.nextPendingConnection();application.pet.recover();socket.disconnectFromServer()
    server.newConnection.connect(activate)
    def fatal(kind,error,tb):
        logging.error('Unhandled error',exc_info=(kind,error,tb))
        application.pet.paused=True
        application.pet.bubble.say('霜璃遇到了一点小麻烦，先安静陪主人。',application.pet,6)
    sys.excepthook=fatal
    result=app.exec();server.close();return result
