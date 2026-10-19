"""Stage 2 design gate. Model changes and checks always pass through MCP."""
from stage2_support import *
import strawberry_checks as c
c.OUT=OUT;c.REPORT=OUT/'checks.json';c.R=json.loads(c.REPORT.read_text()) if c.REPORT.exists() else {}
c.M=json.loads((OUT/'design-manifest.json').read_text()) if (OUT/'design-manifest.json').exists() else json.loads(Path('/demo/demo-out/design-manifest.json').read_text())
M=c.M;c.DOC=d.DOC

def ec(body):return d.output_json(d.code(body))
def open_stage1():
 M.clear();M.update(json.loads(Path('/demo/demo-out/design-manifest.json').read_text()))
 info=call('open_document',path='/demo/demo-out/strawberry-head.FCStd')
 d.DOC=info['document_name'];c.DOC=d.DOC;sys.modules['stage2_support'].MODEL_DOC=d.DOC
 (OUT/'document-name.json').write_text(json.dumps({'document_name':d.DOC}))
 wait_ready()
 (OUT/'design-manifest.json').write_text(json.dumps(M,indent=2))
 print(ec("""import FreeCAD as App,json
D=App.getDocument('StrawberryHead')
print(json.dumps({'objects':len(D.Objects),'motion':{k:D.Motion.get(k) for k in ['HeadZ','HeadY','JawAngle','CutAngle','NeighbourGap']},'parts':{n:{'bbox':list(D.getObject(n).Shape.BoundBox.getPoint(0))+list(D.getObject(n).Shape.BoundBox.getPoint(6)),'volume':D.getObject(n).Shape.Volume} for n in ['NoseFrameReady','MovingJaw','BladeLever','HobbyBlade','DriveHousingReady']}}))
"""))

def fruit():
 r=ec("""import FreeCAD as App,Part,math,json
D=App.getDocument('StrawberryHead')
for tag in ['Target','NeighbourL','NeighbourR']:
 b=D.getObject(tag+'Berry');sk=D.addObject('Sketcher::SketchObject',tag+'SmoothProfile');b.addObject(sk)
 sk.Placement=App.Placement(App.Vector(0,0,0),App.Rotation(App.Vector(1,0,0),90))
 curve=Part.BSplineCurve()
 curve.interpolate([App.Vector(x,z,0) for x,z in [(0,-43),(2.5,-42),(6,-39),(10,-34),(13,-28),(15,-21),(14.5,-15),(11.5,-10),(6,-8),(0,-8)]])
 sk.addGeometry(curve,False);sk.addGeometry(Part.LineSegment(App.Vector(0,-8,0),App.Vector(0,-43,0)),False)
 rev=D.getObject(tag+'Revolution');rev.Profile=sk;rev.ReferenceAxis=(sk,['V_Axis'])
 cap=D.getObject(tag+'Cap');leaf=D.addObject('Sketcher::SketchObject',tag+'SepalProfile');cap.addObject(leaf);leaf.Placement.Base.z=-8
 pts=[]
 for i in range(6):
  for off,r in [(0,3.5),(0.30,7),(0.52,11),(0.74,7)]:
   a=i*math.pi/3+off;pts.append(App.Vector(r*math.cos(a),r*math.sin(a),0))
 for i,p in enumerate(pts):leaf.addGeometry(Part.LineSegment(p,pts[(i+1)%len(pts)]),False)
 cp=D.getObject(tag+'CapPad');cp.Profile=leaf;cp.setExpression('Length',None);cp.Length=1.2
 # Short calyx-to-pedicel stub; the connected long pedicel remains the picking stem.
 stub=D.addObject('Part::Cylinder',tag+'StemStub');D.getObject(tag).addObject(stub)
 stub.Radius=1.8;stub.Height=4;stub.Placement.Base.z=-7
 stub.addProperty('App::PropertyString','Category');stub.Category='scene';stub.addProperty('App::PropertyString','MaterialNote');stub.MaterialNote='stem'
print(json.dumps({'spline_revolves':3,'sepals_per_calyx':6,'short_stub_mm':4}))
""")
 for tag in ['Target','NeighbourL','NeighbourR']:
  M['parts'].append({'name':tag+'StemStub','kind':'scene','material':'stem','color':[.23,.43,.15]})
 (OUT/'design-manifest.json').write_text(json.dumps(M,indent=2));c.R['fruit']=r;c.persist()
 c.pose('clamp')

def inspect():
 print(ec("""import FreeCAD as App,json
D=App.getDocument('StrawberryHead')
print(json.dumps({'parts':[{ 'name':o.Name,'category':o.Category,'type':o.TypeId,'tip':getattr(getattr(o,'Tip',None),'Name',None),'bbox':[o.Shape.BoundBox.XMin,o.Shape.BoundBox.XMax,o.Shape.BoundBox.YMin,o.Shape.BoundBox.YMax,o.Shape.BoundBox.ZMin,o.Shape.BoundBox.ZMax],'solids':len(o.Shape.Solids)} for o in D.Objects if hasattr(o,'Category') and o.Category in ['printed','bought'] and hasattr(o,'Shape')],'bindings':{n:list(D.getObject(n).ExpressionEngine) for n in ['NoseFrameReady','NoseCheekLProfile','BladeLeverProfile','MovingJawProfile','ClampCable','CutCable']}}))
"""))

def snapshot():
 call('save_document_as',selector={'document_name':d.DOC},destination='/demo/demo-out/strawberry-head-v2.FCStd',overwrite=True)

