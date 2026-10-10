from pathlib import Path

root=Path(SPECPATH)
a=Analysis([str(root/'native_host.py')],pathex=[str(root/'src')],binaries=[],datas=[],
    hiddenimports=[],excludes=['PySide6','numpy','PIL','OpenGL','live2d'],noarchive=False)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,a.binaries,a.datas,name='ShuangliBridgeHost',debug=False,
    strip=False,upx=False,console=True,icon=str(root/'assets/shuangli.ico'))
