from make_q_layers import editor, unwrap, state, operation, save, out, plan
from psd_tools import PSDImage

save('shuangli-split-stage1.psd2live')
operation('project_export_psd',{'path':str(out/'shuangli-split-stage1.psd'),'include_generated_layers':False})
unwrap(editor.call('project',{'op':'import_psd','request':{'state':state(),
    'path':str(out/'shuangli-split-stage1.psd'),'discard_unsaved':True},'wait_ms':20000}))
layers=unwrap(editor.call('workspace_inspect',{'request':{'scope':'layers'}}))['items']
head=next(l['id'] for l in layers if l['name']=='head')
for piece in plan['head_pieces']:
    next_id='head-after-'+piece['id']
    operation('source_split_polygon',{'layer_id':head,'polygon':piece['polygon'],
        'names':[piece['id'],next_id],'piece_ids':[piece['id'],next_id]})
    head=next_id
save('shuangli-visible-splits.psd2live')
operation('project_export_psd',{'path':str(out/'shuangli-visible-splits.psd'),'include_generated_layers':False})
p=PSDImage.open(out/'shuangli-visible-splits.psd')
roles={piece['id']:piece['role'].replace('_',' ') for piece in plan['pieces']+plan['head_pieces']}
for layer in p:
    ident=layer.name
    if ident.startswith('remaining-'): layer.name='topwear'
    elif ident.startswith('head-after-'): layer.name='front hair'
    else:
        name=roles.get(ident,'objects')
        if ident in ('horn-l','horn-r'): name='headwear '+ident
        else: name += ' '+ident
        layer.name=name
p.save(out/'shuangli-visible-layers.psd')
unwrap(editor.call('project',{'op':'import_psd','request':{'state':state(),
    'path':str(out/'shuangli-visible-layers.psd'),'discard_unsaved':True},'wait_ms':20000}))
save('shuangli-visible-layers.psd2live')
print('Visible layers saved; full eye anatomy and occlusion repaint still pending.',flush=True)
