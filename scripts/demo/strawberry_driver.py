#!/usr/bin/env python3
"""Design gate orchestration: every CAD read/write uses real MCP stdio tools.
Geometry script is submitted via MCP execute_code; engineering uses typed tools.
Director is presentation only. No recordings, commits, or network publication.
"""
import json, math, time, sys, traceback
from pathlib import Path
from stdio_client import Client
ROOT=Path(__file__).resolve().parents[2]; OUT=ROOT/'demo-out'; DOC='StrawberryHead'
RUNTIME=OUT/'design-runtime'; RUNTIME.mkdir(exist_ok=True)
if not (RUNTIME/'profile').exists() and not (RUNTIME/'profile').is_symlink(): (RUNTIME/'profile').symlink_to(OUT/'design-profile')
C=Client(RUNTIME, timeout=600)
CALLS=OUT/'design-calls.json'
events=json.loads(CALLS.read_text()) if CALLS.exists() else []
def call(tool,required=True,**args):
 if tool not in ['create_document','open_document','get_parts_list','get_view','set_section_view','save_document_as','save_document','execute_code','get_worker_status','get_request_status']:
  args.setdefault('doc_name',DOC)
 started=time.time()
 result=C.call(tool,**args)
 events.append({'tool':tool,'arguments':args,'result':result,'seconds':round(time.time()-started,3)})
 tmp=CALLS.with_suffix('.tmp'); tmp.write_text(json.dumps(events,indent=2)); tmp.replace(CALLS)
 print(tool, 'OK' if result['ok'] else 'FAILED',result['text'][:450],flush=True)
 if required and not result['ok']: raise RuntimeError(str(result)[:2000])
 return result['data']
def code(body,required=True):
 return call('execute_code',required,code=body,document=DOC,recompute='target',execution_mode='gui')
def edit(name,**props): return call('edit_object',obj_name=name,obj_properties=props)
def show(name,yes): return edit(name,ViewObject={'Visibility':yes})
def capture(file,title,subtitle='',footer=None,**kw):
 seq=int(time.time()*1000)
 command={'id':seq,'action':'capture','file':file,'title':title,'subtitle':subtitle,'footer':footer or [],**kw}
 tmp=OUT/'design-command.tmp'; tmp.write_text(json.dumps(command)); tmp.replace(OUT/'design-command.json')
 for i in range(300):
  p=OUT/'design-ack.json'
  if p.exists():
   ack=json.loads(p.read_text())
   if ack.get('id')==seq:
    if not ack['ok']: raise RuntimeError(ack)
    return
  time.sleep(.1)
 raise TimeoutError('Director capture')
def output_json(data):
 # execute_code returns printed output inside a result wrapper.
 for text in [data.get('stdout',''),data.get('output',''),data.get('result',''),data.get('message','')]:
  if isinstance(text,str):
   for line in reversed(text.splitlines()):
    line=line.removeprefix('Output: ').strip()
    try: return json.loads(line)
    except ValueError: pass
 return None

def build():
 if '--retry' in sys.argv: code("import FreeCAD as App\nd=App.getDocument('StrawberryHead')\nfor o in reversed(d.Objects): d.removeObject(o.Name)")
 else: call('create_document',name=DOC)
 call('spreadsheet_create',sheet_name='Dims')
 code((ROOT/'scripts/demo/design_presentation.py').read_text())
 res=code((ROOT/'scripts/demo/strawberry_model.py').read_text())
 (OUT/'build-result.json').write_text(json.dumps(res,indent=2))
 manifest=output_json(res)
 if manifest: (OUT/'design-manifest.json').write_text(json.dumps(manifest,indent=2))
 else: raise RuntimeError('Cannot decode model manifest '+str(res)[:1500])
 finish_build()