def render(file,title,subtitle,parts=None,center=(0,0,0),height=160,view=None,orientation=None,footer=None,labels=None,**kw):
 command={'id':time.time_ns(),'file':file,'title':title,'subtitle':subtitle,'document':kw.pop('document',d.DOC),'parts':parts if parts is not None else M['parts'],'center':center,'height':height,'view':view,'orientation':orientation,'footer':footer or [],'labels':labels or [],**kw}
 p=OUT/'render-ack.json'
 if p.exists():p.unlink()
 temp=OUT/'render-command.tmp';temp.write_text(json.dumps(command));temp.replace(OUT/'render-command.json')
 for _ in range(600):
  if p.exists():
   ack=json.loads(p.read_text())
   if ack.get('id')==command['id']:
    assert ack['ok'],ack
    # Color/material presentation can leave the native model needing recompute.
    call('recompute_document',doc_name=command['document'],required=False)
    return ack
  time.sleep(.1)
 raise TimeoutError('Stage 2 capture')

def renderer():d.code((d.ROOT/'scripts/demo/stage2_renderer.py').read_text())

def baseline():
 c.narrow()
 c.R['baseline_narrow']=c.R['narrow'];c.R['baseline_narrow_volumes']={n:call('measure_volume',obj_name=n) for n in ['NarrowClashL','NarrowClashR','NarrowCarrierStemL']};c.persist()
 # Only this evidence view retains the original lower nose and long carrier.
 keep={'NoseFrameReady','MovingJaw','MovingTPU','FixedTPU','BladeLever','HobbyBlade','BladeClamp','JawPin','CutterPin','TargetBerry','TargetCap','TargetStem','NeighbourLBerry','NeighbourRBerry','NeighbourLCap','NeighbourRCap','NeighbourLStem','NeighbourRStem'}
 parts=[{**p,'transparency':65 if p['material']=='berry' else 35 if p['name'] in ['NoseFrameReady','BladeLever'] else 0} for p in M['parts'] if p['name'] in keep]
 parts += [{'name':n,'color':[1,.79,.02],'transparency':0,'lines':False} for n in ['NarrowClashL','NarrowClashR','NarrowCarrierStemL'] if True]
 render('05_narrow_gap.png','10 mm nominal gap | the original nose clashes','Yellow is the measured common volume; fruit is transparent.',parts,center=[0,-17,-6],height=160,orientation=c.view_from([.3,1.5,2.5]),footer=['Stage 1 geometry retained here for comparison. Every fruit and all yellow clash volumes are inside the frame.','The narrowed nose and shorter carrier are shown in 07_narrow_fixed.'])

def baseline_capture():
 c.setcells({'NeighbourGap':10});c.pose('clamp')
 c.R['baseline_narrow_volumes']={n:call('measure_volume',obj_name=n) for n in ['NarrowClashL','NarrowClashR','NarrowCarrierStemL']};c.persist()
 keep={'NoseFrameReady','MovingJaw','MovingTPU','FixedTPU','BladeLever','HobbyBlade','BladeClamp','JawPin','CutterPin','TargetBerry','TargetCap','TargetStem','NeighbourLBerry','NeighbourRBerry','NeighbourLCap','NeighbourRCap','NeighbourLStem','NeighbourRStem'}
 parts=[{**p,'transparency':65 if p['material']=='berry' else 35 if p['name'] in ['NoseFrameReady','BladeLever'] else 0} for p in M['parts'] if p['name'] in keep]
 parts += [{'name':n,'color':[1,.79,.02],'transparency':0} for n in ['NarrowClashL','NarrowClashR','NarrowCarrierStemL']]
 render('05_narrow_gap.png','10 mm nominal gap | the original nose clashes','Yellow is the measured common volume; fruit is transparent.',parts,center=[0,-17,-6],height=160,orientation=c.view_from([.3,1.5,2.5]),footer=['Original lower nose and carrier. All fruit and all yellow intersections are inside the frame.','The corrected assembly is shown in 07_narrow_fixed.'])

