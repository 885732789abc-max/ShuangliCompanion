"""Produce a clean neutral authoring preview in the professional model editor."""
import base64
from make_q_layers import editor,unwrap,state,operation,out,ROOT

operation('project_import_cmo3',{'path':str(ROOT/'assets/live2d/shuangli-q/shuangli-layered-trimmed.cmo3'),
    'mode':'new','discard_unsaved':True})
result=editor.call('workspace_call',{'operation':'view_render_model','request':{
    'viewport':{'mode':'canvas_rect','left':0,'top':0,'width':830,'height':1007},
    'parameters':{},'target_long_edge':1007,'background':'transparent'}})
data=unwrap(result)
def find_image(value):
    if isinstance(value,dict):
        if value.get('type')=='image' and value.get('data'):return value['data']
        for key in ('png_base64','image_base64','base64','png'):
            if isinstance(value.get(key),str):return value[key]
        for entry in value.values():
            found=find_image(entry)
            if found:return found
    elif isinstance(value,list):
        for entry in value:
            found=find_image(entry)
            if found:return found
    return None
encoded=find_image(result)
if not encoded:
    print('Preview metadata keys:',list(data),flush=True)
else:
    (out/'live2d-neutral-preview.png').write_bytes(base64.b64decode(encoded))
    print('Neutral model preview saved.',flush=True)