def finish_build():
 # Reveal only final Body tips, through typed view property calls.
 code("import FreeCAD as App\nd=App.getDocument('StrawberryHead')\nprint([(o.Name,str(o.State)) for o in d.Objects if hasattr(o,'Shape') and o.State])")
 manifest=json.loads((OUT/'design-manifest.json').read_text())
 # All view mutations belong to typed tools, which run on the correct GUI thread.
 for p in manifest['parts']:
  edit(p['name'],ViewObject={'ShapeColor':p['color'],'DisplayMode':'Flat Lines','Visibility':True})
 # Hide intermediate features without touching the presentation director.
 res=code("import FreeCAD as App,json\nd=App.getDocument('StrawberryHead')\nprint(json.dumps([o.Name for o in d.Objects if o.TypeId=='Sketcher::SketchObject' or (o.TypeId.startswith('PartDesign::') and o.TypeId!='PartDesign::Body' and o.getParentGeoFeatureGroup() and o.getParentGeoFeatureGroup().Tip!=o)]))")
 hidden=output_json(res)
 for name in hidden or []: show(name,False)
 call('create_assembly',assembly_name='PickingHead')
 parents=['JawRotor','CutterRotor','ClampHornRotor','CutHornRotor','ClampLinkRotor','CutLinkRotor']
 moving=['MovingJaw','MovingTPU','PadBacking','BladeLever','HobbyBlade','BladeClamp','BladeClampM20','BladeClampM21','ClampHorn','ClampLink','ClampHornLinkPin','ClampLeverLinkPin','CutHorn','CutLink','CutHornLinkPin','CutLeverLinkPin']
 for p in manifest['parts']:
  if p['kind']!='scene' and p['name'] not in moving:
   call('move_object',obj_name=p['name'],target_container='PickingHead')
 for name in parents: call('move_object',obj_name=name,target_container='PickingHead')
 for axis in ['x','y','z']: call('set_expression',object_name='PickingHead',prop_path='Placement.Base.'+axis,expression='Dims.Head'+axis.upper())
 # Shape aggregation includes every physical solid for interference and mass.
 call('create_object',obj_type='Part::Feature',obj_name='HeadEnvelope')
 # Link lists are set via MCP code because the generic mapper has no LinkList conversion.
 code("import FreeCAD as App\nd=App.getDocument('StrawberryHead')\nshapes=[]\nfor o in d.Objects:\n if o.TypeId=='PartDesign::Body' and o.Category!='scene':\n  shape=o.Shape.copy(); shape.Placement=o.getGlobalPlacement(); shapes.append(shape)\nimport Part\nd.HeadEnvelope.Shape=Part.makeCompound(shapes)\nprint('Head compound tracks physical components')")
 show('HeadEnvelope',False)
 capture('initial.png','Initial parametric assembly',footer=['Reference cluster: 30 x 35 mm berries | 3 mm stem | 15 mm neighbour gap'])
 call('save_document_as',selector={'document_name':DOC},destination='/demo/demo-out/strawberry-head.FCStd',overwrite=True)

def gui_batch(parts=None,visible=None):
 parts=parts or []
 payload={'parts':parts,'visible':visible or {}}
 res=code("""import FreeCAD as App,FreeCADGui as Gui,json
from PySide import QtCore,QtWidgets
_design_view_payload="""+repr(payload)+"""
class DesignViewBatch(QtCore.QObject):
 @QtCore.Slot()
 def start(self): QtCore.QTimer.singleShot(1000,self.apply)
 @QtCore.Slot()
 def apply(self):
  try:
   d=App.getDocument('StrawberryHead')
   if not d.getMutationReadiness().get('ready',False):
    QtCore.QTimer.singleShot(200,self.apply);return
   App.ParamGet('User parameter:BaseApp/Preferences/View').SetBool('ShowNaviCube',False)
   for p in _design_view_payload['parts']:
    b=d.getObject(p['name']); tip=getattr(b,'Tip',None) or b
    b.ViewObject.ShapeColor=tuple(p['color']); tip.ViewObject.ShapeColor=tuple(p['color'])
    tip.ViewObject.DisplayMode='Flat Lines'
    b.ViewObject.Transparency=p.get('transparency',0);tip.ViewObject.Transparency=p.get('transparency',0)
    b.ViewObject.Visibility=True
   if _design_view_payload['parts']:
    for o in d.Objects:
     if o.TypeId.startswith('Fem::') or hasattr(o,'JointType') or hasattr(o,'ObjectToGround'):
      vo=getattr(o,'ViewObject',None)
      if vo and hasattr(vo,'Visibility'):vo.Visibility=False
     elif o.TypeId=='Sketcher::SketchObject':o.ViewObject.Visibility=False
     elif o.TypeId.startswith('PartDesign::') and o.TypeId!='PartDesign::Body':
      body=o.getParentGeoFeatureGroup()
      if body and body.Tip!=o:o.ViewObject.Visibility=False
   for n,v in _design_view_payload['visible'].items():
    o=d.getObject(n)
    if o:o.ViewObject.Visibility=v
   result={'ok':True}
  except Exception as e:
   if 'non-owner thread during an atomic presentation callback' in str(e):
    QtCore.QTimer.singleShot(200,self.apply);return
   result={'ok':False,'error':str(e)}
  from pathlib import Path
  Path('/demo/demo-out/design-ui-ack.json').write_text(json.dumps(result))
_design_view_actor=DesignViewBatch()
_design_view_actor.moveToThread(QtWidgets.QApplication.instance().thread())
QtCore.QMetaObject.invokeMethod(_design_view_actor,'start',QtCore.Qt.QueuedConnection)
print('Queued GUI-only view batch; no geometry mutation')
""")
 ack=OUT/'design-ui-ack.json'
 for i in range(600):
  if ack.exists():
   r=json.loads(ack.read_text());ack.unlink()
   if not r['ok']:raise RuntimeError(r)
   return res
  time.sleep(.1)
 raise TimeoutError('GUI view batch')