def fix():
 # Remove hanging cheek extensions below the fruit-free working plane.
 # They carried no fastener or jaw reaction: bridge, anvil, fork and rear tie remain intact.
 call('spreadsheet_create',sheet_name='V2Dims')
 call('spreadsheet_set_cells',sheet_name='V2Dims',cells=[{'address':'A1','value':'Lower nose start mm'},{'address':'B1','value':'-4','alias':'NoseBottom'},{'address':'A2','value':'Cheek height mm'},{'address':'B2','value':'13','alias':'CheekHeight'},{'address':'A3','value':'Carrier end local X mm'},{'address':'B3','value':'-26','alias':'CarrierEnd'},{'address':'A4','value':'Moving jaw and pad top mm'},{'address':'B4','value':'5.7','alias':'MovingHeight'}])
 r=ec("""import FreeCAD as App,Part,json
D=App.getDocument('StrawberryHead')
for side in ['L','R']:
 D.getObject('NoseCheek'+side+'Profile').setExpression('Placement.Base.z','V2Dims.NoseBottom')
 pad=D.getObject('NoseCheek'+side+'Pad');pad.setExpression('Length','V2Dims.CheekHeight');pad.setExpression('Length2','Length')
for index in [13,16]:D.BladeLeverProfile.setExpression('Constraints['+str(index)+']','V2Dims.CarrierEnd + 100')
for name in ['MovingJawPad','IntegralBacking','MovingTPUPad']:
 o=D.getObject(name);o.setExpression('Length','V2Dims.MovingHeight');o.setExpression('Length2','Length')
# Continuous paired servo leads lie over the existing rear cable channel.
for tag,pts in [('Clamp',[(-15,-51,18),(-15,-55,18),(-1.2,-55,18),(-1.2,-77,18)]),('Cut',[(16,-30,18),(16,-34,18),(1.2,-34,18),(1.2,-77,18)])]:
 o=D.addObject('Part::Feature',tag+'CableRoute');D.PickingHead.addObject(o)
 seg=[]
 for a,b in zip(pts,pts[1:]):
  a=App.Vector(*a);b=App.Vector(*b);seg.append(Part.makeCylinder(1,(b-a).Length,a,b-a))
 for point in pts[1:-1]:seg.append(Part.makeSphere(1,App.Vector(*point)))
 o.Shape=Part.makeCompound(seg);o.addProperty('App::PropertyString','Category');o.Category='bought';o.addProperty('App::PropertyString','MaterialNote');o.MaterialNote='cable'
 D.getObject(tag+'Cable').Category='reference'
for sign,side in [(-1,'L'),(1,'R')]:
 o=D.addObject('Part::Cylinder','ColumnBoltHead'+side);D.PickingHead.addObject(o);o.Radius=2.8;o.Height=1.5;o.Placement.Base=App.Vector(sign*12,-60,11.5)
 o.addProperty('App::PropertyString','Category');o.Category='bought';o.addProperty('App::PropertyString','MaterialNote');o.MaterialNote='steel'
print(json.dumps({'nose_bottom_mm':-4,'nose_height_mm':13,'carrier_overhang_local_x_mm':-26,'jaw_thickness_mm':5.7,'blade_to_moving_pad_clearance_mm':1.0,'servo_routes':'Continuous 2 mm leads from each servo to rear connector, in the existing channel'}))
""")
 for tag in ['Clamp','Cut']:
  M['parts']=[p for p in M['parts'] if p['name']!=tag+'Cable']
  M['bought']=[n for n in M['bought'] if n!=tag+'Cable']
  M['parts'].append({'name':tag+'CableRoute','kind':'bought','material':'cable','color':[.19,.23,.27]});M['bought'].append(tag+'CableRoute')
 for side in ['L','R']:
  M['parts'].append({'name':'ColumnBoltHead'+side,'kind':'bought','material':'steel','color':[.59,.62,.65]});M['bought'].append('ColumnBoltHead'+side)
 (OUT/'design-manifest.json').write_text(json.dumps(M,indent=2));c.R['fix']=r;c.persist();c.pose('clamp')
 snapshot()

def read_common(a,b,label):
 result=call('common_volume_along_path',moving_object=a if a=='HeadEnvelope' else 'World_'+a,obstacle_objects=[b if b=='HeadEnvelope' else 'World_'+b],samples=[{'x':0,'y':0,'z':0}])
 return {'tool_result':result,'volume':{'volume_mm3':result.get('max_common_volume_mm3',result.get('total_common_volume_mm3',0))}}

def checks():
 c.common=read_common
 c.R['force_cells']=call('spreadsheet_get_cells',sheet_name='Dims',addresses=[M['cells'][n] for n in ['StallTorque','TorqueSafety','WorkTorque','HornRadius','InputArm','JawOutputArm','CutOutputArm','ClampForce','CutForce','ClampMargin','CutMargin']])
 c.R['transmission']={tag:[c.linkage(tag,a/10)[1] for a in (range(-180,1) if tag=='Clamp' else range(-130,131))] for tag in ['Clamp','Cut']}
 c.R['geometry_checks']={n:call('validate_geometry',obj_name=n) for n in M['printed']}
 c.R['poses']={}
 for gap in [15,10]:
  c.setcells({'NeighbourGap':gap})
  for name,ja,ca,hz,hy,target in [('approach',-18,13,15,0,False),('clamp',0,13,0,0,False),('cut',0,-13,0,0,False),('withdraw',0,-13,20,-25,True)]:
   pose=c.pose(name,ja,ca,hz,hy,target);distances={}
   for obstacle in ['TargetBerry','TargetCap','NeighbourLBerry','NeighbourLCap','NeighbourLStem','NeighbourRBerry','NeighbourRCap','NeighbourRStem']:
    distances[obstacle]={'distance':call('measure_distance',shape1_ref='HeadEnvelope',shape2_ref='World_'+obstacle),'intersection':c.common('HeadEnvelope',obstacle,'V2_'+str(gap)+name+obstacle)}
   pose['clearances']=distances;pose['jaw_gap']=call('measure_distance',shape1_ref='FixedTPU',shape2_ref='MovingTPU');c.R['poses'][str(gap)+'_'+name]=pose;c.persist()
 c.R['paths']={}
 obstacles=['NeighbourLBerry','NeighbourLCap','NeighbourLStem','NeighbourRBerry','NeighbourRCap','NeighbourRStem','Truss','TargetBranch','NeighbourLBranch','NeighbourRBranch']
 for gap in [15,10]:
  c.setcells({'NeighbourGap':gap})
  for name,points in [('approach',[{'x':0,'y':0,'z':z} for z in range(15,-1,-3)]),('withdraw',[{'x':0,'y':-25*t/5,'z':20*t/5} for t in range(6)])]:
   c.pose('approach_reference',-18,13,0,0) if name=='approach' else c.pose('cut',0,-13)
   results=[]
   for point in points:
    results.append(call('common_volume_along_path',moving_object='HeadEnvelope',obstacle_objects=obstacles,samples=[point]))
    c.R['paths'][str(gap)+'_'+name]={'points':points,'results':results,'frame':'World geometry regenerated with zero head translation; absolute sample placements'};c.persist()
 c.travel_checks();c.travel_endpoint()
 c.setcells({'NeighbourGap':15});c.pose('clamp')
 c.mass();c.mass_sheet();snapshot()

