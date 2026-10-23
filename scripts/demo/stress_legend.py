"""Same von Mises colour mapping as the actual solver nodal field (MPa)."""
import colorsys,json
from pathlib import Path
try:
 from PySide import QtCore, QtGui, QtWidgets
except ImportError:
 from PySide6 import QtCore, QtGui, QtWidgets
MAX_MPA=1.3673728648580374

def legend(parent, maximum=None):
 if maximum is None:
  results=Path(__file__).resolve().parents[2]/'demo-out/stage3/replay-fem.json'
  maximum=json.loads(results.read_text())['result']['stress_MPa'] if results.exists() else MAX_MPA
 frame=QtWidgets.QFrame(parent);frame.setGeometry(1300,230,290,550)
 frame.setStyleSheet('background:#f0f2f3; color:#263d46; font:26px "DejaVu Sans";')
 def label(x,y,w,h,text):
  l=QtWidgets.QLabel(text,frame);l.setGeometry(x,y,w,h);l.show()
 label(8,0,280,42,'von Mises (MPa)')
 bar=QtWidgets.QLabel(frame);bar.setGeometry(25,65,42,360)
 pix=QtGui.QPixmap(42,360);p=QtGui.QPainter(pix)
 for y in range(360):
  rgb=colorsys.hsv_to_rgb(y/359*2/3,.85,.95)
  p.setPen(QtGui.QColor.fromRgbF(*rgb));p.drawLine(0,y,41,y)
 p.end();bar.setPixmap(pix);bar.show()
 for t in [0,.25,.5,.75,1]:label(85,int(48+(1-t)*359),190,34,'%.3f'%(maximum*t))
 label(8,460,280,40,'Undeformed jaw')
 return frame
