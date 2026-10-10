"""Render authored idle key poses at desktop size using the actual compositor."""
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtGui import QPixmap, QSurfaceFormat
from shuangli.live2d_view import Live2DView

fmt = QSurfaceFormat()
fmt.setAlphaBufferSize(8)
fmt.setVersion(2, 1)
fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CompatibilityProfile)
QSurfaceFormat.setDefaultFormat(fmt)
app = QApplication([])
parent = QWidget()
parent.art = QPixmap(str(ROOT / 'assets/approved-q/shuangli-exact-cutout.png'))
parent.player = SimpleNamespace(action=SimpleNamespace(duration=0))
parent.config = {'spontaneous_actions': True, 'quiet': True}
parent.chat_open = False
view = Live2DView(ROOT / 'assets/live2d/shuangli-q/shuangli.model3.json', parent)
view.resize(245, 265)
folder = ROOT / 'art/idle-motion-preview'
folder.mkdir(exist_ok=True)
poses = {
    'neutral': {'ParamTail': 0, 'ParamWingL': 0, 'ParamWingR': 0,
                'ParamIdleAhoge': 0, 'ParamIdleHairL': 0, 'ParamIdleHairR': 0},
    'open': {'ParamTail': 25, 'ParamWingL': 27, 'ParamWingR': -27,
             'ParamIdleAhoge': 22, 'ParamIdleHairL': 20, 'ParamIdleHairR': -20},
    'return': {'ParamTail': -23, 'ParamWingL': -24, 'ParamWingR': 24,
               'ParamIdleAhoge': -22, 'ParamIdleHairL': -20, 'ParamIdleHairR': 20},
}
try:
    for name, values in poses.items():
        view.idle_motion.values = lambda *args, values=values, **kwargs: values
        view.smoothed.clear()
        view.advance_frame()
        if view.image.isNull(): raise RuntimeError('Model preview could not render')
        view.image.save(str(folder / (name + '.png')))
    print('Desktop-size idle poses rendered:', folder)
finally:
    view.shutdown()
