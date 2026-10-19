"""GUI thread presentation: fixed cameras, prompts and actual MCP readback cards.
The director changes view properties only. All model edits belong to the MCP driver.
"""
import json,traceback
from pathlib import Path
import FreeCAD as App,FreeCADGui as Gui
from PySide import QtCore,QtGui,QtWidgets
import sys
sys.path.insert(0,"/demo/scripts/demo")
from stress_legend import legend
OUT=Path('/demo/demo-out/stage3')
class ReplayDirector(QtCore.QObject):
 @QtCore.Slot()
 def start(self):
  self.main=Gui.getMainWindow();self.main.showMaximized()
  QtWidgets.QApplication.setOverrideCursor(QtGui.QCursor(QtCore.Qt.BlankCursor))
  QtGui.QCursor.setPos(1599,999)
  for dock in self.main.findChildren(QtWidgets.QDockWidget):dock.hide()
  for bar in self.main.findChildren(QtWidgets.QToolBar):bar.hide()
  for old in getattr(App,'_replay_directors',[])[:-1]:
   old.timer.stop();old.top.hide();old.bottom.hide();old.card.hide()
   if hasattr(old,"legend"):old.legend.hide()
  def panel(x,y,w,h):
   p=QtWidgets.QFrame(self.main);p.setGeometry(x,y,w,h);p.setStyleSheet('background:#f0f2f3;');p.show();p.raise_();return p
  def label(parent,x,y,w,h,size,color='#263d46',bold=False):
   l=QtWidgets.QLabel(parent);l.setGeometry(x,y,w,h);l.setWordWrap(True)
   l.setStyleSheet('color:%s;font:%s %dpx "DejaVu Sans";background:transparent;'%(color,'bold' if bold else '',size));l.show();return l
  self.top=panel(0,26,1600,190)
  self.chapter=label(self.top,40,4,1520,30,21,'#19717c',True)
  self.prompt=label(self.top,40,40,1520,74,29,'#263d46',True)
  self.proof=label(self.top,40,120,1520,55,25)
  self.bottom=panel(0,790,1600,168)
  self.activity=label(self.bottom,40,5,1520,42,25,'#19717c',True)
  self.detail=label(self.bottom,40,44,1520,54,23)
  self.disclosure=label(self.bottom,40,100,1520,68,28)
  self.disclosure.setText('Scripted MCP replay · no live AI · waits trimmed · joined takes\nCAD capture · captions restored · forces estimated, not measured')
  self.legend=legend(self.main);self.legend.hide()
  self.card=panel(1030,230,545,550);self.card.hide()
  self.cardlabel=label(self.card,20,10,505,530,23)
  self.timer=QtCore.QTimer(self);self.timer.timeout.connect(self.poll);self.timer.start(150)
  (OUT/'ui-ready').write_text('ready')
 def calm(self):
  c=getattr(self,'current_shot',None)
  if not c:return
  d=App.getDocument(c['document'])
  # Activating the MDI window matters: off-screen activeView can differ from
  # the GUI window visible in an x11 recording after opening a FEM document.
  area=self.main.findChild(QtWidgets.QMdiArea)
  windows=area.subWindowList() if area else []
  candidates=[w for w in windows if d.Label in w.windowTitle() or d.Name in w.windowTitle() or (d.Name=='fem' and 'fem' in w.windowTitle().lower())]
  if candidates and area.activeSubWindow()!=candidates[0]:area.setActiveSubWindow(candidates[0])
  if not App.ActiveDocument or App.ActiveDocument.Name!=d.Name:App.setActiveDocument(d.Name)
  if not Gui.activeDocument() or Gui.activeDocument().Document.Name!=d.Name:Gui.ActiveDocument=Gui.getDocument(d.Name)
  v=Gui.getDocument(d.Name).activeView();v.setAnimationEnabled(False)
  q=App.Rotation(*c['orientation']) if c.get('orientation') else App.Rotation()
  if c.get('view')=='viewTop':q=App.Rotation()
  elif c.get('view')=='viewFront':q=App.Rotation(App.Vector(1,0,0),90)
  center=App.Vector(*c['center']);direction=q.multVec(App.Vector(0,0,-1));pos=center-direction*500;a=q.Axis
  camera='OrthographicCamera { position %s %s %s orientation %s %s %s %s nearDistance 0.1 farDistance 3000 focalDistance 500 height %s }'%(pos.x,pos.y,pos.z,a.x,a.y,a.z,q.Angle,c['height'])
  v.setCameraType('Orthographic');v.setCamera(camera)
  keep={p['name'] for p in c['parts']}
  for name in list(keep):
   o=d.getObject(name);tip=getattr(o,'Tip',None)
   if tip:keep.add(tip.Name)
  for o in d.Objects:
   vo=getattr(o,'ViewObject',None)
   if not vo or not hasattr(vo,'Visibility'):continue
   desired=o.Name in keep or o.TypeId=='App::Part' or o.Name=='PickingHead'
   if c.get('fem') and o.Name=='JawCoarseMesh':desired=True
   if vo.Visibility!=desired:vo.Visibility=desired
  if d.getObject('RobotWrist'):
   wrist=d.RobotWrist.getGlobalPlacement();adapter=d.WristAdapter.getGlobalPlacement()
   delta=wrist.Base-adapter.Base
   angle=(wrist.Rotation.inverted()*adapter.Rotation).Angle
   assert delta.Length<1e-6 and abs(angle)<1e-6,'Wrist reference detached from adapter'
   pilot=d.WristPilotBoss.getGlobalPlacement().Base-adapter.Base-App.Vector(0,float(d.Dims.get('WristAdapterProfileY0')),float(d.Dims.get('WristAdapterProfileZ'))+float(d.Dims.get('PlateThickness'))-float(d.Dims.get('PilotDepth')))
   assert pilot.Length<1e-6,'Wrist pilot detached from adapter'
   with (OUT/'wrist-poses.jsonl').open('a') as log:
    log.write(json.dumps({'head_mm':[float(d.Motion.get('Head'+a)) for a in 'XYZ'],'jaw_deg':float(d.Motion.get('JawAngle')),'cut_deg':float(d.Motion.get('CutAngle')),'wrist_mm':list(wrist.Base),'adapter_mm':list(adapter.Base),'offset_mm':delta.Length,'pilot_error_mm':pilot.Length,'rotation_error_rad':angle})+'\n')
  if any(p.get('clash') for p in c['parts']):App._stage2_renderers[-1].highlight_clashes(c,d,v)
  v.redraw()
 def poll(self):
  path=OUT/'ui-command.json'
  if not path.exists():return
  c=json.loads(path.read_text())
  path.unlink()
  try:
   if c.get('shot'):
    self.legend.setVisible(bool(c['shot'].get('fem')))
    area=self.main.findChild(QtWidgets.QMdiArea)
    (OUT/'mdi-windows.json').write_text(json.dumps({'target':c['shot']['document'],'label':App.getDocument(c['shot']['document']).Label,'windows':[w.windowTitle() for w in area.subWindowList()]}))
    actor=App._stage2_renderers[-1];actor.capture=lambda:None;actor.cmd=c['shot'];actor.prepare();self.current_shot=c['shot'];self.calm()
   elif c.get('refresh'):self.calm()
   for key in ['chapter','prompt','proof','activity','detail']:
    if key in c:getattr(self,key).setText(c[key])
   if 'card' in c:
    self.cardlabel.setText(c['card']);self.card.setVisible(bool(c['card']))
   for p in [self.top,self.bottom,self.card]:p.raise_()
   QtCore.QTimer.singleShot(350,lambda:(OUT/'ui-ack.json').write_text(json.dumps({'id':c['id'],'ok':True})))
  except Exception:(OUT/'ui-ack.json').write_text(json.dumps({'id':c['id'],'ok':False,'error':traceback.format_exc()}))
_replay_director=ReplayDirector();_replay_director.moveToThread(QtWidgets.QApplication.instance().thread())
App._replay_directors=getattr(App,'_replay_directors',[])+[_replay_director]
QtCore.QMetaObject.invokeMethod(_replay_director,'start',QtCore.Qt.QueuedConnection)
print('Replay prompt director queued')
