from __future__ import annotations

import logging
import math
import os
import time

from PySide6.QtCore import QPoint,QPointF,QRectF,Qt,QTimer,Signal
from PySide6.QtGui import QPainter,QPixmap,QCursor,QRegion,QImage
from PySide6.QtWidgets import QApplication,QWidget,QMenu

from .config import ROOT
from .animation import AssetPack,AnimationPlayer,Emotion
from .behavior import CompanionBehavior,reaction_pose
from .platform_win import click_through,platforms,window_rect,available_memory_mb,input_idle_seconds
from .ui import Bubble


class Pet(QWidget):
    chat_requested=Signal()
    settings_requested=Signal()
    exit_requested=Signal()
    moved=Signal()

    def __init__(self,config,bridge):
        flags=Qt.WindowType.Tool|Qt.WindowType.FramelessWindowHint
        if config['topmost']:flags|=Qt.WindowType.WindowStaysOnTopHint
        super().__init__(None,flags)
        self.setWindowTitle('霜璃')
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMouseTracking(True)
        self.config=config;self.bridge=bridge
        self.pack=AssetPack(config['pack']);self.player=AnimationPlayer(self.pack)
        self.emotion=Emotion(config)
        self.behavior=CompanionBehavior();self.system_idle=0;self.last_idle_probe=0
        self.art=self.pack.load(self.pack.actions['idle'].loop[0])
        self.bubble=Bubble()
        self.live=None;self.renderer_error=''
        self.pose_active=False;self.mask_action=None;self.mask_blending=False
        self.last_render=0.0;self.last_render_action=None
        self.natural_started=None
        self.presented=QImage();self.presentation_started=None;self.mask_signature=None
        self.paused=False;self.chat_open=False;self.sleeping=False
        self.dock_reserve=0;self.dock_lift=0;self.dock_open=False
        self.pending_impact=0
        self.dragging=False;self.pressed=False;self.press_point=QPoint();self.offset=QPoint()
        self.samples=[];self.vx=self.vy=0.0;self.xpos=self.ypos=0.0
        self.attached=None;self.attached_rect=None;self.supports=[]
        self.last_support=0;self.last_tick=time.monotonic();self.roam_started=self.last_tick
        self.next_reminder=self.last_tick
        self.land_until=0;self.direction=1;self.hold_last=0
        self.single_timer=QTimer(self);self.single_timer.setSingleShot(True);self.single_timer.timeout.connect(self.single_click)
        self.hold_timer=QTimer(self);self.hold_timer.setSingleShot(True);self.hold_timer.timeout.connect(self.long_touch)
        self.timer=QTimer(self);self.timer.timeout.connect(self.safe_tick)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.tick_errors=0
        self.scaled_frames={};self.scaled_bytes=0;self.memory_pressure=False;self.last_memory=0
        self.apply_settings(initial=True)
        screens=QApplication.screens();screen=QApplication.primaryScreen().availableGeometry()
        self.xpos=float(config['x']) if isinstance(config['x'],(int,float)) else screen.right()-self.width()-32
        self.ypos=float(config['y']) if isinstance(config['y'],(int,float)) else screen.bottom()-self.height()-12
        self.clamp_position();self.place()
        self.show();click_through(self,config['click_through'])
        bridge.state_changed.connect(self.chat_state)

    def apply_settings(self,initial=False):
        self.scaled_frames.clear()
        self.scaled_bytes=0
        old_bottom=self.y()+self.height()
        size=max(140,min(500,round(245*self.config['scale'])))
        self.resize(size,round(size*1.08))
        self.setWindowOpacity(self.config['opacity'])
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint,self.config['topmost'])
        if not initial:
            self.ypos=old_bottom-self.height()
            self.show();click_through(self,self.config['click_through'])
        self.timer.start(round(1000/int(self.config['fps'])))
        if self.config['pack']!=self.pack.manifest.get('id','default'):
            try:
                self.pack=AssetPack(self.config['pack']);self.player=AnimationPlayer(self.pack)
                self.art=self.pack.load(self.pack.actions['idle'].loop[0])
            except Exception:
                logging.exception('Pet pack load failed');self.config['pack']='default'
        self.next_reminder=time.monotonic()+self.config['reminder_minutes']*60
        self.configure_renderer()
        self.update_mask()

    def configure_renderer(self):
        path=self.config['live2d_path'] or str(ROOT/'assets/live2d/shuangli-q/shuangli.model3.json')
        if self.live and (self.config['renderer']!='live2d' or str(self.live.path)!=path):
            self.live.shutdown();self.live.hide();self.live.deleteLater();self.live=None
        if self.config['renderer']=='live2d' and not self.live:
            try:
                from pathlib import Path
                if not Path(path).is_file():
                    self.renderer_error='指定形态的 Live2D 模型尚未导出，当前使用原图底稿。'
                    return
                from .live2d_view import Live2DView
                self.live=Live2DView(path,self)
                self.live.failed.connect(self.renderer_failed)
                self.live.setGeometry(self.rect())
                # Finish the one-off DLL/model load before revealing the pet; visible frames stay lightweight.
                self.live.initializeGL()
                self.live.hide()
            except Exception:
                logging.exception('Live2D unavailable')
                self.renderer_error='Live2D 无法启动，当前使用 2D 原画。'
        if self.live:self.live.reduce=self.config['reduced_motion']

    def renderer_failed(self,message):
        self.renderer_error=message
        if self.live:
            self.live.hide();self.live.shutdown();self.live.deleteLater();self.live=None
        self.update();self.bubble.say(message,self,6)

    def update_mask(self):
        signature=(id(self.pack),self.width(),self.height())
        if signature==self.mask_signature:return
        # A stable union prevents native layered-window region churn on each expression.
        paths=[self.pack.actions['idle'].loop[0]]
        paths.extend(action.loop[0] for action in self.pack.actions.values()
                     if action.effect=='pose' and action.loop)
        region=QRegion()
        for path in list(dict.fromkeys(paths))[:12]:
            scaled=self.pack.load(path).scaled(self.size(),Qt.AspectRatioMode.KeepAspectRatio,
                                               Qt.TransformationMode.SmoothTransformation)
            region|=QRegion(scaled.mask()).translated((self.width()-scaled.width())//2,
                                                     self.height()-scaled.height())
        pad=12
        horizontal=QRegion(region)
        for dx in range(-pad,pad+1,2):horizontal|=region.translated(dx,0)
        expanded=QRegion(horizontal)
        for dy in range(-pad,pad+1,2):expanded|=horizontal.translated(0,dy)
        self.setMask(expanded);self.mask_signature=signature

    def resizeEvent(self,event):
        if self.live:self.live.setGeometry(self.rect())
        super().resizeEvent(event)

    def paintEvent(self,_):
        now=time.monotonic()
        live_frame=self.live and not self.pose_active and not self.live.image.isNull()
        frame=self.live.image if live_frame else self.player.frame(now)
        ratio=min(1.5,self.devicePixelRatioF())
        canvas=QImage(round(self.width()*ratio),round(self.height()*ratio),QImage.Format.Format_ARGB32_Premultiplied)
        canvas.setDevicePixelRatio(ratio);canvas.fill(Qt.GlobalColor.transparent)
        composed=QPainter(canvas)
        composed.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        def draw(source,opacity):
            composed.setOpacity(opacity)
            if isinstance(source,QImage):
                composed.drawImage(QRectF(0,0,self.width(),self.height()),source)
            else:
                key=(source.cacheKey(),self.width(),self.height(),ratio)
                scaled=self.scaled_frames.get(key)
                if scaled is None:
                    scaled=source.scaled(round(self.width()*ratio),round(self.height()*ratio),
                                         Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)
                    scaled.setDevicePixelRatio(ratio)
                    cost=scaled.width()*scaled.height()*4
                    limit=(2 if self.memory_pressure else 8)*1024*1024
                    if self.scaled_bytes+cost>limit:self.scaled_frames.clear();self.scaled_bytes=0
                    self.scaled_frames[key]=scaled;self.scaled_bytes+=cost
                w,h=scaled.width()/ratio,scaled.height()/ratio
                composed.drawPixmap(QPointF((self.width()-w)/2,self.height()-h),scaled)
        alpha=self.player.blend(now) if self.player.previous is not None else 1.0
        if self.player.previous is not None and alpha<1:
            # Weighted premultiplied addition preserves opacity through a crossfade.
            draw(self.player.previous,1-alpha)
            composed.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        draw(frame,alpha);composed.end()
        self.presented=canvas
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        angle,lift,sx,sy=reaction_pose(self.player.action.name,now-self.player.started,
                                      self.config['reduced_motion'],self.player.action.duration or 2.4)
        painter.translate(self.width()/2,self.height());painter.translate(0,lift)
        painter.rotate(angle);painter.scale(sx,sy)
        painter.drawImage(QPointF(-self.width()/2,-self.height()),canvas)

    def nearest_screen(self,x=None,y=None):
        point=QPoint(round(self.xpos+self.width()/2 if x is None else x),round(self.ypos+self.height()/2 if y is None else y))
        screen=QApplication.screenAt(point)
        if screen:return screen
        def distance(s):
            r=s.availableGeometry();dx=max(r.left()-point.x(),0,point.x()-r.right());dy=max(r.top()-point.y(),0,point.y()-r.bottom());return dx*dx+dy*dy
        return min(QApplication.screens(),key=distance)

    def clamp_position(self):
        area=self.nearest_screen().availableGeometry()
        minx,maxx=area.left(),max(area.left(),area.right()-self.width()+1)
        miny,maxy=area.top(),max(area.top(),area.bottom()-self.height()+1-self.dock_reserve)
        if self.xpos<minx:
            self.xpos=minx;self.vx=abs(self.vx)*.4;self.direction=1;self.edge_reaction()
        if self.xpos>maxx:
            self.xpos=maxx;self.vx=-abs(self.vx)*.4;self.direction=-1;self.edge_reaction()
        if self.ypos<miny:self.ypos=miny;self.vy=abs(self.vy)*.35
        if self.ypos>=maxy:
            impact=self.vy
            self.ypos=maxy
            self.vy=-impact*.25 if impact>180 else 0
            if impact>100:self.landing(impact)
        return maxy

    def edge_reaction(self):
        if self.dragging or self.paused or self.chat_open or self.sleeping or not self.config['spontaneous_actions']:return
        now=time.monotonic()
        if self.behavior.reaction('edge_peek',now,25):self.player.play('edge_peek')

    def place(self):
        target=QPoint(round(self.xpos),round(self.ypos))
        if target==self.pos():return
        self.move(target)
        if self.bubble.isVisible():self.bubble.reposition(self)
        self.moved.emit()

    def safe_tick(self):
        try:self.tick();self.tick_errors=0
        except Exception:
            self.tick_errors+=1;logging.exception('Desktop frame failed')
            if self.tick_errors>=3:
                self.paused=True;self.vx=self.vy=0;self.attached=None
                self.timer.setInterval(500)
                self.bubble.say('桌面变化有点快，霜璃先安静待着。',self,5)

    def tick(self):
        now=time.monotonic();dt=min(.25,max(0,now-self.last_tick));self.last_tick=now
        if not self.isVisible():
            if self.timer.interval()!=500:self.timer.setInterval(500)
            return
        fps=int(self.config['fps'])
        if now-self.last_memory>3:
            self.last_memory=now;free=available_memory_mb()
            if free<1600:
                if not self.memory_pressure:
                    self.scaled_frames.clear();self.scaled_bytes=0
                self.memory_pressure=True
            elif free>1900:self.memory_pressure=False
            self.pack.trim(self.memory_pressure)
        if now-self.last_idle_probe>=1:
            self.last_idle_probe=now;idle=input_idle_seconds()
            self.system_idle=idle if idle is not None else now-self.emotion.last
        in_motion=self.dragging or abs(self.vx)>1 or abs(self.vy)>1
        if in_motion:fps=max(fps,60)
        elif self.player.action.name=='sleep' or self.paused:fps=min(fps,10)
        interval=round(1000/fps)
        if self.timer.interval()!=interval:self.timer.setInterval(interval)
        needs_platforms=self.dragging or self.vy>0 or self.attached is not None
        if self.config['window_standing'] and needs_platforms and now-self.last_support>1.5:
            self.last_support=now
            self.supports=platforms(os.getpid())
        if not self.dragging and not self.paused and not self.chat_open:
            if self.attached:
                rect=window_rect(self.attached,os.getpid())
                if rect and self.attached_rect:
                    dx=rect.x()-self.attached_rect.x();dy=rect.y()-self.attached_rect.y()
                    if abs(dx)<800 and abs(dy)<600:
                        self.xpos+=dx;self.ypos+=dy;self.attached_rect=rect
                        if self.xpos+self.width()/2<rect.left() or self.xpos+self.width()/2>rect.right():self.attached=None
                    else:self.attached=None
                else:self.attached=None
            resting=self.dock_open or self.sleeping or self.player.action.effect=='pose' or (self.config['spontaneous_actions'] and self.behavior.rest!='idle')
            if self.config['mode']=='follow' and not resting:
                cursor=QCursor.pos();distance=cursor.x()-(self.xpos+self.width()/2)
                target=max(-100,min(100,distance*.6)) if abs(distance)>self.width()*.7 else 0
                self.vx+=(target-self.vx)*(1-math.exp(-dt*4))
            elif self.config['mode']=='roam' and not resting:
                cycle=(now-self.roam_started)%30
                target=(42*self.direction) if 8<cycle<14 and now-self.emotion.last>10 else 0
                self.vx+=(target-self.vx)*(1-math.exp(-dt*3))
                if 14<cycle<14+dt:self.direction*=-1
            else:self.vx*=math.exp(-dt*4)
            old_foot=self.ypos+self.height()
            self.xpos+=self.vx*dt
            if not self.attached and self.config['gravity']:
                self.ypos+=self.vy*dt+.5*1050*dt*dt;self.vy+=1050*dt
                new_foot=self.ypos+self.height()
                if self.config['window_standing'] and self.vy>0:
                    for hwnd,rect in self.supports:
                        center=self.xpos+self.width()/2
                        if rect.left()+25<center<rect.right()-25 and old_foot<=rect.top()+3<=new_foot:
                            if rect.top()<self.nearest_screen().availableGeometry().top()+self.height():continue
                            self.ypos=rect.top()-self.height();self.attached=hwnd;self.attached_rect=rect;self.landing(self.vy);self.vy=0;break
            if self.attached:self.vy=0
            self.clamp_position();self.place()
        busy=self.bridge.state in (ChatState.SENDING,ChatState.GENERATING)
        moving=abs(self.vx)>12 or abs(self.vy)>60
        airborne=self.config['gravity'] and not self.attached and self.ypos+self.height()<self.nearest_screen().availableGeometry().bottom()-self.dock_reserve-3
        cursor=QCursor.pos()
        if self.pending_impact and not airborne and not moving and not self.dragging:
            if self.config['spontaneous_actions']:self.behavior.queue('meme_dizzy',now,.5)
            self.pending_impact=0
        if self.paused or self.chat_open or self.dragging or busy or airborne:
            self.behavior.interrupted()
        old_rest=self.behavior.rest
        reaction=self.behavior.observe(now,self.system_idle,(cursor.x(),cursor.y()),
            (self.xpos,self.ypos,self.width(),self.height()),
            blocked=self.paused or self.chat_open or self.pressed or self.dragging or busy or airborne,
            enabled=self.config['spontaneous_actions'],quiet=self.config['quiet'],moving=moving,
            explicit_sleep=self.sleeping,can_pet=not self.config['click_through'],mood=self.emotion.mood,
            reaction_busy=self.player.until>now)
        base='sleep' if self.sleeping else self.behavior.rest if self.config['spontaneous_actions'] else 'idle'
        if self.dragging:base='drag'
        elif airborne and self.vy>90:base='fall'
        elif busy:base='working'
        elif moving and base not in ('sleep','drowsy','sit'):base='walk'
        if self.chat_open and not self.sleeping:base='idle'
        interrupted=self.dragging or moving or busy or self.chat_open or airborne
        returned=old_rest!='idle' and self.behavior.rest=='idle' and not self.sleeping
        if ((self.player.action.effect=='pose' and (interrupted or returned) or
                self.natural_started==self.player.started and interrupted) and
                (self.player.action.name!=base or self.player.until>now)):
            self.player.play(base,0,True)
            self.behavior.interrupted()
            if interrupted:reaction=None
            if returned:
                if not reaction:self.behavior.queue('perk_up',now,1)
                self.behavior.next_reaction=min(self.behavior.next_reaction,now+1)
        self.player.set_base(base);self.player.tick(now)
        if reaction:
            if reaction=='pat':
                self.emotion.mood=min(1,self.emotion.mood+.025);self.emotion.last=now
            fallback={'wake_up':'happy','notice':'curious','pat':'happy','content':'happy',
                      'yawn':'stretch','look_around':'curious','blink_slow':'idle'}
            name=reaction if reaction in self.pack.actions else fallback.get(reaction,'idle')
            duration=self.behavior.random.uniform(25,40) if reaction=='sit' else self.pack.actions[name].duration
            if self.player.play(name,duration):
                self.natural_started=self.player.started
                self.behavior.performed(name,now,duration)
        pose=self.player.action.effect=='pose'
        if self.presentation_started!=self.player.started:
            same_art=(self.pose_active==pose and not pose and self.live is not None)
            self.player.previous=None if same_art or self.presented.isNull() else self.presented.copy()
            self.presentation_started=self.player.started
        self.pose_active=pose
        if self.live:
            self.live.set_action(self.player.action.name,self.player.started);self.live.mood=self.emotion.mood
            self.live.memory_pressure=self.memory_pressure
            self.live.bridge_state=self.bridge.state.value
            if pose:self.update()
            elif not self.paused:
                render_key=(self.player.action.name,self.player.started)
                changed=render_key!=self.last_render_action
                # Movement uses the existing transparent frame; avoid a synchronous GL readback at every move.
                motion_frame=self.dragging or airborne or abs(self.vx)>12
                due=not motion_frame and now-self.last_render>=1/max(10,int(self.config['fps']))
                if changed or due or self.live.image.isNull():
                    self.live.advance_frame();self.last_render=now;self.last_render_action=render_key
        else:self.update()
        if self.live and not pose:self.update()
        if self.config['reminder_minutes'] and now>=self.next_reminder:
            self.next_reminder=now+self.config['reminder_minutes']*60
            if not self.config['quiet']:self.bubble.say('主人，眼睛和肩膀也想休息一小会儿。',self,7)

    def landing(self,impact):
        if self.land_until>time.monotonic():return
        self.land_until=time.monotonic()+.24
        if impact>650:
            self.pending_impact=max(impact,self.pending_impact)
            self.player.play('hurt',.5,True)
        else:self.player.play('land',.45,True)
        if self.config['spontaneous_actions'] and impact<=650:self.behavior.landed(time.monotonic())

    def chat_state(self,state,detail):
        if state in (ChatState.SENDING.value,ChatState.GENERATING.value) and self.player.action.effect=='pose':
            self.player.play('working',0,True)
        elif state==ChatState.COMPLETED.value:self.player.play('happy',1.6)
        elif state==ChatState.FAILED.value:self.player.play('hurt',1.8)
        # Only status is animated. No local line impersonates a model response.

    def hit_region(self,position):
        x=position.x()/self.width();y=position.y()/self.height()
        for region in self.pack.regions:
            a,b,c,d=region['rect']
            if a<=x<=c and b<=y<=d:return region['name']
        return 'body'

    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.RightButton:self.menu().exec(event.globalPosition().toPoint());return
        if event.button()!=Qt.MouseButton.LeftButton:return
        self.pressed=True;self.dragging=False;self.press_point=event.globalPosition().toPoint()
        self.offset=self.press_point-self.pos();self.press_local=event.position().toPoint()
        self.samples=[(time.monotonic(),self.xpos,self.ypos)]
        self.hold_timer.start(600)

    def mouseMoveEvent(self,event):
        if not self.pressed:return
        point=event.globalPosition().toPoint()
        if not self.dragging and (point-self.press_point).manhattanLength()<QApplication.startDragDistance():return
        if not self.dragging:
            self.hold_timer.stop();self.single_timer.stop();self.attached=None;self.vx=self.vy=0
            self.player.play('drag',0,True)
        self.dragging=True
        self.xpos=point.x()-self.offset.x();self.ypos=point.y()-self.offset.y()
        self.samples.append((time.monotonic(),self.xpos,self.ypos));self.samples=self.samples[-8:]
        self.place()

    def mouseReleaseEvent(self,event):
        if event.button()!=Qt.MouseButton.LeftButton or not self.pressed:return
        self.hold_timer.stop();self.pressed=False
        if self.dragging:
            self.dragging=False;now=time.monotonic();self.emotion.last=now
            self.behavior.released(now)
            recent=[s for s in self.samples if now-s[0]<.14]
            if len(recent)>1 and now-recent[-1][0]<.08:
                elapsed=max(.02,recent[-1][0]-recent[0][0])
                self.vx=max(-1000,min(1000,(recent[-1][1]-recent[0][1])/elapsed))
                self.vy=max(-1100,min(1100,(recent[-1][2]-recent[0][2])/elapsed))
            else:self.vx=self.vy=0
            airborne=self.config['gravity'] and self.ypos+self.height()<self.nearest_screen().availableGeometry().bottom()-4
            self.player.play('fall' if airborne else 'land',0 if airborne else .4,True)
            if self.config['mode']=='fixed' and not self.config['gravity']:self.vx=self.vy=0
            self.clamp_position();self.place()
        elif time.monotonic()-self.hold_last>.5:
            self.single_timer.start(QApplication.doubleClickInterval())

    def mouseDoubleClickEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:
            self.single_timer.stop();self.hold_timer.stop();self.pressed=False
            self.wake();self.touch(self.hit_region(event.position().toPoint()))

    def single_click(self):
        self.wake();self.touch(self.hit_region(self.press_local))

    def long_touch(self):
        if self.pressed and not self.dragging:
            self.hold_last=time.monotonic();self.wake();self.touch('head')

    def touch(self,region):
        self.behavior.interrupted()
        action,line=self.emotion.touch(region)
        if action=='hurt' and 'meme_pout' in self.pack.actions:action='meme_pout'
        elif action!='hurt':
            specific={'head':'meme_smug' if self.emotion.mood>.65 else 'pat','cheek':'shy','horn':'meme_shock','wing':'wing_adjust','tail':'tail_flick'}
            candidate=specific.get(region,action)
            if candidate in self.pack.actions:action=candidate
        duration=self.pack.actions[action].duration or 1.7
        self.player.play(action,duration,True)
        self.behavior.performed(action,time.monotonic(),duration)
        self.bubble.say(line,self)

    def wheelEvent(self,event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.config['scale']=max(.5,min(2.5,self.config['scale']+(.1 if event.angleDelta().y()>0 else -.1)))
            self.apply_settings();self.config.save()

    def wake(self):
        self.sleeping=False;self.emotion.last=time.monotonic();self.system_idle=0
        self.behavior.rest='idle';self.player.play('idle',0,True)

    def set_mode(self,mode):
        self.config['mode']=mode;self.vx=self.vy=0;self.wake();self.config.save()

    def recover(self):
        self.config['click_through']=False;self.paused=False
        self.show();click_through(self,False)
        self.clamp_position();self.place();self.raise_()

    def menu(self):
        menu=QMenu();menu.setStyleSheet('QMenu{background:#faf6ff;color:#6d5287;border:1px solid #d7c2eb;padding:8px;}QMenu::item{padding:8px 24px;}QMenu::item:selected{background:#e7d7f6;border-radius:6px;}')
        menu.addAction('和霜璃说话',self.chat_requested.emit)
        modes=menu.addMenu('陪伴方式')
        for key,label in [('fixed','待在这里'),('follow','跟随鼠标'),('roam','自由漫游')]:
            action=modes.addAction(label);action.setCheckable(True);action.setChecked(self.config['mode']==key);action.triggered.connect(lambda checked=False,k=key:self.set_mode(k))
        menu.addAction('暂停动作' if not self.paused else '继续动作',self.toggle_pause)
        menu.addSeparator();menu.addAction('小小的设置',self.settings_requested.emit)
        menu.addAction('隐藏',self.hide_pet)
        menu.addAction('鼠标穿透',self.toggle_through)
        plugins=[cmd for cmd in getattr(self,'plugin_commands',[]) if cmd.get('kind') not in ('animation','local_bubble')]
        if plugins:
            extension=menu.addMenu('小工具')
            for cmd in plugins:extension.addAction(str(cmd.get('label','工具'))[:40],lambda checked=False,c=cmd:self.run_plugin(c))
        menu.addSeparator();menu.addAction('退出',self.exit_requested.emit)
        return menu

    def toggle_pause(self):self.paused=not self.paused
    def hide_pet(self):self.hide();self.bubble.hide()
    def toggle_through(self):
        self.config['click_through']=not self.config['click_through'];click_through(self,self.config['click_through']);self.config.save()
    def run_plugin(self,cmd):
        kind=cmd.get('kind')
        if kind=='animation':self.player.play(cmd.get('action','idle'),float(cmd.get('seconds',2)))
        elif kind=='local_bubble':self.bubble.say(str(cmd.get('text',''))[:200],self)
        elif kind=='chat_entry':self.bridge.open_conversation()
        elif kind=='reminder':
            self.config['reminder_minutes']=max(0,min(240,int(cmd.get('minutes',0))));self.next_reminder=time.monotonic()+self.config['reminder_minutes']*60
    def persist(self):
        self.config['x']=round(self.xpos);self.config['y']=round(self.ypos+self.dock_lift)
        self.config['mood']=self.emotion.mood;self.config['touch_count']=self.emotion.count;self.config.save()
    def shutdown(self):
        self.timer.stop();self.bubble.close()
        if self.live:self.live.shutdown()
        self.persist()


from .bridge import ChatState