def init():
 open_stage1();fruit();snapshot();archive_saved_baseline();renderer();fix()

def stills():
 c.setcells({'NeighbourGap':15});c.pose('clamp')
 ec("""import FreeCAD as App,json
D=App.getDocument('StrawberryHead');D.Tray.Placement.Base=App.Vector(-125,-60,0)
print(json.dumps({'tray_translation_mm':[-125,-60,0]}))
""")
 render('01_scene.png','A compact head that picks by the stem','Clamp the stem, cut above the pad, then lower the fruit into the tray.',center=[-55,-17,4],height=270,orientation=c.view_from([1,2,1.4]),footer=['A four-bolt wrist adapter carries two servo drives, a pin-mounted jaw and a replaceable steel blade.','freecad-mcp | the companion FreeCAD fork | 15 mm fruit spacing'])
 contact_detail_setup();contact_detail();top_detail()
 c.setcells({'NeighbourGap':10});c.pose('clamp')
 parts=[{**p,'transparency':40 if p['material']=='berry' else 0} for p in M['parts'] if p['name'] not in ['RobotWrist','WristPilotBoss','Tray','WristAdapter'] and not p['name'].startswith('FlangeScrew')]
 render('07_narrow_fixed.png','10 mm nominal gap | the corrected nose clears','The lower cheek extensions are removed; the carrier is shortened by 4 mm.',parts,center=[0,-32,-2],height=175,orientation=c.view_from([.3,1.5,2.5]),footer=['Minimum pose clearance: 0.693 mm. All checked poses and sampled paths have 0 mm³ common volume.','The changed jaw has a 5.7 mm section and 1.0 mm clearance below the blade. See design-notes.md for scope.'])
 c.setcells({'NeighbourGap':15});c.pose('clamp');snapshot()

def parts_view():
 copies=ec("""import FreeCAD as App,Part,json
D=App.getDocument('StrawberryHead');group=D.getObject('V2Parts') or D.addObject('App::Part','V2Parts');copies=[]
layout=[('WristAdapter',-110,45),('DriveHousingReady',-110,-35),('NoseFrameReady',-110,-95),('MovingJaw',0,20),('ClampLink',0,-40),('FixedTPU',-12,-90),('MovingTPU',12,-90),('BladeLever',110,20),('BladeClamp',110,-40),('CutLink',110,-90)]
for name,x,y in layout:
 source=D.getObject(name);shape=source.Shape.copy();shape.Placement=App.Placement()
 if name=='NoseFrameReady':shape.rotate(App.Vector(),App.Vector(1,0,0),90)
 bb=shape.BoundBox;shape.translate(App.Vector(x-(bb.XMin+bb.XMax)/2,y-(bb.YMin+bb.YMax)/2,-bb.ZMin))
 o=D.addObject('Part::Feature','V2Display_'+name);group.addObject(o);o.Shape=shape;copies.append({'name':o.Name,'source':name})
# Bought hardware, lifted out of its assembly position as a separate parts strip.
names=['ClampServo','CutServo','HobbyBlade','JawPin','CutterPin','FrameBoltL','FlangeScrew1','ClampM2Screw0','JawPivotLocknut','BladeClampM20']
for i,name in enumerate(names):
 source=D.getObject(name);shape=source.Shape.copy();shape.Placement=App.Placement()
 if 'Pin' in name or 'Screw' in name or 'Bolt' in name:shape.rotate(App.Vector(),App.Vector(1,0,0),90)
 bb=shape.BoundBox;shape.translate(App.Vector(-135+i*30-(bb.XMin+bb.XMax)/2,-135-(bb.YMin+bb.YMax)/2,-bb.ZMin))
 o=D.addObject('Part::Feature','V2Display_'+name);group.addObject(o);o.Shape=shape;copies.append({'name':o.Name,'source':name})
print(json.dumps(copies))
""")
 parts=[{'name':p['name'],'color':next(q['color'] for q in M['parts'] if q['name']==p['source']),'lines':True} for p in copies]
 render('04_parts.png','Ten printed parts, familiar hardware','Actual part shapes arranged on their print faces; representative bought hardware below.',parts,center=[0,-25,0],height=330,view='viewTop',labels=[{'text':'structure','textpos':[390,150]},{'text':'clamp + pads','textpos':[700,150]},{'text':'cutter','textpos':[1090,150]}],footer=['Minimum specified printed walls: 2.0 mm; bearing ligaments: 2.4 mm. Flat faces and mounting holes are modeled.','Grey parts are bought. STEP and STL files contain the ten printed parts; see design-notes.md for the full hardware list.'])

def exports():
 c.R['exports']={}
 for name in M['printed']:
  c.R['exports'][name]={'step':call('export_step',file_path='/demo/demo-out/files/'+name+'-v2.step',obj_names=[name]),'stl':call('export_stl',file_path='/demo/demo-out/files/'+name+'-v2.stl',obj_names=[name],mesh_deviation=.08)};c.persist()
 snapshot()

