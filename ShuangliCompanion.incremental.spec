# Code-only rebuild for the unchanged dependency/runtime family.
import ast
import sys
from pathlib import Path
import shutil

root=Path(SPECPATH)
saved=ast.literal_eval((root/'build/ShuangliCompanion/Analysis-00.toc').read_text(encoding='utf-8'))
if saved[12]!=sys.version:
    raise RuntimeError('Cached analysis uses a different Python runtime; use a full build.')
pure=list(saved[14])
required={'random','collections','shuangli','shuangli.pet','shuangli.live2d_view'}
if not required.issubset({entry[0] for entry in pure + list(saved[-1])}):
    raise RuntimeError('Cached dependencies are incomplete; use a full build.')
for module in ('behavior',):
    pure=[entry for entry in pure if entry[0]!='shuangli.'+module]
    pure.append(('shuangli.'+module,str(root/'src/shuangli'/f'{module}.py'),'PYMODULE'))
for file in (root/'src/shuangli').glob('*.py'):
    compile(file.read_bytes(),str(file),'exec')
pyz=PYZ(pure)
exe=EXE(pyz,saved[13],[],exclude_binaries=True,name='ShuangliCompanion',
    debug=False,bootloader_ignore_signals=False,strip=False,upx=False,console=False,
    icon=str(root/'assets/shuangli.ico'))
stage=root/'build/package-stage/ShuangliCompanion'
stage.mkdir(parents=True,exist_ok=True)
shutil.copy2(exe.name,stage/'ShuangliCompanion.exe')
