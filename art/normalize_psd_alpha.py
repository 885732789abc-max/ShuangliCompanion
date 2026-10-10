"""Normalize PSD layer transparency for exporters that do not apply Photoshop user masks.

This is a lossless format conversion of existing layer pixels, not new artwork.
The original PSD and its masks remain untouched.
"""
from pathlib import Path
from psd_tools import PSDImage
from psd_tools.api.layers import PixelLayer
root=Path(__file__).resolve().parents[1]
folder=root/'art/shuangli-q-v1'
source=PSDImage.open(folder/'shuangli-layered-trimmed.psd')
normalized=PSDImage.new('RGBA',source.size)
for layer in source:
    pixels=layer.composite(force=True,alpha=0)
    PixelLayer.frompil(pixels,normalized,name=layer.name,top=layer.top,left=layer.left)
normalized.save(folder/'shuangli-layered-alpha.psd')
print('Saved PSD with alpha in channel -1; user masks baked into a preserved copy.')
print('First layer alpha:',normalized[0].topil().getchannel('A').getextrema())