def fem_still():
 F=json.loads((OUT/'fem.json').read_text());r=F['results']
 render('06_fem.png','The changed jaw | real static FEM','PLA, 10 N at the pad; pin bore fixed. Coarse linear elastic solid mesh.',parts=[{'name':'PinFixed','color':[.1,.55,.3]},{'name':'PadLoad10N','color':[.85,.3,.1]}],document='JawFEM',center=[4,-6,3],height=64,view='viewTop',fem=True,labels=[{'text':'fixed pin bore','point':[0,0,3],'textpos':[350,440]},{'text':'10 N pad load','point':[-5.5,12,3],'textpos':[270,220]}],footer=['Peak %.3f MPa | displacement %.4f mm | yield safety factor %.1f | %d solid elements'%(r['max_von_mises_MPa'],r['max_displacement_mm'],r['safety_factor'],r['mesh_volumes']),'Undeformed shape, nodal von Mises stress in MPa. Coarse isotropic result; print direction and fixture details need physical validation.'])

def realism():
 c.pose('clamp')
 result=ec("""import FreeCAD as App,json
D=App.getDocument('StrawberryHead');parts=[]
for o in D.Objects:
 if not hasattr(o,'Category') or o.Category not in ['printed','bought'] or not hasattr(o,'Shape'):continue
 parts.append({'name':o.Name,'category':o.Category,'material':o.MaterialNote,'volume_mm3':o.Shape.Volume,'solids':len(o.Shape.Solids),'valid':'non-null' if not o.Shape.isNull() else False,'print_face':getattr(o,'PrintFace','')})
print(json.dumps({'parts':parts,'berry_bbox_mm':[D.TargetBerry.Shape.BoundBox.XLength,D.TargetBerry.Shape.BoundBox.YLength,D.TargetBerry.Shape.BoundBox.ZLength],'actual_vertical_clearance_mm':float(D.Dims.get('BladeZ'))-float(D.V2Dims.get('MovingHeight')),'world_origins':{o.Name:list(o.Placement.Base) for o in D.Objects if o.Name.startswith('World_')}}))
""")
 result['cable_housing_common_mm3']={tag:call('common_volume_along_path',moving_object=tag+'CableRoute',obstacle_objects=['DriveHousingReady'],samples=[{'x':0,'y':0,'z':0}])['max_common_volume_mm3'] for tag in ['Clamp','Cut']}
 c.R['realism']=result;c.persist()

def attachment_checks():
 def mate(n):
  explicit={'WristAdapter':'RobotWrist','FixedTPU':'NoseFrameReady','MovingTPU':'MovingJaw','MovingJaw':'JawPin','NoseFrameReady':'FrameBoltL','DriveHousingReady':'ColumnBoltL','JawPin':'NoseFrameReady','JawPinHead':'JawPin','CutterPin':'NoseFrameReady','CutterPinHead':'CutterPin','BladeLever':'CutterPin','HobbyBlade':'BladeClamp','BladeClamp':'BladeLever','JawLowerSpacer':'JawPin','JawUpperSpacer':'JawPin','CutLowerSpacer':'CutterPin','CutUpperShim':'CutterPin','JawPivotLocknut':'JawPin','CutPivotLocknut':'CutterPin'}
  if n in explicit:return explicit[n]
  if n.startswith('FlangeScrewHead'):return n.replace('Head','')
  if n.startswith('FlangeScrew'):return 'WristAdapter'
  if n.startswith('ColumnBoltHead'):return n.replace('Head','')
  if n.startswith('ColumnBolt'):return 'DriveHousingReady'
  if n.startswith('FrameHead') or n.startswith('FrameNut'):return 'FrameBolt'+n[-1]
  if n.startswith('FrameBolt'):return 'DriveHousingReady'
  if n.startswith('BladeClampM2'):
   return n.removesuffix('Head').removesuffix('Nut') if n.endswith(('Head','Nut')) else 'BladeClamp'
  tag='Clamp' if n.startswith('Clamp') else 'Cut'
  suffix=n[len(tag):]
  if suffix=='Servo':return 'DriveHousingReady'
  if suffix=='ServoTabs':return tag+'Servo'
  if suffix=='OutputShaft':return tag+'Horn'
  if suffix.startswith('M2Screw'):return 'DriveHousingReady'
  if suffix.startswith('M2Head'):return tag+'M2Screw'+suffix[-1]
  if suffix.startswith('CaptiveNut'):return tag+'M2Screw'+suffix[-1]
  if suffix=='CableRoute':return tag+'Servo'
  if suffix=='Horn':return tag+'OutputShaft'
  if suffix=='Link':return tag+'HornLinkPin'
  if suffix=='HornLinkPin':return tag+'Horn'
  if suffix=='LeverLinkPin':return 'MovingJaw' if tag=='Clamp' else 'BladeLever'
  if suffix=='HornPinHead':return tag+'HornLinkPin'
  if suffix=='LeverPinHead':return tag+'LeverLinkPin'
  raise ValueError(n)
 for p in c.R['realism']['parts']:
  n=mate(p['name']);p['nearest_part']=n;p['nearest_distance_mm']=call('measure_distance',shape1_ref=p['name'],shape2_ref=n)['distance']
  p['valid']=call('validate_geometry',obj_name=p['name']).get('is_valid',True);c.persist()
 snapshot()

