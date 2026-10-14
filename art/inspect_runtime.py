"""Short-lived inspection of the actual Pet widget and renderer, without changing saved settings."""
import sys,time,json,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from PySide6.QtCore import QTimer,Qt
from PySide6.QtWidgets import QApplication
from shuangli.config import Config
from shuangli.bridge import DesktopConversationBridge
from shuangli.pet import Pet
app=QApplication([])
config=Config();config.values.update(renderer='live2d',live2d_path=str(ROOT/'assets/live2d/shuangli-q-clean/shuangli-layered-alpha.model3.json'),x=600,y=250,
    gravity=False,window_standing=False,mode='fixed',fps=30)
config.save=lambda:None
bridge=DesktopConversationBridge(config)
pet=Pet(config,bridge)
pet.setWindowFlag(Qt.WindowType.Tool,False);pet.setWindowFlag(Qt.WindowType.Window,True)
pet.setWindowTitle('霜璃 · 实际渲染检查');pet.show()
destination=ROOT/'art/runtime-captures';destination.mkdir(exist_ok=True)
label=sys.argv[1] if len(sys.argv)>1 else 'before'
times=[]
original=pet.live.advance_frame
def measured():
    start=time.perf_counter();original();times.append((time.perf_counter()-start)*1000)
pet.live.advance_frame=measured
def capture():
    pet.grab().save(str(destination/f'pet-{label}.png'))
    if pet.live:pet.live.image.save(str(destination/f'frame-{label}.png'))
    sorted_times=sorted(times[5:])
    (destination/f'timing-{label}.json').write_text(json.dumps({'frames':len(times),
       'median_ms':sorted_times[len(sorted_times)//2] if sorted_times else None,
       'max_ms':max(sorted_times) if sorted_times else None,'last_frame':pet.live.frame_cost}),encoding='utf-8')
QTimer.singleShot(10000,capture)
def closed_capture():
    pet.grab().save(str(destination/f'pet-{label}-closed.png'))
QTimer.singleShot(12000,lambda:setattr(pet,'sleeping',True))
QTimer.singleShot(14000,closed_capture)
QTimer.singleShot(60000,app.quit)
app.aboutToQuit.connect(pet.shutdown)
app.exec()
