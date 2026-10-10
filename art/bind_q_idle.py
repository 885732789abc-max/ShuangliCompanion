"""Bind root-pinned idle parts on a copy of the alpha PSD and export a staged rig."""
import json
from psd_tools import PSDImage
from authoring_client import ROOT
from make_q_layers import editor, unwrap, state, operation

out = ROOT / 'art/shuangli-q-v1'
stage = ROOT / 'art/idle-model-stage'
stage.mkdir(exist_ok=True)
source = out / 'shuangli-layered-alpha.psd'
unwrap(editor.call('project', {'op': 'import_psd', 'request': {
    'state': state(), 'path': str(source), 'discard_unsaved': True}, 'wait_ms': 20000}))
operation('settings_update', {'changes': {'headStrength': 0.0, 'bodyStrength': 0.0,
    'meshSpacing': 32, 'atlasSize': 2048}})
rows = []
offset = 0
while True:
    page = unwrap(editor.call('workspace_inspect', {'request': {
        'scope': 'objects', 'limit': 64, 'offset': offset}}))
    rows.extend(page['items'])
    if page.get('nextOffset') is None: break
    offset = page['nextOffset']

# Roots lie inside the adjoining opaque region; pinned sections keep cut edges together.
parts = [
    ('tail tail', 'ParamTail', [.55, .08], [.18, .92], .35, 14),
    ('wings wing-l', 'ParamWingL', [.88, .30], [.08, .70], .40, 14),
    ('wings wing-r', 'ParamWingR', [.08, .30], [.92, .65], .40, 14),
    ('front hair ahoge', 'ParamIdleAhoge', [.55, .90], [.45, .05], .35, 22),
    ('back hair hair-l', 'ParamIdleHairL', [.55, .10], [.50, .95], .50, 9),
    ('back hair hair-r', 'ParamIdleHairR', [.40, .10], [.50, .95], .50, 9),
]
for name, ident, root, tip, pin, degrees in parts:
    target = next(row['target'] for row in rows
                  if row.get('name') == name and row['target'].startswith('mesh:'))
    shapes = [{'target': target, 'value': value, 'operations': [{
        'type': 'arc', 'degrees': degrees * value / 30,
        'root': root, 'tip': tip, 'root_pin': pin}]} for value in (-30, 30)]
    if ident in ('ParamWingL', 'ParamWingR'):
        for shape in shapes:
            shape['operations']=[{'type': 'rotate', 'degrees': degrees*shape['value']/30,
                                  'pivot': root}]
            shape['selection']={'center': tip, 'radius': .9, 'hardness': .55}
    unwrap(editor.call('author_axis', {'request': {'state': state(),
        'parameter': {'id': ident, 'min': -30, 'max': 30, 'default': 0},
        'shapes': shapes}, 'wait_ms': 20000}))
    print('Bound', ident, flush=True)
unwrap(editor.call('project', {'op': 'save_as', 'request': {
    'state': state(), 'path': str(out / 'shuangli-idle.psd2live')}, 'wait_ms': 20000}))
operation('project_export_model', {'output_directory': str(stage)})

# A stationary seam backing must not leave neutral copies behind moving parts.
psd = PSDImage.open(source)
moving = {part[0] for part in parts}
backing = psd.composite(force=True, alpha=0, layer_filter=lambda layer: layer.name not in moving)
backing.save(stage / 'neutral-backing.png')
model_path = stage / 'shuangli-layered-alpha.model3.json'
model = json.loads(model_path.read_text(encoding='utf-8'))
(stage / 'shuangli.model3.json').write_text(json.dumps(model, ensure_ascii=False, indent=2), encoding='utf-8')
(stage / 'idle-rig.json').write_text(json.dumps({'parameters': [part[1] for part in parts],
    'backing': 'neutral-backing.png', 'pinned_roots': True}, indent=2), encoding='utf-8')
import shutil
shutil.copy2(ROOT / 'assets/live2d/shuangli-q/face-backing.png', stage / 'face-backing.png')
print('Idle rig staged:', stage, flush=True)
