"""Slice the generated transparent sheet into equal-scale, foot-aligned sprites."""
import json
import shutil
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'art/shuangli-memes/expressions-sheet-v1.png'
NAMES = ('meme_shock', 'meme_smug', 'meme_pout', 'meme_tears', 'meme_dizzy', 'meme_flop')

def main():
    archive = ROOT / 'art/shuangli-memes'
    archive.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SOURCE, archive / 'expressions-sheet-v1.png')
    folder = ROOT / 'assets/poses/shuangli-q/memes'
    folder.mkdir(parents=True, exist_ok=True)
    sheet = Image.open(SOURCE).convert('RGBA')
    width, height = sheet.size
    seam = round(height * .515625)
    paths = {}
    for index, name in enumerate(NAMES):
        column, row = index % 3, index // 3
        cell = sheet.crop((round(width*column/3), 0 if row == 0 else seam,
                           round(width*(column+1)/3), seam if row == 0 else height))
        bounds = cell.getchannel('A').getbbox()
        if bounds is None:raise ValueError(f'Empty sprite: {name}')
        sprite = cell.crop(bounds)
        scale = min(600/(width/3), 660/seam)
        sprite = sprite.resize((round(sprite.width*scale), round(sprite.height*scale)), Image.Resampling.LANCZOS)
        canvas = Image.new('RGBA', (640, 700))
        canvas.alpha_composite(sprite, ((640-sprite.width)//2, 688-sprite.height))
        file = folder / f'{name}-v1.png'
        canvas.save(file)
        paths[name] = file.relative_to(ROOT/'assets').as_posix()
    pack_path = ROOT/'assets/default-pack.json'
    pack = json.loads(pack_path.read_text(encoding='utf-8'))
    for name, duration in zip(NAMES, (2.8, 3.2, 2.8, 3.4, 3.8, 5.2)):
        pack['actions'][name] = dict(enter=[], loop=[paths[name]], exit=[], fps=1,
            priority=5 if name=='meme_dizzy' else 4, duration=duration, effect='pose',
            quality='Reference-preserving imagegen full-body comic pose; equal-scale transparent sprite')
    pack_path.write_text(json.dumps(pack,ensure_ascii=False,indent=2),encoding='utf-8')
    manifest_path=ROOT/'assets/manifest.json'
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    existing={item['path']:item for item in manifest['assets']}
    for name,path in paths.items():
        existing['assets/'+path]=dict(path='assets/'+path,format='PNG',width=640,height=700,
            alpha=True,alpha_range=[0,255],frames=1,action=name,reuse='natural event reaction',
            original='art/shuangli-memes/expressions-sheet-v1.png',
            reference='assets/references/shuangli-approved-q-v1.png',generator='built-in imagegen')
    manifest['assets']=list(existing.values())
    manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    (archive/'prompt.md').write_text('Reference: assets/references/shuangli-approved-q-v1.png\n'
        'Built-in imagegen, transparent 3 × 2 full-body sheet. Preserve chibi identity, costume, ornaments and 2D linework.\n'
        'Reading order: shocked lean back; smug hands on hips; puffed-cheek protest; tearful puppy eyes; seated dizzy spirals; exhausted face-down flop.\n'
        'No text or borders. Constant scale and foot alignment when slicing; preserve lying pose proportions.\n',encoding='utf-8')

if __name__=='__main__':main()
