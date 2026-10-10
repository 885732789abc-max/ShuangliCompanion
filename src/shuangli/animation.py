from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from collections import OrderedDict
from pathlib import Path

from PySide6.QtGui import QPixmap,QImageReader
from PySide6.QtCore import QSize,Qt

from .config import ROOT, DATA


@dataclass
class Action:
    name: str
    enter: list
    loop: list
    exit: list
    fps: float = 6
    priority: int = 0
    duration: float = 0
    effect: str = ''
    quality: str = 'existing frames'


class AssetPack:
    def __init__(self, name='default'):
        path = ROOT / 'assets/default-pack.json' if name == 'default' else DATA / 'packs' / name / 'pack.json'
        self.base = path.parent
        self.manifest = json.loads(path.read_text(encoding='utf-8'))
        self.cache = OrderedDict()
        self.cache_bytes = 0
        self.cache_limit = 16 * 1024 * 1024
        self.actions = {}
        for key, spec in self.manifest['actions'].items():
            phases = []
            for phase in ('enter', 'loop', 'exit'):
                values = spec.get(phase, [])
                phases.append(list(values))
            self.actions[key] = Action(key, *phases, **{k:spec[k] for k in ('fps','priority','duration','effect','quality') if k in spec})
        atlas = QPixmap(str(self.base / self.manifest['gaze_atlas'])) if self.manifest.get('gaze_atlas') else QPixmap()
        self.looks = [atlas.copy(i%8*192, (9+i//8)*208, 192,208) for i in range(16)] if not atlas.isNull() else []
        self.regions = self.manifest.get('hit_regions', [])

    def load(self, name):
        if name in self.cache:
            self.cache.move_to_end(name)
            return self.cache[name]
        if name not in self.cache:
            file = (self.base / name).resolve()
            if not file.is_relative_to(self.base.resolve()): raise ValueError('Pack path escapes pack folder')
            reader = QImageReader(str(file))
            size = reader.size()
            edge = 640 if name.startswith('poses/') else 1024
            if size.isValid() and max(size.width(),size.height()) > edge:
                reader.setScaledSize(size.scaled(QSize(edge,edge),Qt.AspectRatioMode.KeepAspectRatio))
            pix = QPixmap.fromImage(reader.read())
            if pix.isNull(): raise ValueError(f'Missing frame: {name}')
            cost = pix.width() * pix.height() * 4
            while self.cache and self.cache_bytes + cost > self.cache_limit:
                _, old = self.cache.popitem(last=False)
                self.cache_bytes -= old.width() * old.height() * 4
            self.cache[name] = pix
            self.cache_bytes += cost
        return self.cache[name]

    def trim(self, pressure=False):
        self.cache_limit = (4 if pressure else 16) * 1024 * 1024
        while len(self.cache) > 1 and self.cache_bytes > self.cache_limit:
            _, old = self.cache.popitem(last=False)
            self.cache_bytes -= old.width() * old.height() * 4


class AnimationPlayer:
    def __init__(self, pack):
        self.pack = pack
        self.base = 'idle'
        self.action = pack.actions['idle']
        self.started = time.monotonic()
        self.phase = 'enter' if self.action.enter else 'loop'
        self.phase_started = self.started
        self.previous = None
        self.transition = 0.18
        self.pending = None
        self.until = 0
        self.resume = []

    def play(self, name, duration=None, force=False):
        if name not in self.pack.actions: return False
        incoming = self.pack.actions[name]
        now = time.monotonic()
        if force:
            self.resume.clear();self.pending = None
        if incoming.name == self.action.name:
            if force:
                self.started = self.phase_started = now
                self.phase = 'enter' if incoming.enter else 'loop'
                length = incoming.duration if duration is None else duration
                self.until = now + length if length else 0
            return True
        if not force and incoming.priority < self.action.priority and self.until > now:
            return False
        if not force and self.action.exit:
            self.pending = (name, duration)
            self.phase = 'exit'; self.phase_started = now
            return True
        if not force and self.until > now and incoming.priority > self.action.priority:
            self.resume.append((self.action.name, self.until-now))
            self.resume = self.resume[-4:]
        self.previous = self.frame(now)
        self.action = incoming
        self.started = self.phase_started = now
        self.phase = 'enter' if incoming.enter else 'loop'
        length = incoming.duration if duration is None else duration
        self.until = now + length if length else 0
        return True

    def set_base(self, name):
        if name not in self.pack.actions: name = 'idle'
        self.base = name
        if not self.until and self.phase != 'exit' and self.action.name != name:self.play(name,0,force=True)

    def frame(self, now=None):
        now = now or time.monotonic()
        frames = getattr(self.action, self.phase) or self.action.loop
        if not frames:
            frames = self.pack.actions['idle'].loop
        if not frames:return QPixmap()
        index = int((now-self.phase_started)*self.action.fps)
        return self.pack.load(frames[index % len(frames)] if self.phase == 'loop' else frames[min(index,len(frames)-1)])

    def tick(self, now):
        frames = getattr(self.action, self.phase)
        if self.phase != 'loop' and (not frames or now-self.phase_started >= len(frames)/self.action.fps):
            if self.phase == 'exit':
                pending = self.pending; self.pending = None
                self.until = 0; self.resume.clear()
                self.action = self.pack.actions['idle']
                self.play(*(pending or (self.base, None)), force=True)
            else: self.phase = 'loop'; self.phase_started = now
        if self.until and now >= self.until:
            if self.action.exit and self.phase != 'exit':
                self.phase = 'exit'; self.phase_started = now; self.pending = (self.base,None)
                self.until = 0
            else:
                self.until = 0
                name, duration = self.resume.pop() if self.resume else (self.base, None)
                remaining = self.resume[:]
                self.play(name, duration, force=True)
                self.resume = remaining

    def blend(self, now):
        alpha = min(1, (now-self.started)/self.transition)
        if alpha >= 1:self.previous = None
        return alpha


class Emotion:
    def __init__(self, config):
        self.mood = float(config['mood'])
        self.touches = []
        self.last = time.monotonic()
        self.count = config['touch_count']
        self.sequence = 0

    def touch(self, region):
        now = time.monotonic()
        self.touches = [t for t in self.touches if now-t<4]
        self.touches.append(now); self.last = now; self.count += 1
        self.sequence += 1
        if len(self.touches) >= 5:
            self.mood = max(-1,self.mood-.22)
            return 'hurt', ['主人，霜璃有点晕啦。','轻一点……龙角也会痒的。'][self.sequence%2]
        self.mood = min(1,self.mood+.08)
        lines = {
            'head':['主人摸摸，霜璃就精神了。','再待一小会儿，好不好。'],
            'cheek':['唔……脸颊有点热。','霜璃在听主人说话。'],
            'horn':['角尖要轻轻碰呀。','被主人发现这对小角了。'],
            'wing':['小翅膀也想伸一伸。','霜璃把翅膀收好，陪着主人。'],
            'tail':['尾巴自己绕过来啦。','唔，主人别挠尾巴尖……'],
            'body':['霜璃在这里。','主人忙的时候，霜璃会乖乖陪着。']}
        return ('happy' if region in ('head','cheek') else 'curious'), lines.get(region,lines['body'])[self.sequence%2]

    def idle_action(self, now):
        idle = now-self.last
        if idle > 300: return 'sleep'
        if idle > 120: return 'sit'
        if idle > 50 and int(idle)%37 < 3: return 'stretch'
        return 'idle'