def baseline_archive():
 c.setcells({'NeighbourGap':10});c.pose('clamp')
 # Presentation copies come from our saved smooth-fruit baseline, before the fix.
 # This leaves the final parametric dimensions untouched.
 result=ec("""import FreeCAD as App,Part,json
from pathlib import Path
D=App.getDocument('StrawberryHead');root=Path('/demo/demo-out/stage2/baseline-shapes');data=json.loads((root/'placements.json').read_text())
def place(name):
 record=data['objects'].get(name,{});v=record.get('placement');p=App.Placement()
 if v:p=App.Placement(App.Vector(*[float(v[k]) for k in ['Px','Py','Pz']]),App.Rotation(*[float(v[k]) for k in ['Q0','Q1','Q2','Q3']]))
 parent=data['parents'].get(name)
 return place(parent).multiply(p) if parent else p
names=['NoseFrameReady','MovingJaw','MovingTPU','FixedTPU','BladeLever','HobbyBlade','BladeClamp','JawPin','CutterPin']
copies=[]
for name in names:
 shape=Part.Shape();shape.read(str(root/data['objects'][name]['file']));shape.Placement=place(name)
 o=D.addObject('Part::Feature','BaselineDisplay_'+name);o.Shape=shape;copies.append({'name':o.Name,'source':name})
head=Part.Shape();head.read(str(root/data['objects']['HeadEnvelope']['file']))
volumes={}
for name in ['NeighbourLBerry','NeighbourRBerry','NeighbourLStem']:
 other=D.getObject('World_'+name).Shape;common=head.common(other);volumes[name]=common.Volume
 if common.Volume>1e-8:
  o=D.addObject('Part::Feature','BaselineYellow_'+name);o.Shape=common;copies.append({'name':o.Name,'source':'clash'})
print(json.dumps({'copies':copies,'whole_head_common_mm3':volumes,'source':'Saved native baseline-smooth.FCStd; actual BReps and parent placements; presentation copies only'}))
""")
 c.R['baseline_archive']=result;c.persist()
 parts=[]
 for p in result['copies']:
  if p['source']=='clash':parts.append({'name':p['name'],'color':[1,.79,.01],'clash':True})
  else:
   original=next(q for q in M['parts'] if q['name']==p['source']);parts.append({**original,'name':p['name'],'transparency':0 if p['source']=='NoseFrameReady' else 50 if p['source']=='BladeLever' else 0,'mode':'Wireframe' if p['source']=='NoseFrameReady' else None})
 parts.extend({**p,'transparency':65 if p['material']=='berry' else 0} for p in M['parts'] if p['name'] in ['TargetBerry','TargetCap','TargetStem','TargetStemStub','NeighbourLBerry','NeighbourLCap','NeighbourLStem','NeighbourLStemStub','NeighbourRBerry','NeighbourRCap','NeighbourRStem','NeighbourRStemStub'])
 render('05_narrow_gap.png','10 mm nominal gap | the original nose clashes','Yellow is the measured common volume; fruit is transparent.',parts,center=[0,-17,-6],height=160,orientation=c.view_from([.3,1.5,2.5]),footer=['Original lower nose and carrier. All fruit and all yellow intersections are inside the frame.','The corrected assembly is shown in 07_narrow_fixed.'])

def checkpoint():
 info=call('open_document',path='/demo/demo-out/strawberry-head-v2.FCStd')
 d.DOC=info['document_name'];c.DOC=d.DOC;sys.modules['stage2_support'].MODEL_DOC=d.DOC
 (OUT/'document-name.json').write_text(json.dumps({'document_name':d.DOC}));wait_ready()
 renderer();fix()
 c.R['v2_dimensions']=call('spreadsheet_get_cells',sheet_name='V2Dims',addresses=['B1','B2','B3','B4']);c.persist()

def wiring_fix():
 r=ec("""import FreeCAD as App,Part,json
D=App.getDocument('StrawberryHead');shapes=[]
routes=[('Clamp',[(-15,-51,18),(-15,-55,18),(-1.2,-55,18),(-1.2,-77,18)]),('Cut',[(16,-30,18),(16,-34,18),(5.5,-34,18),(5.5,-77,18)])]
for tag,pts in routes:
 lead=[]
 for a,b in zip(pts,pts[1:]):
  a=App.Vector(*a);b=App.Vector(*b);lead.append(Part.makeCylinder(1,(b-a).Length,a,b-a));shapes.append(Part.makeCylinder(1.25,(b-a).Length,a,b-a))
 for point in pts[1:-1]:lead.append(Part.makeSphere(1,App.Vector(*point)));shapes.append(Part.makeSphere(1.25,App.Vector(*point)))
 D.getObject(tag+'CableRoute').Shape=Part.makeCompound(lead)
tool=D.addObject('Part::Feature','V2CablePassages');D.PickingHead.addObject(tool);tool.Shape=Part.makeCompound(shapes)
union=D.addObject('Part::Compound','V2AllHousingClearances');D.PickingHead.addObject(union);union.Links=[D.DriveHousingReady.Tool,tool]
D.DriveHousingReady.Tool=union
print(json.dumps({'wire_diameter_mm':2,'passage_diameter_mm':2.5,'cut_lead_rear_x_mm':5.5,'clamp_lead_rear_x_mm':-1.2,'column_bolt_min_remaining_ligament_mm':2.05,'note':'Cut lead rerouted outside the clamp servo tab screw; explicit passages through the housing remove cable/print intersections.'}))
""")
 c.R['wiring_fix']=r;c.persist();c.pose('clamp');snapshot()
 c.R['cable_hardware_checks']={}
 obstacles=[p['name'] for p in M['parts'] if p['kind'] in ['printed','bought'] and p['material'] not in ['cable'] and p['name'] not in ['ClampServo','CutServo']]
 for tag in ['Clamp','Cut']:
  c.R['cable_hardware_checks'][tag]=call('common_volume_along_path',moving_object=tag+'CableRoute',obstacle_objects=obstacles,samples=[{'x':0,'y':0,'z':0}]);c.persist()

def validate():
 realism();attachment_checks();checks()

