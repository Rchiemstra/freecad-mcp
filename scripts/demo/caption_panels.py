"""Repaint scripted caption/readback panels; leave every CAD viewport pixel intact."""
import os,math
os.environ["QT_QPA_PLATFORM"]="offscreen"
from pathlib import Path
from PySide6 import QtCore,QtGui,QtWidgets
from stress_legend import legend
O=Path(__file__).resolve().parents[2]/'demo-out/stage3'
INITIAL=('freecad-mcp · real MCP tools','')
EASE='spreadsheet_set_cells · eased pose'
DISC='Scripted MCP replay · no live AI · waits trimmed · joined takes\nCAD capture · captions restored · forces estimated, not measured'
CARDS={
1:'MCP cell readback · Dims\n\nNominal berry: 30 × 35 mm\nStem: 3 mm\nHorn radius: 6 mm\nInput arm: 24 mm\nJaw arm: 15 mm\nCutter arm: 10.5 mm',
2:'MCP cell readback · Dims\n\nStall torque: 176 N mm\nWorking torque: 88 N mm\nIdeal clamp: 23.47 N\nIdeal cut: 33.52 N\n\nNeed: 10 N grip / 15 N cut',
4:'MCP clearance readback\n\n15 mm nominal spacing\nRetained minimum: 4.073 mm\n\nSix neighbouring objects\nEight retained poses\n24 path samples\n\nSampled common: 0 mm³',
5:'MCP narrow-cluster readback\n\n10 mm nominal spacing\nOriginal common volumes:\nFruit: 583.615 / 583.602 mm³\nStem: 3.195 mm³\n\nRetained fix:\nMinimum pose gap: 0.693 mm\nSampled common: 0 mm³'}
CUES={
1:[INITIAL,('spreadsheet_get_cells','The native checkpoint retains the spreadsheet, sketches and expressions.'),('spreadsheet_set_cells + recompute_document · native parts rebuilt','The same Stage 2a geometry is regenerated; the reveal is presentation.'),('Stem first','Two drives: one holds the stem, the other moves a replaceable blade.')],
2:[INITIAL,('spreadsheet_get_cells · force formulas','Torque is derated by 2. The linkage geometry gives the pad force.'),('Full-stroke minima: clamp 23.14 N · cut 33.42 N','Stage 2a: 0.1° samples with transmission correction; 2.31× / 2.23× targets.'),('Forces from datasheets + FEM, not measured','Stem strength, friction and real servo performance still need bench tests.')],
4:[INITIAL,('measure_distance · positive gap','15 mm setting: the retained pose check has at least 4.073 mm clearance.'),('common_volume_along_path · 0 mm³','Both neighbouring fruit, calyces and stems are included.'),('The check has a defined scope','Eight poses and 24 approach/withdrawal samples passed in Stage 2a; sampling is not a continuous certificate.')],
5:[INITIAL,('measure_volume · original clash in yellow','Original overlaps: 583.615 / 583.602 mm³ in fruit; 3.195 mm³ at a neighbouring stem.'),('Retained nose fix · same camera','Lower cheek extensions removed; carrier shortened 4 mm. Pad and blade stay functional.'),('common_volume_along_path · re-check 0 mm³','Minimum retained pose clearance: 0.693 mm. The fruit shape makes the actual gap about 9.802 mm.')],
6:[INITIAL,('Actual changed jaw · fixed pin bore · 10 N at the pad','PLA: E 3500 MPa, yield 50 MPa. Coarse isotropic mesh; 1063 solid elements.'),('execute_code · actual solver on the retained mesh','Peak 1.367 MPa · movement 0.01661 mm · yield safety factor 36.57.'),('Forces from datasheets + FEM, not measured','This coarse isotropic result does not prove print strength, fatigue or mesh convergence.')],
7:[INITIAL,('spreadsheet_get_cells · native parts enumeration','83.84 g estimated at the retained 40% PLA fill convention; all-solid envelope 130.38 g.'),('export_step + export_stl · native model + ten print pairs','The assembly STEP contains the head; the native file also retains the scene and spreadsheet.'),('Next: print, measure and test real stems','Grip 10 N, cut 15 N; test dummy clusters at 15 mm, 10 mm, then closer.')]}
def cue(n,i):
 if n!=3:return CUES[n][min(i,3)]
 if i==0:return INITIAL
 if i<=29:return ('spreadsheet_set_cells · approach' if i==1 else EASE,'Move down toward the stem while the jaw is open.')
 if i<=58:return ('Clamp' if i==30 else EASE,'The pads close around the stem.')
 if i<=92:return ('Cut' if i==59 else EASE,'The blade passes above the pad. This is a placement preview, without contact physics.')
 if i<=125:return ('Withdraw' if i==93 else EASE,'The cut fruit moves with the head along the checked withdrawal direction.')
 if i<=174:return ('Tray transfer · preview only' if i==126 else EASE,'The relocated-tray transfer was not included in the collision checks.')
 return ('At the tray · preview only','No drop, gravity, contact or tray-transfer collision result is claimed.')
