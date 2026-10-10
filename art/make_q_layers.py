"""Author visible original pixels using the PSD2Live editor's own paint/split operations."""
from pathlib import Path
import json
from authoring_client import Editor, ROOT

editor=Editor()
out=ROOT/'art/shuangli-q-v1'
plan=json.loads((out/'split-plan.json').read_text(encoding='utf-8'))

def unwrap(result):
    value=result.get('structuredContent')
    if value is None:
        value=json.loads(next(c['text'] for c in result['content'] if c.get('type')=='text'))
    if not value.get('ok'): raise RuntimeError(value)
    data=value['data']
    while 'terminal' in data:
        if data['terminal']:
            if data['status']!='completed': raise RuntimeError(data)
            return data['result']
        data=unwrap(editor.call('job',{'op':'wait','request':{'id':data['id'],'timeout_ms':30000}}))
    return data

def state():
    return unwrap(editor.call('workspace_inspect',{'request':{'scope':'project'}}))['state']

def operation(name,request):
    request={'state':state(),**request}
    value=unwrap(editor.call('workspace_call',{'operation':name,'request':request,'wait_ms':20000}))
    print(name, value.get('state',''), flush=True)
    return value

def save(name):
    return unwrap(editor.call('project',{'op':'save_as','request':{'state':state(),'path':str(out/name)},'wait_ms':20000}))

if __name__=='__main__':
    base='artwork:53ee62e23191'
    for point in ([3,3],[731,482],[25,832],[355,965]):
        operation('source_paint_bucket',{'layer_id':base,'point':point,'color':[0,0,0,0],
                   'tolerance':3,'rebuild_mesh':True})
    save('shuangli-original-cutout.psd2live')
    operation('project_export_psd',{'path':str(out/'shuangli-original-cutout.psd'),'include_generated_layers':False})
    remainder=base
    ids={}
    for piece in plan['pieces']:
        next_id='remaining-'+piece['id']
        operation('source_split_polygon',{'layer_id':remainder,'polygon':piece['polygon'],
                  'names':[piece['id'],next_id],'piece_ids':[piece['id'],next_id]})
        ids[piece['id']]=piece
        remainder=next_id
    operation('layer_classify',{'layer_id':remainder,'role':'topwear'})
    head='head'
    for piece in plan['head_pieces']:
        next_id='head-after-'+piece['id']
        operation('source_split_polygon',{'layer_id':head,'polygon':piece['polygon'],
                  'names':[piece['id'],next_id],'piece_ids':[piece['id'],next_id]})
        ids[piece['id']]=piece
        head=next_id
    operation('layer_classify',{'layer_id':head,'role':'front_hair'})
    for ident,piece in ids.items():
        if ident=='head': continue
        operation('layer_classify',{'layer_id':ident,'role':piece['role'],'side':piece.get('side','center')})
    operation('settings_update',{'changes':{'headStrength':0.3,'bodyStrength':0.3,
                 'meshSpacing':32,'atlasSize':2048,'motionIdle':True,'motionBlink':False}})
    save('shuangli-visible-layers.psd2live')
    operation('project_export_psd',{'path':str(out/'shuangli-visible-layers.psd'),'include_generated_layers':False})
    (out/'authoring-stage.json').write_text(json.dumps({'stage':'visible original layers separated',
        'parts':list(ids),'remaining_work':['occlusion repaint','separate eye internals','facial expressions','pose motions','Cubism refinement'],
        'state':state()},indent=2),encoding='utf-8')