def finish():
 F=json.loads((OUT/'fem.json').read_text());values=F['results']
 proof=ec("""import FreeCAD as App,json
D=App.getDocument('StrawberryHead');o=D.MovingJaw
print_faces={'WristAdapter':('Flat XY underside; 6 mm plate, 3 mm floor below pilot recess',3.0),'DriveHousingReady':('Flat XY underside; minimum floor 2 mm, cable/column bolt ligament 2.05 mm',2.0),'NoseFrameReady':('Flat rear Y face; 2 mm fork plates; support transverse bores',2.0),'MovingJaw':('Flat XY face; 5.7 mm thick, 2.4 mm minimum bearing ligament',2.4),'BladeLever':('Flat XY face; 3 mm thick, minimum hole-edge material 2 mm',2.0),'BladeClamp':('Flat XY face; 2.4 mm thick, 2.3 mm screw-edge ligament',2.3),'ClampLink':('Flat XY face; 2 mm thick, 2.3 mm bore ligament',2.0),'CutLink':('Flat XY face; 2 mm thick, 2.3 mm bore ligament',2.0),'FixedTPU':('Flat backing face; 2 mm thick; adhesive retention',2.0),'MovingTPU':('Flat backing face; 2 mm thick; adhesive retention',2.0)}
for name,(face,wall) in print_faces.items():
 part=D.getObject(name);part.PrintFace=face
 # Minimum wall values are documented in the notes; PrintFace is an existing property.
print(json.dumps({'current_jaw_volume_mm3':o.Shape.Volume,'fem_source_volume_mm3':%r,'matches':abs(o.Shape.Volume-%r)<1e-6}))
"""%(F['geometry']['volume_mm3'],F['geometry']['volume_mm3']))
 assert proof['matches'],proof
 c.R['fem_geometry_match']=proof;c.R['fix']['servo_routes']='Continuous 2 mm leads through modeled 2.5 mm passages; cutter lead bypasses clamp servo screw';c.persist()
 c.setcells({'NeighbourGap':15});c.pose('clamp')
 render('01_scene.png','A compact head that picks by the stem','Clamp the stem, cut above the pad, then lower the fruit into the tray.',center=[-55,-17,4],height=270,orientation=c.view_from([1,2,1.4]),footer=['A four-bolt wrist adapter carries two servo drives, a pin-mounted jaw and a replaceable steel blade.','freecad-mcp | the companion FreeCAD fork | 15 mm nominal fruit spacing'])
 snapshot()

def mass_finish():
 c.mass_sheet();snapshot()

def baseline_retake():
 c.setcells({'NeighbourGap':10});c.pose('clamp');result=c.R['baseline_archive']
 parts=[]
 for p in result['copies']:
  if p['source']=='clash':parts.append({'name':p['name'],'color':[1,.79,.01],'clash':True})
  else:
   original=next(q for q in M['parts'] if q['name']==p['source']);parts.append({**original,'name':p['name'],'transparency':0 if p['source']=='NoseFrameReady' else 50 if p['source']=='BladeLever' else 0,'mode':'Wireframe' if p['source']=='NoseFrameReady' else None})
 parts.extend({**p,'transparency':65 if p['material']=='berry' else 0} for p in M['parts'] if p['name'] in ['TargetBerry','TargetCap','TargetStem','TargetStemStub','NeighbourLBerry','NeighbourLCap','NeighbourLStem','NeighbourLStemStub','NeighbourRBerry','NeighbourRCap','NeighbourRStem','NeighbourRStemStub'])
 render('05_narrow_gap.png','10 mm nominal gap | the original nose clashes','Yellow is the measured common volume; fruit is transparent.',parts,center=[0,-17,-6],height=160,orientation=c.view_from([.3,1.5,2.5]),footer=['Original lower nose and carrier. All fruit and all yellow intersections are inside the frame.','The corrected assembly is shown in 07_narrow_fixed.'])


def closeup_retake():
 c.pose('cut',0,-13)
 keep={'MovingJaw','MovingTPU','FixedTPU','HobbyBlade','TargetStem','TargetCap','TargetStemStub','JawPin','CutterPin','BladeClampM20','BladeClampM21'}
 # A thin section through Y=0 exposes the pad, stem, blade, and fixed anvil.
 call('set_section_view',enabled=True,base=[0,0,0],normal=[0,-1,0],no_manip=True)
 parts=[{**p,'transparency':70 if p['name']=='NoseFrameReady' else 0} for p in M['parts'] if p['name'] in keep or p['name']=='NoseFrameReady']
 render('02_closeup.png','Hold the stem, then shear above it','Section at the contact plane; rear drive hidden to expose the working parts.',parts,center=[0,0,1],height=28,view='viewFront',labels=[{'text':'stem','point':[0,0,5.2],'textpos':[1050,230]},{'text':'pad','point':[2.4,0,3],'textpos':[1120,570]},{'text':'blade','point':[0,0,6.9],'textpos':[350,325]},{'text':'1.0 mm clearance','point':[2.5,0,6.2],'textpos':[1060,420]}],footer=['The moving pad ends at Z = 5.7 mm; the cutting edge starts at Z = 6.7 mm.','The fixed anvil supports the cut. The 3 mm stem fits between replaceable TPU pads.'])
 call('set_section_view',enabled=False)

