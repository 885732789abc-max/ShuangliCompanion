from __future__ import annotations

import json
import logging
import math
import time
import os
import random
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal, QSize
from PySide6.QtGui import QCursor, QSurfaceFormat, QOpenGLContext, QOffscreenSurface, QImage, QPainter
from PySide6.QtOpenGL import QOpenGLFramebufferObject, QOpenGLFramebufferObjectFormat
from PySide6.QtWidgets import QWidget
from .config import ROOT
from .behavior import expression_values, IdleMotion


class Live2DView(QWidget):
    failed = Signal(str)

    def __init__(self, model_path, parent):
        super().__init__(parent)
        fmt=QSurfaceFormat()
        fmt.setAlphaBufferSize(8)
        fmt.setVersion(2,1)
        fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CompatibilityProfile)
        fmt.setSamples(0)
        self.gl_format=fmt
        self.context=None;self.surface=None;self.fbo=None
        self.image=QImage();self.initialized=False
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAutoFillBackground(False)
        self.setStyleSheet('background: transparent')
        self.path=Path(model_path)
        self.model=None
        self.runtime=None
        self.params=set()
        self.action='idle'
        self.started=time.monotonic()
        self.last_error=False
        self.smoothed={}
        self.target={}
        self.last=time.monotonic()
        self.mood=0
        self.reduce=False
        self.bridge_state='未连接'
        self.conservative=self.path.parent.name.startswith('shuangli-q') or (self.path.parent/'idle-rig.json').is_file()
        self.backing=parent.art.toImage() if self.conservative else QImage()
        if self.conservative:
            face=QImage(str(self.path.parent/'face-backing.png'))
            if not face.isNull():
                painter=QPainter(self.backing)
                painter.drawImage(209,328,face);painter.end()
        self.backing_scaled=QImage()
        self.frame_cost={}
        self.memory_pressure=False
        self.previous_pressure=False
        self.last_target_signature=None
        self.next_blink=self.started+random.uniform(2,5)
        self.blink_started=-100.0
        self.blink_duration=.26
        self.idle_motion=IdleMotion()
        self.idle_rig=(self.path.parent/'idle-rig.json').is_file()
        if self.idle_rig:
            stationary=QImage(str(self.path.parent/'neutral-backing.png'))
            if not stationary.isNull():
                self.backing=stationary
                face=QImage(str(self.path.parent/'face-backing.png'))
                if not face.isNull():
                    painter=QPainter(self.backing);painter.drawImage(209,328,face);painter.end()
            else:self.idle_rig=False

    def initializeGL(self):
        try:
            self.surface=QOffscreenSurface();self.surface.setFormat(self.gl_format);self.surface.create()
            self.context=QOpenGLContext();self.context.setFormat(self.gl_format)
            if not self.context.create() or not self.context.makeCurrent(self.surface):
                raise RuntimeError('Cannot create offscreen OpenGL context')
            if os.environ.get('SHUANGLI_RUNTIME')=='legacy':
                import live2d.v3 as live2d
            else:
                import live2d
            self.runtime=live2d
            live2d.init()
            (getattr(live2d,'glInit',None) or live2d.glewInit)()
            self.model=(getattr(live2d,'Model',None) or live2d.LAppModel)()
            self.model.LoadModelJson(str(self.path))
            self.model.Resize(self.width(),self.height())
            spec=json.loads(self.path.read_text(encoding='utf-8'))
            info=spec.get('FileReferences',{}).get('DisplayInfo')
            if info:
                meta=json.loads((self.path.parent/info).read_text(encoding='utf-8'))
                self.params={p['Id'] for p in meta.get('Parameters',[])}
            if hasattr(self.model,'GetParamIds'):self.params=set(self.model.GetParamIds())
            (getattr(self.model,'SetAutoBlink',None) or self.model.SetAutoBlinkEnable)(False)
            (getattr(self.model,'SetAutoBreath',None) or self.model.SetAutoBreathEnable)(False)
            if hasattr(self.model,'StopAllMotions'):self.model.StopAllMotions()
        except Exception:
            logging.exception('Live2D load failed')
            self.model=None
            QTimer.singleShot(0,lambda:self.failed.emit('Live2D 暂时不能加载，霜璃先用同一套 2D 原画陪主人。'))
        finally:
            self.initialized=True
            if self.context:self.context.doneCurrent()

    def ensure_target(self):
        ratio=min(1.0 if self.memory_pressure else 1.5,self.devicePixelRatioF())
        if self.previous_pressure!=self.memory_pressure:
            self.previous_pressure=self.memory_pressure
            # Keep the small authored face backing intact across pressure changes.
        size=QSize(max(1,round(self.width()*ratio)),max(1,round(self.height()*ratio)))
        if not self.fbo or self.fbo.size()!=size:
            self.fbo=None
            fmt=QOpenGLFramebufferObjectFormat();fmt.setInternalTextureFormat(0x8058)
            self.fbo=QOpenGLFramebufferObject(size,fmt)
            if not self.fbo.isValid():raise RuntimeError('Invalid RGBA framebuffer')
            self.model.Resize(size.width(),size.height())
            if self.conservative:
                source=self.backing
                if source.isNull():source=self.parentWidget().art.toImage()
                self.backing_scaled=source.scaled(size,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)

    def set_action(self,action,started=None):
        if self.action!=action or started is not None and self.started!=started:
            self.action=action;self.started=started if started is not None else time.monotonic()

    def set_param(self,ident,value,dt):
        if self.params and ident not in self.params:return
        previous=self.smoothed.get(ident,value)
        speed=40 if ident in ('ParamEyeLOpen','ParamEyeROpen') else 13
        smooth=previous+(value-previous)*(1-math.exp(-dt*speed))
        self.smoothed[ident]=smooth
        (getattr(self.model,'SetParamById',None) or self.model.SetParameterValue)(ident,smooth,1.0)

    def advance_frame(self):
        start=time.perf_counter()
        if not self.initialized:self.initializeGL()
        if not self.model: return
        try:
            if not self.context.makeCurrent(self.surface):raise RuntimeError('OpenGL context lost')
            self.ensure_target()
            self.fbo.bind()
            from OpenGL.GL import glViewport,glDisable,GL_SCISSOR_TEST
            glViewport(0,0,self.fbo.width(),self.fbo.height());glDisable(GL_SCISSOR_TEST)
            self.runtime.clearBuffer(0,0,0,0)
            begin=time.perf_counter()
            now=time.monotonic();dt=min(.1,now-self.last);self.last=now
            cursor=self.mapFromGlobal(QCursor.pos())
            dx=max(-1,min(1,(cursor.x()/max(1,self.width())-.5)*1.2))
            dy=max(-1,min(1,(.5-cursor.y()/max(1,self.height()))*1.2))
            t=now-self.started
            breath=.5+.35*math.sin(now*1.8)
            if now>=self.next_blink:
                self.blink_started=now;self.blink_duration=random.uniform(.22,.34)
                self.next_blink=now+random.uniform(3.2,7.5)
            blink_phase=(now-self.blink_started)/self.blink_duration
            blink=1 if blink_phase>=1 else max(0,min(1,(abs(blink_phase-.5)-.12)/.38))
            sleeping=self.action=='sleep'
            hurt=self.action=='hurt'
            happy=self.action=='happy'
            work=self.bridge_state in ('发送中','生成中')
            values={
                'ParamAngleX':dx*14,'ParamAngleY':dy*10,
                'ParamAngleZ':-3 if hurt else 2*math.sin(now*.6),
                'ParamBreath':breath,
                'ParamEyeLOpen':0 if sleeping else blink,
                'ParamEyeROpen':0 if sleeping else blink,
                'ParamEyeBallX':dx*.7,'ParamEyeBallY':dy*.5,
                'ParamDragonAhoge':0 if self.reduce else math.sin(now*2.1)*.5,
                'ParamDragonTailBase':0 if self.reduce else math.sin(now*1.5)*.6,
                'ParamHairFront':0 if self.reduce else math.sin(now*1.2)*.35,
                'ParamHairSide':0 if self.reduce else math.sin(now*1.1+.4)*.3,
                'ParamHairBack':0 if self.reduce else math.sin(now*.9)*.3,
                'ParamTail':0 if self.reduce else math.sin(now*1.3)*12,
                'ParamWingL':0 if self.reduce else math.sin(now*1.8)*8,
                'ParamWingR':0 if self.reduce else math.sin(now*1.8+.2)*8,
                'ParamBodyAngleX':dx*3,
                'ParamBodyAngleY':-4 if sleeping else 4*math.sin(t*2) if self.action=='stretch' else dy*2,
                'ParamBodyAngleZ':-4 if hurt else math.sin(t*5)*3 if self.action=='happy' else 1.0*math.sin(now*.8),
                'ParamMouthForm':-.6 if hurt else .8 if happy else .2,
                'ParamMouthOpenY':.12 if happy else 0,
                'ParamCheek':.7 if happy else max(0,self.mood)*.15,
                'ParamBrowLY':-.4 if hurt else .2 if happy else 0,
                'ParamBrowRY':-.4 if hurt else .2 if happy else 0,
                'ParamDragonMouseX':dx*.4 if not work else math.sin(now*2.5)*.45,
                'ParamDragonKeyIndex':(.5+.5*math.sin(now*8)) if work else 0,
            }
            duration=self.parentWidget().player.action.duration or 2.4
            parent=self.parentWidget()
            idle_enabled=(not self.reduce and self.action=='idle' and
                          parent.config['spontaneous_actions'] and not parent.chat_open and not work)
            ambient=self.idle_motion.values(now,enabled=idle_enabled,quiet=parent.config['quiet'],
                available=self.params,cursor_near=(-.25*self.width()<=cursor.x()<=1.25*self.width()
                                                  and -.25*self.height()<=cursor.y()<=self.height()))
            values.update(ambient)
            for ident in ('ParamEyeLOpen','ParamEyeROpen'):
                if ident in ambient:values[ident]*=blink
            values.update(expression_values(self.action,t,duration,blink,dx,dy,self.reduce))
            if self.conservative:
                # These source cuts have no hidden artwork. Do not pull their adjoining edges apart.
                for ident in ('ParamAngleX','ParamAngleY','ParamAngleZ','ParamBodyAngleX',
                              'ParamBodyAngleY','ParamBodyAngleZ','ParamBreath',
                              'ParamHairFront','ParamHairSide','ParamHairBack'):
                    values[ident]=0
                values['ParamEyeBallX']*=.85;values['ParamEyeBallY']*=.85
                if not self.idle_rig:
                    values['ParamTail']=0 if self.reduce else values['ParamTail']/6
                    values['ParamWingL']=0 if self.reduce else values['ParamWingL']*.1875
                    values['ParamWingR']=0 if self.reduce else values['ParamWingR']*.1875
            active={ident:value for ident,value in values.items() if not self.params or ident in self.params}
            signature=(self.fbo.width(),self.fbo.height(),tuple((ident,round(value,4)) for ident,value in active.items()))
            settling=any(abs(self.smoothed.get(ident,value)-value)>.005 for ident,value in active.items())
            if signature==self.last_target_signature and not settling and not self.image.isNull():
                self.frame_cost.update(update_ms=0,draw_ms=0,read_ms=0)
                self.update()
                return
            self.model.Update()
            self.frame_cost['update_ms']=(time.perf_counter()-begin)*1000
            for ident,value in active.items():self.set_param(ident,value,dt)
            self.last_target_signature=signature
            begin=time.perf_counter()
            self.model.Draw()
            self.frame_cost['draw_ms']=(time.perf_counter()-begin)*1000
            self.fbo.bind()
            frame=self.fbo.toImage(True)
            if self.conservative and not self.backing_scaled.isNull():
                # Complementary antialiased cuts do not recombine to opaque coverage under source-over.
                # Share the unchanged original under the neutral rig so subpixel cut edges cannot open holes.
                composed=self.image
                if composed.size()!=frame.size() or composed.format()!=QImage.Format.Format_ARGB32_Premultiplied:
                    composed=QImage(frame.size(),QImage.Format.Format_ARGB32_Premultiplied)
                composed.fill(Qt.GlobalColor.transparent)
                painter=QPainter(composed)
                painter.drawImage((frame.width()-self.backing_scaled.width())//2,
                                  frame.height()-self.backing_scaled.height(),self.backing_scaled)
                painter.drawImage(0,0,frame);painter.end()
                self.image=composed
            else:self.image=frame
            self.frame_cost['read_ms']=(time.perf_counter()-begin)*1000-self.frame_cost['draw_ms']
            self.update()
        except Exception:
            if not self.last_error:
                self.last_error=True;logging.exception('Live2D renderer failed')
                QTimer.singleShot(0,lambda:self.failed.emit('Live2D 渲染中断，霜璃先退回 2D 原画。'))
        finally:
            if self.context:self.context.doneCurrent()
            self.frame_cost['total_ms']=(time.perf_counter()-start)*1000

    def shutdown(self):
        if self.runtime and self.model:
            try:
                self.context.makeCurrent(self.surface)
                self.model=None;self.fbo=None;self.runtime.dispose()
                self.context.doneCurrent();self.image=QImage()
            except Exception:logging.exception('Live2D shutdown')
        if self.surface:self.surface.destroy()
