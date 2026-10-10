"""Declarative local plugins; importing a pack never executes its Python code."""
from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path

from .config import DATA


class PluginRegistry:
    def __init__(self):
        self.root=DATA/'plugins';self.root.mkdir(parents=True,exist_ok=True)
        self.commands=[]
        for file in self.root.glob('*/plugin.json'):
            try:
                data=json.loads(file.read_text(encoding='utf-8'))
                if data.get('version')!=1:continue
                for cmd in data.get('commands',[])[:20]:
                    if cmd.get('kind') in ('animation','local_bubble','chat_entry','reminder'):
                        self.commands.append(cmd)
            except (OSError,ValueError):pass


def import_pack(source):
    source=Path(source)
    dest=DATA/'packs'/source.stem
    if dest.exists():raise ValueError('已有同名皮肤，请先改名；霜璃不会覆盖原素材。')
    if source.is_dir():
        if not (source/'pack.json').exists():raise ValueError('皮肤目录需要 pack.json。')
        shutil.copytree(source,dest)
    elif source.suffix.lower()=='.zip':
        with zipfile.ZipFile(source) as z:
            total=0
            for info in z.infolist():
                target=(dest/info.filename).resolve()
                if not target.is_relative_to(dest.resolve()):raise ValueError('皮肤含有越界路径。')
                if info.external_attr>>16 & 0o170000 == 0o120000:raise ValueError('皮肤不能包含链接。')
                total+=info.file_size
                if total>200_000_000:raise ValueError('皮肤超过 200 MB。')
            dest.mkdir(parents=True)
            z.extractall(dest)
        if not (dest/'pack.json').exists():raise ValueError('压缩包根目录需要 pack.json。')
    else:raise ValueError('请选择皮肤目录或 ZIP。')
    return dest.name


class VoiceExtension:
    """Explicit extension boundary. No audio device is opened by the core."""
    enabled=False
    def start_recording(self): raise NotImplementedError('No voice provider installed')
    def speak(self,text): raise NotImplementedError('No voice provider installed')