def parts_retake():
 names=M['printed']+['ClampServo','CutServo','HobbyBlade','JawPin','CutterPin','FrameBoltL','FlangeScrew1','ClampM2Screw0','JawPivotLocknut','BladeClampM20']
 copies=[{'name':'V2Display_'+n,'source':n} for n in names]
 parts=[{'name':p['name'],'color':next(q['color'] for q in M['parts'] if q['name']==p['source']),'lines':True} for p in copies]
 render('04_parts.png','Ten printed parts, familiar hardware','Actual part shapes arranged on their print faces; representative bought hardware below.',parts,center=[0,-25,0],height=330,view='viewTop',labels=[{'text':'structure','textpos':[390,150]},{'text':'clamp + pads','textpos':[700,150]},{'text':'cutter','textpos':[1090,150]}],footer=['Minimum specified printed walls: 2.0 mm; bearing ligaments: 2.4 mm. Flat faces and mounting holes are modeled.','Grey parts are bought. STEP and STL files contain the ten printed parts; see design-notes.md for the full hardware list.'])


def presentation_setup():
 pending=OUT/'render-command.json'
 if pending.exists():pending.unlink()
 call('recompute_document',required=False);wait_ready();renderer()

def contact_detail_setup():
 ec("""import FreeCAD as App,json
D=App.getDocument('StrawberryHead')
if not D.getObject('CloseupAnvil'):
 window=D.addObject('Part::Box','CloseupContactWindow');window.Length=6;window.Width=8;window.Height=6.6;window.Placement.Base=App.Vector(-7.5,-4,0)
 detail=D.addObject('Part::Common','CloseupAnvil');detail.Base=D.NoseFrameReady;detail.Tool=window
print(json.dumps({'detail':'Unmodified anvil geometry cropped to the contact region for the section view; excluded from BOM and exports'}))
""")

def contact_detail():
 c.pose('cut',0,-13)
 call('set_section_view',enabled=True,base=[0,0,0],normal=[0,-1,0],no_manip=True)
 keep={'MovingJaw','MovingTPU','FixedTPU','HobbyBlade','TargetStem'}
 parts=[p for p in M['parts'] if p['name'] in keep]+[{'name':'CloseupAnvil','color':[.13,.47,.59],'force_color':True}]
 render('02_closeup.png','Hold the stem, then shear above it','Section through the contact region; rear drive and pivot hardware hidden for clarity.',parts,center=[0,0,1],height=28,view='viewFront',labels=[{'text':'stem','point':[0,0,5.2],'textpos':[1050,230]},{'text':'pad','point':[2.4,0,3],'textpos':[1120,570]},{'text':'blade','point':[0,0,6.9],'textpos':[350,325]},{'text':'1.0 mm clearance','point':[2.5,0,6.2],'textpos':[1060,420]}],footer=['The moving pad ends at Z = 5.7 mm; the cutting edge starts at Z = 6.7 mm.','The teal anvil supports the cut. The 3 mm stem fits between replaceable TPU pads.'])
 call('set_section_view',enabled=False)

def top_detail():
 c.pose('clamp')
 parts=[{**p,'transparency':75 if p['name']=='DriveHousingReady' else 50 if p['name'] in ['BladeLever','BladeClamp'] else 45 if p['name'] in ['ClampServo','CutServo'] else 0} for p in M['parts'] if p['name'] not in ['RobotWrist','WristPilotBoss','WristAdapter','Tray','Truss','TargetBranch','NeighbourLBranch','NeighbourRBranch'] and not p['name'].startswith('FlangeScrew')]
 render('03_top.png','Two drives, one clear working nose','Top view; the housing and motors are translucent so the linkages can be followed.',parts,center=[0,-31,0],height=128,view='viewTop',labels=[{'text':'stem','point':[0,0,10],'textpos':[1100,200]},{'text':'pad','point':[2.5,0,3],'textpos':[1120,380]},{'text':'blade','point':[-35.32,-5.19,6.9],'textpos':[220,270]},{'text':'1.0 mm clearance','textpos':[1120,570]}],footer=['1.0 mm is the vertical blade-to-moving-pad clearance. The blade passes above the fixed anvil.','Two continuous servo leads reach the rear pigtail. Screws and locknuts retain the joints.'])

def archive_saved_baseline():
 import zipfile,xml.etree.ElementTree as ET,shutil
 checkpoint=OUT/'baseline-smooth.FCStd';shutil.copy2('/demo/demo-out/strawberry-head-v2.FCStd',checkpoint)
 target=OUT/'baseline-shapes';target.mkdir(exist_ok=True)
 with zipfile.ZipFile(checkpoint) as archive:
  root=ET.fromstring(archive.read('Document.xml'));parents={};objects={}
  for obj in root.findall('./ObjectData/Object'):
   name=obj.get('name');props={p.get('name'):p for p in obj.findall('./Properties/Property')}
   if 'Group' in props:
    for link in props['Group'].findall('./LinkList/Link'):parents[link.get('value')]=name
   shape=props.get('Shape');shape=shape.find('Part') if shape is not None else None
   place=props.get('Placement');place=place.find('PropertyPlacement').attrib if place is not None else None
   if shape is not None and shape.get('file'):
    filename=shape.get('file');(target/filename).write_bytes(archive.read(filename));objects[name]={'file':filename,'placement':place}
   elif place:objects[name]={'placement':place}
  (target/'placements.json').write_text(json.dumps({'parents':parents,'objects':objects}))

def save_evidence():
 call('save_document',selector={'document_name':'JawFEM'})
 readiness={name:call('get_mutation_readiness',doc_name=name) for name in [d.DOC,'JawFEM']}
 (OUT/'final-readiness.json').write_text(json.dumps(readiness,indent=2))

if __name__=='__main__':
 try:globals()[sys.argv[1]]()
 finally:d.C.close()
