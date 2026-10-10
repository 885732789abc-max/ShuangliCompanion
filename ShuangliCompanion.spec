from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files

root=Path(SPECPATH)
pet_data=[(str(root/'assets/approved-q'),'assets/approved-q'),
          (str(root/'assets/poses'),'assets/poses'),
          (str(root/'assets/default-pack.json'),'assets'),
          (str(root/'assets/shuangli.ico'),'assets'),
          (str(root/'art/shuangli-q-v1/shuangli-exact-cutout.png'),'art/shuangli-q-v1')]
model_dir=root/'assets/live2d/shuangli-q'
if model_dir.exists():
    pet_data.append((str(model_dir/'shuangli.model3.json'),'assets/live2d/shuangli-q'))
    for file in model_dir.glob('shuangli-layered-alpha.*'):
        target='assets/live2d/shuangli-q'+('/'+file.name if file.is_dir() else '')
        pet_data.append((str(file),target))
    for name in ('face-backing.png','neutral-backing.png','idle-rig.json'):
        if (model_dir/name).is_file():
            pet_data.append((str(model_dir/name),'assets/live2d/shuangli-q'))
a=Analysis([str(root/'run.py')],pathex=[str(root/'src')],
    binaries=[],datas=pet_data+collect_data_files('live2d'),
    hiddenimports=['live2d','live2d._live2d','OpenGL.GL'],
    hookspath=[],runtime_hooks=[],excludes=['PySide6.QtWebEngineWidgets','PySide6.QtWebEngineCore','PySide6.QtMultimedia','PySide6.QtQml','tkinter'],
    noarchive=False)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='ShuangliCompanion',
    debug=False,bootloader_ignore_signals=False,strip=False,upx=False,console=False,
    icon=str(root/'assets/shuangli.ico'))
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='ShuangliCompanion')