def fast_finish():
 manifest=json.loads((OUT/'design-manifest.json').read_text())
 gui_batch(manifest['parts'])
 call('create_assembly',assembly_name='PickingHead',if_exists='skip')
 code("""import FreeCAD as App
D=App.getDocument('StrawberryHead')
for o in list(D.Objects):
 if o.TypeId=='PartDesign::Body' and o.Category!='scene' and not o.getParentGeoFeatureGroup():D.PickingHead.addObject(o)
for n in ['JawRotor','CutterRotor','ClampHornRotor','CutHornRotor','ClampLinkRotor','CutLinkRotor']:D.PickingHead.addObject(D.getObject(n))
for axis in ['x','y','z']:D.PickingHead.setExpression('Placement.Base.'+axis,'Dims.Head'+axis.upper())
if not D.getObject('HeadEnvelope'):D.addObject('Part::Feature','HeadEnvelope')
import Part
shapes=[]
for o in D.Objects:
 if o.TypeId=='PartDesign::Body' and o.Category!='scene':
  shape=o.Shape.copy();shape.Placement=o.getGlobalPlacement();shapes.append(shape)
D.HeadEnvelope.Shape=Part.makeCompound(shapes)
print('Assembly grouping and world-frame validation compound complete')
""")
 gui_batch(visible={'HeadEnvelope':False})
 capture('initial.png','Initial parametric assembly',footer=['30 x 35 mm berries | 3 mm stem | 15 mm nominal gap'])
 call('save_document_as',selector={'document_name':DOC},destination='/demo/demo-out/strawberry-head.FCStd',overwrite=True)

def status():
 res=call('get_request_status',request_id='ae4582c1-377c-5c75-9441-f06b2883e4c3',required=False)
 (OUT/'design-request-status.json').write_text(json.dumps(res,indent=2))
 print(json.dumps(res)[:2500],flush=True)

def recover():
 res=call('get_mutation_readiness',required=False)
 while not res.get('ready',False):
  time.sleep(15)
  res=call('get_mutation_readiness',required=False)
 print(json.dumps(res)[:1500],flush=True)
 data=code("""import FreeCAD as App,json
D=App.getDocument('StrawberryHead'); S=D.Dims
params=[]
for r in range(1,6000):
 a='B'+str(r); v=S.getContents(a)
 if not v: break
 params.append({'row':r,'alias':S.getAlias(a),'value':v,'description':S.getContents('A'+str(r))})
parts=[]
for b in D.Objects:
 if b.TypeId!='PartDesign::Body':continue
 material=b.MaterialNote; category=b.Category
 color=(0.59,0.62,0.65) if category=='bought' else (0.13,0.47,0.59)
 if material=='TPU':color=(0.22,0.68,0.57)
 if any(k in b.Name for k in ['Jaw','ClampLink']):color=(0.94,0.62,0.20) if category=='printed' else color
 if any(k in b.Name for k in ['BladeLever','BladeClamp','CutLink']):color=(0.43,0.38,0.65) if category=='printed' else color
 if material=='berry':color=(0.78,0.12,0.18)
 if material in ['cap','stem']:color=(0.24,0.46,0.20)
 if category=='scene' and material not in ['berry','cap','stem']:color=(0.68,0.74,0.77)
 parts.append({'name':b.Name,'kind':category,'material':material,'color':color})
print(json.dumps({'parameters':params,'printed':[p['name'] for p in parts if p['kind']=='printed'],'bought':[p['name'] for p in parts if p['kind']=='bought'],'scene':[p['name'] for p in parts if p['kind']=='scene'],'parts':parts,'cells':{p['alias']:'B'+str(p['row']) for p in params}}))
""")
 (OUT/'recover-result.json').write_text(json.dumps(data,indent=2))
 manifest=output_json(data)
 if manifest:(OUT/'design-manifest.json').write_text(json.dumps(manifest,indent=2))
 else:raise RuntimeError('Cannot decode '+str(data)[:1000])

if __name__=='__main__':
 try:
  globals()[sys.argv[1] if len(sys.argv)>1 else 'build']()
 finally: C.close()
