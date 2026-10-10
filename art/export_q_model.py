from make_q_layers import editor,unwrap,state,operation,save,out,ROOT
import json

operation('project_import_cmo3',{'path':str(ROOT/'assets/live2d/shuangli-q/shuangli-layered-trimmed.cmo3'),
    'mode':'new','discard_unsaved':True})
objects=unwrap(editor.call('workspace_inspect',{'request':{'scope':'objects','limit':64}}))
(out/'objects.json').write_text(json.dumps(objects,ensure_ascii=False,indent=2),encoding='utf-8')
rows=objects['items']
while objects.get('nextOffset') is not None:
    objects=unwrap(editor.call('workspace_inspect',{'request':{'scope':'objects','limit':64,'offset':objects['nextOffset']}}))
    rows.extend(objects['items'])
for part,param,pivot in [('tail tail','ParamTail',[.55,.08]),
                        ('wings wing-l','ParamWingL',[.8,.35]),
                        ('wings wing-r','ParamWingR',[.08,.35])]:
    mesh=next(r['target'] for r in rows if r.get('name')==part and r['target'].startswith('mesh:'))
    shapes=[]
    for value in (-30,30):
        deform={'type':'rotate','degrees':value/5,'pivot':pivot}
        if param=='ParamTail':deform={'type':'arc','degrees':value/5,'root':pivot,'tip':[.18,.92],'root_pin':.25}
        shapes.append({'target':mesh,'value':value,'operations':[deform]})
    unwrap(editor.call('author_axis',{'request':{'state':state(),
        'parameter':{'id':param,'min':-30,'max':30,'default':0},'shapes':shapes},'wait_ms':20000}))
    save('shuangli-bound-'+param+'.psd2live')
save('shuangli.psd2live')
destination=ROOT/'assets/live2d/shuangli-q'
destination.mkdir(parents=True,exist_ok=True)
operation('project_export_model',{'output_directory':str(destination)})
print('Cubism model family exported.',flush=True)
