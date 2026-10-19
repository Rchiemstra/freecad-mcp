"""Presentation only: native viewport capture and plain measurement labels."""
import FreeCAD as App,FreeCADGui as Gui,json,math,traceback,colorsys
from pathlib import Path
from PySide import QtCore,QtGui,QtWidgets
class Stage2Renderer(QtCore.QObject):
 @QtCore.Slot()
 def start(self):
  for actor in getattr(App,'_stage2_renderers',[])[:-1]:actor.timer.stop()
  self.timer=QtCore.QTimer(self);self.timer.timeout.connect(self.poll);self.timer.start(150)
 def poll(self):
  path=Path('/demo/demo-out/stage2/render-command.json')
  if not path.exists():return
  cmd=json.loads(path.read_text())
  if not App.getDocument(cmd.get('document','StrawberryHead')).getMutationReadiness().get('ready'):return
  path.unlink();self.cmd=cmd
  try:self.prepare()
  except Exception:self.ack(False,traceback.format_exc())
 def prepare(self):
  previous=getattr(self,'clash_overlay',None)
  if previous is not None:
   if self.clash_root.findChild(previous)>=0:self.clash_root.removeChild(previous)
   self.clash_overlay=None
  c=self.cmd;d=App.getDocument(c.get('document','StrawberryHead'));App.setActiveDocument(d.Name);Gui.ActiveDocument=Gui.getDocument(d.Name)
  for o in d.Objects:
   if o.TypeId=='App::Part' or o.Name=='PickingHead':o.ViewObject.Visibility=True
  for o in d.Objects:
   vo=getattr(o,'ViewObject',None)
   if vo and hasattr(vo,'Visibility') and o.TypeId!='App::Part' and o.Name!='PickingHead':vo.Visibility=False
  for p in c['parts']:
   o=d.getObject(p['name']);vo=o.ViewObject
   vo.Visibility=True
   parent=o.getParentGeoFeatureGroup()
   while parent:
    parent.ViewObject.Visibility=True;parent=parent.getParentGeoFeatureGroup()
   tip=getattr(o,'Tip',None);views=[vo]+([tip.ViewObject] if tip else [])
   for v in views:
    v.Visibility=True
    color=tuple(p.get('color',[.45,.5,.55]))
    try:
     if any(any(abs(a-b)>1e-5 for a,b in zip(old[:3],color)) for old in v.DiffuseColor):v.DiffuseColor=[color]
    except Exception:pass
    try:modes=list(v.listDisplayModes())
    except Exception:modes=[]
    mode=p.get('mode') or ('Flat Lines' if p.get('lines') else 'Shaded' if 'Shaded' in modes else 'Flat Lines')
    for prop,value in [('ShapeColor',color),('Transparency',p.get('transparency',0)),('DisplayMode',mode),('Deviation',.025),('AngularDeflection',4),('LineWidth',1.)]:
     try:
      old=getattr(v,prop)
      same=all(abs(a-b)<1e-5 for a,b in zip(old[:3],value)) if prop=='ShapeColor' else old==value
      if not same:setattr(v,prop,value)
     except Exception:pass
    try:
     if tuple(v.LineColor[:3])!=(.19,.23,.26):v.LineColor=(.19,.23,.26)
    except Exception:pass
   if p.get('clash') or p.get('force_color'):
    from pivy import coin
    root=vo.RootNode
    if root.getNumChildren()==0 or root.getChild(0).getName()!='Stage2ClashMaterial':
     bias=coin.SoPolygonOffset();bias.setName('Stage2ClashMaterial');bias.factor=-2;bias.units=-2;bias.on=True;root.insertChild(bias,0)
     material=coin.SoMaterial();material.diffuseColor.setValue(*p.get('color',[1,.79,.01]));material.transparency.setValue(0);material.setOverride(True);root.insertChild(material,1)
     binding=coin.SoMaterialBinding();binding.value=coin.SoMaterialBinding.OVERALL;binding.setOverride(True);root.insertChild(binding,2)
  if c.get('fem'):
   r=[o for o in d.Objects if hasattr(o,'vonMises') and len(o.vonMises)][-1];mesh=d.JawCoarseMesh
   mesh.ViewObject.Visibility=True;mesh.ViewObject.DisplayMode='Faces';mesh.ViewObject.ColorMode='ByNode'
   vmax=max(r.vonMises);mesh.ViewObject.NodeColor={int(n):colorsys.hsv_to_rgb((1-float(s)/vmax)*2/3,.85,.95) for n,s in zip(r.NodeNumbers,r.vonMises)}
  pref=App.ParamGet('User parameter:BaseApp/Preferences/View')
  for k in ('BackgroundColor','BackgroundColor2','BackgroundColor3'):pref.SetUnsigned(k,0xf0f2f3ff)
  pref.SetBool('UseNavigationAnimations',False);pref.SetBool('Simple',True);pref.SetBool('ShowNaviCube',False);pref.SetBool('ShowAxisCross',False)
  Gui.Selection.clearSelection();view=Gui.activeDocument().activeView();view.setCameraType('Orthographic')
  view.setAnimationEnabled(False)
  q=App.Rotation(*c['orientation']) if c.get('orientation') else App.Rotation()
  if c.get('view')=='viewTop':q=App.Rotation()
  elif c.get('view')=='viewFront':q=App.Rotation(App.Vector(1,0,0),90)
  self.q=q;center=App.Vector(*c['center']);direction=q.multVec(App.Vector(0,0,-1));pos=center-direction*500;a=q.Axis
  view.setCamera('OrthographicCamera { position %s %s %s orientation %s %s %s %s nearDistance 0.1 farDistance 3000 focalDistance 500 height %s }'%(pos.x,pos.y,pos.z,a.x,a.y,a.z,q.Angle,c['height']))
  self.highlight_clashes(c,d,view)
  view.redraw();QtCore.QTimer.singleShot(600,self.capture)
 # Draw actual intersection BReps through solid context in the native viewport.
 def highlight_clashes(self,c,d,view):
  clashes=[p for p in c['parts'] if p.get('clash')]
  if not clashes:return
  root=view.getSceneGraph();previous=getattr(self,'clash_overlay',None)
  if previous is not None and root.findChild(previous)>=0:return
  from pivy import coin
  overlay=coin.SoSeparator();overlay.setName('OriginalCommonHighlight')
  depth=coin.SoDepthBuffer();depth.test=True;depth.write=False;depth.function=coin.SoDepthBuffer.ALWAYS;depth.setOverride(True)
  material=coin.SoMaterial();material.diffuseColor=(1,.79,.01);material.transparency=0;material.setOverride(True)
  overlay.addChild(depth);overlay.addChild(material)
  for p in clashes:overlay.addChild(d.getObject(p['name']).ViewObject.RootNode.copy(False))
  root.addChild(overlay);self.clash_root=root;self.clash_overlay=overlay
 def capture(self):
  try:
   c=self.cmd;path='/demo/demo-out/'+c.get('output_dir','stills2')+'/'+c['file'];v=Gui.activeDocument().activeView();Gui.Selection.clearSelection();v.saveImage(path,1600,1000,'Current')
   im=QtGui.QImage(path);p=QtGui.QPainter(im);p.setRenderHint(QtGui.QPainter.Antialiasing)
   bg=QtGui.QColor('#f0f2f3');ink=QtGui.QColor('#263d46')
   p.fillRect(0,0,1600,112,bg);p.setPen(ink);p.setFont(QtGui.QFont('DejaVu Sans',24,QtGui.QFont.Bold));p.drawText(50,52,c['title'])
   p.setFont(QtGui.QFont('DejaVu Sans',14));p.drawText(52,88,c.get('subtitle','freecad-mcp | the companion FreeCAD fork | design gate 2'))
   p.fillRect(0,914,1600,86,bg);p.setFont(QtGui.QFont('DejaVu Sans',14));p.setPen(ink)
   for i,line in enumerate(c.get('footer',[])):p.drawText(50,946+i*29,line)
   center=App.Vector(*c['center']);right=self.q.multVec(App.Vector(1,0,0));up=self.q.multVec(App.Vector(0,1,0))
   def project(point):
    delta=App.Vector(*point)-center;return QtCore.QPointF(800+delta.dot(right)*1000/c['height'],500-delta.dot(up)*1000/c['height'])
   for label in c.get('labels',[]):
    x,y=label['textpos'];txt=label['text'];p.setFont(QtGui.QFont('DejaVu Sans',17))
    w=p.fontMetrics().horizontalAdvance(txt)+24
    p.setPen(QtGui.QPen(ink,1.5))
    if label.get('point') is not None:
     end=project(label['point']);start=QtCore.QPointF(*label.get('leader_start',[x+w/2,y+5]));p.drawLine(start,end);p.setBrush(ink);p.drawEllipse(end,3,3)
    p.fillRect(int(x)-8,int(y)-26,int(w),37,bg);p.drawText(int(x),int(y),txt)
   for dim in c.get('dimensions',[]):
    a=project(dim['a']);b=project(dim['b']);x=dim['x']
    p.setPen(QtGui.QPen(ink,2));p.drawLine(a,QtCore.QPointF(x+10,a.y()));p.drawLine(b,QtCore.QPointF(x+10,b.y()));p.drawLine(QtCore.QPointF(x,a.y()),QtCore.QPointF(x,b.y()))
    for y,sign in [(a.y(),1),(b.y(),-1)]:
     p.drawLine(QtCore.QPointF(x,y),QtCore.QPointF(x-6,y+sign*7));p.drawLine(QtCore.QPointF(x,y),QtCore.QPointF(x+6,y+sign*7))
    p.setFont(QtGui.QFont('DejaVu Sans',18));p.drawText(int(x+20),int((a.y()+b.y())/2+8),dim['text'])
   if c.get('fem'):
    d=App.getDocument(c['document']);r=[o for o in d.Objects if hasattr(o,'vonMises') and len(o.vonMises)][-1];vmax=max(r.vonMises)
    p.fillRect(1300,160,280,650,bg);p.setFont(QtGui.QFont('DejaVu Sans',15));p.setPen(ink);p.drawText(1310,195,'von Mises [MPa]')
    for y in range(450):
     rgb=colorsys.hsv_to_rgb(y/449*2/3,.85,.95);p.fillRect(1320,230+y,35,1,QtGui.QColor.fromRgbF(*rgb))
    p.setPen(ink)
    for t in [0,.25,.5,.75,1]:p.drawText(1375,int(235+(1-t)*449),'%.3f'%(vmax*t))
    p.drawText(1310,740,'Undeformed jaw')
   p.end();assert im.save(path);self.ack(True,path)
  except Exception:self.ack(False,traceback.format_exc())
 def ack(self,ok,message):Path('/demo/demo-out/stage2/render-ack.json').write_text(json.dumps({'id':self.cmd.get('id'),'ok':ok,'message':message}))
_stage2_renderer=Stage2Renderer();_stage2_renderer.moveToThread(QtWidgets.QApplication.instance().thread())
QtCore.QMetaObject.invokeMethod(_stage2_renderer,'start',QtCore.Qt.QueuedConnection)
App._stage2_renderers=getattr(App,'_stage2_renderers',[])+[_stage2_renderer]
print('Stage 2 renderer queued; presentation only')
