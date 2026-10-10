"""Deploy the complete staged idle rig, retaining an untouched model copy."""
import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from PIL import Image

root = Path(__file__).resolve().parents[1]
stage = root / 'art/idle-model-stage'
target = root / 'assets/live2d/shuangli-q'
model = json.loads((stage / 'shuangli.model3.json').read_text(encoding='utf-8'))
rig = json.loads((stage / 'idle-rig.json').read_text(encoding='utf-8'))
refs = model['FileReferences']
required = [refs['Moc'], *refs['Textures'], refs['DisplayInfo'],
            'neutral-backing.png', 'face-backing.png', 'idle-rig.json']
if refs.get('Physics'): required.append(refs['Physics'])
required.extend(motion['File'] for group in refs.get('Motions', {}).values() for motion in group)
for name in required:
    file = (stage / name).resolve()
    if not file.is_relative_to(stage.resolve()) or not file.is_file():
        raise RuntimeError(f'Incomplete model family: {name}')
params = {row['Id'] for row in json.loads((stage / refs['DisplayInfo']).read_text(encoding='utf-8'))['Parameters']}
missing = set(rig['parameters']) - params
if missing: raise RuntimeError(f'Missing rig axes: {sorted(missing)}')
backup = root / 'art/model-backups' / datetime.now().strftime('%Y%m%d-%H%M%S')
shutil.copytree(target, backup)
for file in stage.rglob('*'):
    if not file.is_file(): continue
    destination = target / file.relative_to(stage)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + '.update')
    shutil.copy2(file, temporary)
    os.replace(temporary, destination)
manifest = root / 'assets/manifest.json'
data = json.loads(manifest.read_text(encoding='utf-8'))
items = {item['path']: item for item in data['assets']}
for file in stage.rglob('*'):
    if not file.is_file(): continue
    destination = target / file.relative_to(stage)
    key = destination.relative_to(root).as_posix()
    item = {'path': key, 'format': file.suffix[1:].upper(), 'bytes': file.stat().st_size,
            'original': 'art/shuangli-q-v1/shuangli-layered-alpha.psd',
            'reuse': 'Original alpha layers; root-pinned idle bindings',
            'action': 'idle, random wing/tail/hair gestures, eye expressions',
            'license': 'User-supplied character artwork; original preserved.'}
    if file.suffix.lower() == '.png':
        with Image.open(file) as image:
            item.update(width=image.width, height=image.height, alpha='A' in image.getbands())
    items[key] = item
data['assets'] = list(items.values())
temporary = manifest.with_suffix('.json.update')
temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
os.replace(temporary, manifest)
print('Idle rig deployed:', target, flush=True)
