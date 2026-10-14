from __future__ import annotations

import json
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[2]))
HOME = Path(sys.executable).parent if getattr(sys, 'frozen', False) else ROOT
DATA = HOME / 'data'
DEFAULTS = dict(scale=1.0, opacity=1.0, mode='fixed', topmost=True,
                click_through=False, gravity=True, window_standing=True,
                quiet=True, reminder_minutes=0, fps=30, x=None, y=None,
                conversation_url='',
                chat_target='desktop',
                browser='edge', startup=False, chat_on_single=False,
                hotkey_show='Ctrl+Alt+Shift+D', hotkey_chat='Ctrl+Alt+Shift+C',
                pack='default', mood=0.0, touch_count=0, todos=[],
                renderer='live2d', live2d_path='', reduced_motion=False,
                spontaneous_actions=True)


def atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    with temp.open('w', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, path)


class Config:
    def __init__(self):
        DATA.mkdir(parents=True, exist_ok=True)
        self.path = DATA / 'settings.json'
        self.values = DEFAULTS.copy()
        self.problem = ''
        prune_saved = False
        if self.path.exists():
            try:
                saved = json.loads(self.path.read_text(encoding='utf-8'))
                if not isinstance(saved, dict):
                    raise ValueError('settings must be an object')
                self.values.update({k: v for k, v in saved.items() if k in DEFAULTS})
                prune_saved = any(k not in DEFAULTS for k in saved)
            except (ValueError, OSError):
                self.problem = '设置暂时读不出来，霜璃先用默认设置陪主人。'
                logging.exception('Could not load settings')
        for k, low, high, default in [('scale', .5, 2.5, 1), ('opacity', .25, 1, 1),
                                      ('fps', 10, 60, 30), ('reminder_minutes', 0, 240, 0),
                                      ('mood', -1, 1, 0)]:
            try:
                self.values[k] = max(low, min(high, float(self.values[k])))
            except (ValueError, TypeError):
                self.values[k] = default
        if self.values['mode'] not in ('fixed', 'follow', 'roam'):
            self.values['mode'] = 'fixed'
        if self.values['chat_target'] not in ('desktop','browser'):self.values['chat_target']='desktop'
        for k in ('conversation_url', 'live2d_path', 'pack'):
            if not isinstance(self.values[k], str): self.values[k] = DEFAULTS[k]
        if not isinstance(self.values['todos'], list): self.values['todos'] = []
        if prune_saved:
            try: self.save()
            except OSError:
                self.problem = '设置清理暂时没能保存，霜璃稍后再试。'
                logging.exception('Could not prune obsolete settings')

    def __getitem__(self, key):
        return self.values[key]

    def __setitem__(self, key, value):
        self.values[key] = value

    def save(self):
        atomic_json(self.path, self.values)


def setup_logging():
    DATA.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(DATA / 'shuangli.log', maxBytes=512000,
                                  backupCount=3, encoding='utf-8')
    logging.basicConfig(level=logging.INFO, handlers=[handler],
                        format='%(asctime)s %(levelname)s %(message)s')
