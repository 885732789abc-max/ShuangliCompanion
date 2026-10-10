"""Record provenance and authoring stage; does not execute or test the pet."""
import json
from pathlib import Path
from PIL import Image

root=Path(__file__).resolve().parents[1]
manifest=root/'assets/manifest.json'
data=json.loads(manifest.read_text(encoding='utf-8'))
by_path={item['path']:item for item in data['assets']}
original='User-supplied reference artwork'
for file in [root/'assets/references/shuangli-approved-q-v1.png',
             *sorted((root/'art/shuangli-q-v1').glob('*')),
             *sorted((root/'assets/live2d/shuangli-q').rglob('*'))]:
    if not file.is_file() or file.suffix.lower() not in ('.png','.psd','.psd2live','.cmo3','.moc3','.json'):continue
    path=file.relative_to(root).as_posix()
    item={'path':path,'original':original,'format':file.suffix[1:].upper(),
          'bytes':file.stat().st_size,'license':'User-supplied character artwork; original preserved.',
          'reuse':'reference' if '/references/' in path else 'authoring source',
          'action':'neutral pose; full posture actions still in production'}
    if file.suffix.lower()=='.png':
        with Image.open(file) as img:
            item.update(width=img.width,height=img.height,alpha='A' in img.getbands())
            if item['alpha']:item['alpha_range']=list(img.getchannel('A').getextrema())
        if file.name=='shuangli-exact-cutout.png':item['reuse']='default fallback; original pixels edited in PSD2Live'
        if file.name=='cutout-candidate-v1.png':item['reuse']='archived imagegen candidate; not used by default'
    by_path[path]=item
for item in by_path.values():
    if '/legacy/' in item['path']: item['reuse']='archived prior user asset; rejected style, not packaged'
data['assets']=list(by_path.values())
data['active_reference']='assets/references/shuangli-approved-q-v1.png'
data['active_fallback']='assets/approved-q/shuangli-exact-cutout.png'
data['authoring_tool']='PSD2Live 3.1.1, official upstream portable distribution, local authenticated MCP'
manifest.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
print('Asset manifest updated.')