APP=None
class Panels:
 def __init__(self):
  global APP
  APP=APP or QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
  self.main=QtWidgets.QWidget();self.main.resize(1600,1000);self.main.setAttribute(QtCore.Qt.WA_TranslucentBackground);self.main.setStyleSheet('background:transparent;')
  def panel(x,y,w,h):
   p=QtWidgets.QFrame(self.main);p.setGeometry(x,y,w,h);p.setStyleSheet('background:#f0f2f3;');p.show();return p
  def label(parent,x,y,w,h,size,color='#263d46',bold=False):
   l=QtWidgets.QLabel(parent);l.setGeometry(x,y,w,h);l.setWordWrap(True);l.setStyleSheet('color:%s;font:%s %dpx "DejaVu Sans";background:transparent;'%(color,'bold' if bold else '',size));l.show();return l
  top=panel(0,26,1600,190);bottom=panel(0,790,1600,168);self.card=panel(1030,230,545,550)
  self.legend=legend(self.main);self.legend.hide()
  self.chapter=label(top,40,4,1520,30,21,'#19717c',True);self.prompt=label(top,40,40,1520,74,29,'#263d46',True);self.proof=label(top,40,120,1520,55,25)
  self.activity=label(bottom,40,5,1520,42,25,'#19717c',True);self.detail=label(bottom,40,44,1520,54,23)
  label(bottom,40,100,1520,68,28).setText(DISC);self.cardlabel=label(self.card,20,10,505,530,23)
 def save(self,ch,i,path):
  n=ch['number'];self.legend.setVisible(n==6);self.chapter.setText('%02d / 07   %s'%(n,ch['title']));self.prompt.setText('You: '+ch['prompt']);self.proof.setText('What this proves: '+ch['proof'])
  a,d=cue(n,i);self.activity.setText(a);self.detail.setText(d)
  text=CARDS.get(n,'') if i>0 and (n!=1 or i==1) else '';self.cardlabel.setText(text);self.card.setVisible(bool(text))
  APP.processEvents()
  for label in self.main.findChildren(QtWidgets.QLabel):
   if not label.isVisibleTo(self.main) or not label.text():continue
   bounds=label.fontMetrics().boundingRect(QtCore.QRect(0,0,label.width(),10000),QtCore.Qt.TextWordWrap,label.text())
   assert bounds.height()<=label.height(),('Clipped caption',label.text(),bounds.height(),label.height())
   origin=label.mapTo(self.main,QtCore.QPoint(0,0))
   assert origin.x()>=0 and origin.x()+label.width()<=1600 and origin.y()>=26 and origin.y()+label.height()<=958,('Caption outside delivery crop',label.text())
  im=QtGui.QImage(1600,1000,QtGui.QImage.Format_ARGB32);im.fill(QtCore.Qt.transparent)
  p=QtGui.QPainter(im);self.main.render(p,QtCore.QPoint(),QtGui.QRegion(),QtWidgets.QWidget.DrawChildren);p.end()
  assert im.pixelColor(500,500).alpha()==0,'Caption renderer touched CAD pixels'
  assert im.save(str(path))
def interval_frames(a,b):
 """Keep only complete capture periods inside a settled interval."""
 return max(0,math.floor((b-a)*10+1e-6))

def sequence(ch,frame_count):
 """Match the selected real GUI intervals, correcting only end-of-file allowance."""
 intervals=[z for src in ch.get('prior_takes',[]) for z in src['intervals']]+ch['intervals']+[z for src in ch.get('following_takes',[]) for z in src['intervals']]
 counts=[interval_frames(a,b) for a,b in intervals];counts[-1]+=frame_count-sum(counts);assert counts[-1]>=30
 folder=O/'caption-panels';folder.mkdir(exist_ok=True);painter=Panels();files=[];cache={}
 for i,count in enumerate(counts):
  key=(cue(ch['number'],i),CARDS.get(ch['number'],'') if i>0 and (ch['number']!=1 or i==1) else '')
  if key not in cache:
   path=folder/f'{ch["number"]:02d}-{i:03d}.png';painter.save(ch,i,path);cache[key]=path
  files.append((cache[key],count/10))
 concat=folder/f'{ch["number"]:02d}.ffconcat';concat.write_text('ffconcat version 1.0\n'+''.join("file '%s'\noption framerate 10\nduration %.1f\n"%(p,d) for p,d in files)+"file '%s'\n"%files[-1][0])
 return concat
