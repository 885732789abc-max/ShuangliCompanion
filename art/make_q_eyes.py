"""Separate original eye pixels and paint hidden backing within the professional editor."""
from make_q_layers import editor, unwrap, state, operation, save, out
from psd_tools import PSDImage
import os

isolated=os.environ.get('SHUANGLI_ISOLATED_EYES')=='1'
if isolated:
    unwrap(editor.call('project',{'op':'create_artwork','request':{'state':state(),
        'width':830,'height':1007,'discard_unsaved':True,
        'layers':[{'path':str(out/'face-source.png'),'name':'face','role':'face','x':0,'y':15}]},'wait_ms':20000}))

operation('settings_update',{'changes':{'generateDeformers':False,'generatePhysics':False,
    'exportMotions':False,'atlasSize':1024,'meshSpacing':80}})
layers=unwrap(editor.call('workspace_inspect',{'request':{'scope':'layers'}}))['items']
face=next(l['id'] for l in layers if l['name'] in ('face face','face'))
eyes=[('r',[[215,401],[231,393],[257,394],[291,399],[315,407],[318,438],[307,459],[290,473],[267,475],[247,468],[232,451],[222,426]],
       [[252,413],[270,411],[295,414],[311,420],[309,444],[300,461],[283,472],[264,466],[253,445]],
       [[215,401],[231,393],[255,394],[290,399],[315,407],[313,419],[291,414],[271,411],[251,412],[233,420],[224,425]]),
      ('l',[[397,402],[418,396],[441,391],[466,393],[494,403],[490,425],[480,450],[463,466],[440,470],[421,462],[409,443],[405,419]],
       [[413,411],[436,410],[459,410],[472,416],[470,441],[460,460],[440,469],[421,462],[413,442]],
       [[397,402],[418,396],[441,391],[466,393],[494,403],[490,415],[472,414],[449,410],[432,410],[413,413],[405,419]])]
for side,polygon,iris,lash in eyes:
    rem='face-after-eye-'+side
    eye='eye-'+side
    operation('source_split_polygon',{'layer_id':face,'polygon':polygon,
        'names':[eye,rem],'piece_ids':[eye,rem]})
    # A bounded hidden backing avoids flood fill leaking through a one-pixel open edge.
    bounds=([215,394],[319,477]) if side=='r' else ([397,391],[495,471])
    operation('source_paint_shape',{'layer_id':rem,'from':bounds[0],'to':bounds[1],
        'shape':'rectangle','filled':True,'color':[254,250,246,255],'rebuild_mesh':False})
    face=rem
    eye_rem='eye-after-iris-'+side
    operation('source_split_polygon',{'layer_id':eye,'polygon':iris,
        'names':['irides-'+side,eye_rem],'piece_ids':['irides-'+side,eye_rem]})
    iris_bounds=([251,410],[314,475]) if side=='r' else ([412,409],[474,470])
    operation('source_paint_shape',{'layer_id':eye_rem,'from':iris_bounds[0],'to':iris_bounds[1],
        'shape':'ellipse','filled':True,'color':[249,250,248,255],'rebuild_mesh':False})
    operation('source_split_polygon',{'layer_id':eye_rem,'polygon':lash,
        'names':['eyelash-'+side,'eyewhite-'+side],'piece_ids':['eyelash-'+side,'eyewhite-'+side]})
    save('shuangli-eye-'+side+'-stage.psd2live')
    operation('project_export_psd',{'path':str(out/('shuangli-eye-'+side+'-stage.psd')),
        'include_generated_layers':False})
save('shuangli-eyes-split.psd2live')
operation('project_export_psd',{'path':str(out/'shuangli-eyes-split.psd'),'include_generated_layers':False})
p=PSDImage.open(out/'shuangli-eyes-split.psd')
for layer in p:
    if layer.name.startswith('face-after-'): layer.name='face'
    elif layer.name.startswith('irides-'): layer.name=layer.name.replace('irides-','irides ')
    elif layer.name.startswith('eyelash-'): layer.name=layer.name.replace('eyelash-','eyelash ')
    elif layer.name.startswith('eyewhite-'): layer.name=layer.name.replace('eyewhite-','eyewhite ')
if isolated:
    full=PSDImage.open(out/'shuangli-visible-layers.psd')
    old=next(l for l in full if l.name=='face face')
    at=list(full).index(old)
    full.remove(old)
    order=['face','eyewhite r','irides r','eyelash r','eyewhite l','irides l','eyelash l']
    for layer in sorted(list(p),key=lambda l:order.index(l.name)):
        p.remove(layer)
        full.insert(at,layer)
        at+=1
    full.save(out/'shuangli-layered.psd')
    print('Completed isolated eye batch; merged source PSD saved.',flush=True)
    raise SystemExit(0)
p.save(out/'shuangli-layered.psd')
unwrap(editor.call('project',{'op':'import_psd','request':{'state':state(),
    'path':str(out/'shuangli-layered.psd'),'discard_unsaved':True},'wait_ms':20000}))
operation('settings_update',{'changes':{'headStrength':0.28,'bodyStrength':0.25,
    'meshSpacing':48,'atlasSize':2048,'motionIdle':True,'motionBlink':True,
    'generateDeformers':True,'generatePhysics':True,'physicsEyeJelly':False,'exportMotions':True}})
save('shuangli.psd2live')
print('Authored original eye layers saved. Completed concealed iris arcs and expressions need further painting.',flush=True)
