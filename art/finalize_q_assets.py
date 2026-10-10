import json
from pathlib import Path
root=Path(__file__).resolve().parents[1]
folder=root/'assets/live2d/shuangli-q'
name='shuangli-layered-trimmed'
model=json.loads((folder/f'{name}.model3.json').read_text(encoding='utf-8'))
model['FileReferences']['Motions']={group:[{'File':f'{name}.{action}.motion3.json'}]
    for group,action in [('Idle','idle'),('Blink','blink'),('Nod','nod'),('Shake','shake')]}
model['Groups']=[{'Target':'Parameter','Name':'EyeBlink','Ids':['ParamEyeLOpen','ParamEyeROpen']},
                 {'Target':'Parameter','Name':'LipSync','Ids':['ParamMouthOpenY']}]
(folder/'shuangli.model3.json').write_text(json.dumps(model,ensure_ascii=False,indent=2),encoding='utf-8')
print('Runtime model entry saved; exported file references preserved.')
