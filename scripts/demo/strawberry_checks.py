"""Typed engineering calls and stage-1 stills; imports the existing stdio facade."""
from strawberry_driver import *
import ast, operator
M=json.loads((OUT/'design-manifest.json').read_text()) if (OUT/'design-manifest.json').exists() else {}
REPORT=OUT/'design-report.json'
R=json.loads(REPORT.read_text()) if REPORT.exists() else {}
def persist(): REPORT.write_text(json.dumps(R,indent=2))
_cell_cache={}
def setcells(values):
 changed={k:v for k,v in values.items() if _cell_cache.get(k)!=v}
 if not changed:return
 motion={k:v for k,v in changed.items() if k in M.get('motion_cells',{})}
 dims={k:v for k,v in changed.items() if k not in motion}
 if dims:call('spreadsheet_set_cells',sheet_name='Dims',cells=[{'address':M['cells'][k],'value':str(v)} for k,v in dims.items()])
 if motion:call('spreadsheet_set_cells',sheet_name='Motion',cells=[{'address':M['motion_cells'][k],'value':str(v)} for k,v in motion.items()])
 _cell_cache.update(changed)

def parameter(alias,default):
 raw={p['alias']:p['value'] for p in M.get('parameters',[])}
 ops={ast.Add:operator.add,ast.Sub:operator.sub,ast.Mult:operator.mul,ast.Div:operator.truediv,ast.Pow:operator.pow}
 def solve(k,seen):
  if k in seen:raise ValueError('circular parameter')
  node=ast.parse(str(raw[k]).lstrip('=').replace('Dims.','').replace('^','**'),mode='eval').body
  def ev(n):
   if isinstance(n,ast.Constant) and isinstance(n.value,(int,float)):return float(n.value)
   if isinstance(n,ast.Name):return solve(n.id,seen|{k})
   if isinstance(n,ast.UnaryOp) and isinstance(n.op,(ast.USub,ast.UAdd)):return -ev(n.operand) if isinstance(n.op,ast.USub) else ev(n.operand)
   if isinstance(n,ast.BinOp) and type(n.op) in ops:return ops[type(n.op)](ev(n.left),ev(n.right))
   raise ValueError('non-numeric parameter')
  return ev(node)
 try:return solve(alias,set())
 except (KeyError,ValueError,TypeError,SyntaxError):return default

def linkage(tag,a):
 prefix='JawRotor' if tag=='Clamp' else 'CutterRotor'
 px=parameter(prefix+'X',9 if tag=='Clamp' else -8)
 py=parameter(prefix+'Y',-12 if tag=='Clamp' else -3.5)
 sx=parameter(tag+'HornRotorX',-15 if tag=='Clamp' else 16)
 sy=parameter(tag+'HornRotorY',-45 if tag=='Clamp' else -24)
 arm=parameter('InputArm',24);r=parameter('HornRadius',6)
 L=parameter(tag+'LinkLength',math.hypot(24,3 if tag=='Clamp' else 2.5))
 ar=math.radians(a);fx=px+arm*math.sin(ar);fy=py-arm*math.cos(ar)
 dx,dy=fx-sx,fy-sy;d=math.hypot(dx,dy)
 phi=math.atan2(dy,dx);c=(d*d+r*r-L*L)/(2*d*r)
 if abs(c)>1:raise ValueError((tag,a,'unreachable',c))
 candidates=[phi+math.acos(c),phi-math.acos(c)]
 target=math.pi/2 if tag=='Clamp' else -math.pi/2
 theta=min(candidates,key=lambda t:abs(math.atan2(math.sin(t-target),math.cos(t-target))))
 hx,hy=sx+r*math.cos(theta),sy+r*math.sin(theta)
 la=math.atan2(fy-hy,fx-hx)
 outarm=parameter('JawOutputArm' if tag=='Clamp' else 'CutOutputArm',15 if tag=='Clamp' else 10.5)
 sinin=abs(math.sin(la-theta));sinout=abs(math.sin(la-(ar-math.pi/2)))
 force=parameter('WorkTorque',88)/r*arm/outarm*sinout/sinin
 return {tag+'ServoAngle':math.degrees(theta),tag+'LinkAngle':math.degrees(la)}, {'angle':a,'servo':math.degrees(theta),'force':force,'link_residual':abs(math.hypot(fx-hx,fy-hy)-L),'follower_pin':[fx,fy],'horn_pin':[hx,hy]}

def pose(name,ja=0,ca=13,hz=0,hy=0,target=False):
 values={'JawAngle':ja,'CutAngle':ca,'HeadZ':hz,'HeadY':hy,'TargetZ':hz if target else 0,'TargetY':hy if target else 0}
 if 'TargetStemLength' in M['cells']:values['TargetStemLength']=12.7 if name in ['cut','withdraw','tray'] else 30
 vals,jr=linkage('Clamp',ja); values.update(vals)
 vals,cr=linkage('Cut',ca); values.update(vals)
 setcells(values)
 if 'TargetStemLength' in M['cells']:show('PlantStemStub',name in ['cut','withdraw','tray'])
 code("import FreeCAD as App,Part\nd=App.getDocument('StrawberryHead')\nfor o in d.Objects:\n if o.TypeId=='PartDesign::Body' and o.Category in ['printed','bought'] and not o.Name.endswith('LeverLinkPin') and (o.Placement.Base.Length>1e-7 or abs(o.Placement.Rotation.Angle)>1e-7):o.Placement=App.Placement()\nfor name,aa in [('JawRotor','JawAngle'),('CutterRotor','CutAngle'),('ClampHornRotor','ClampServoAngle'),('CutHornRotor','CutServoAngle')]:\n xx=float(d.Dims.get(name+'X'));yy=float(d.Dims.get(name+'Y'))\n o=d.getObject(name);o.Placement=App.Placement(App.Vector(xx,yy,0),App.Rotation(App.Vector(0,0,1),float((d.getObject('Motion') or d.Dims).get(aa))))\nshapes=[]\nfor o in d.Objects:\n if hasattr(o,'Category') and o.Category in ['printed','bought'] and hasattr(o,'Shape'):\n  shape=o.Shape.copy(); shape.Placement=o.getGlobalPlacement(); shapes.append(shape)\nd.HeadEnvelope.Shape=Part.makeCompound(shapes)\nfor source in list(d.Objects):\n if source.Name not in ['TargetBerry','TargetCap','NeighbourLBerry','NeighbourLCap','NeighbourRBerry','NeighbourRCap','TargetStem','NeighbourLStem','NeighbourRStem','MovingJaw','ClampLink','BladeLever','CutLink','DriveHousingReady','NoseFrameReady','HobbyBlade','CutterPin','CutLowerSpacer','BladeClamp','NoseCheekL','NoseCheekR']:continue\n target=d.getObject('World_'+source.Name) or d.addObject('Part::Feature','World_'+source.Name)\n try:sig=str(source.Shape.hashCode())+str([round(v,8) for v in source.getGlobalPlacement().toMatrix().A])\n except Exception:sig=''\n cache=globals().setdefault('_design_world_cache',{})\n if sig and cache.get(target.Name)==sig:continue\n shape=source.Shape.copy();shape.Placement=source.getGlobalPlacement();target.Shape=shape;cache[target.Name]=sig\nprint('World-space validation compound and object proxies refreshed')")
 gui_batch(visible={**{'World_'+p['name']:False for p in M['parts']},'World_NoseCheekL':False,'World_NoseCheekR':False,'HeadEnvelope':False})
 return {'jaw':jr,'cut':cr}
def volume(name): return call('measure_volume',obj_name=name,required=False)
def common(a,b,label):
 res=call('boolean_intersection',shape1=a if a=='HeadEnvelope' else 'World_'+a,shape2=b if b=='HeadEnvelope' else 'World_'+b,result_name=label,required=False)
 if not events[-1]['result']['ok']:
  empty='EMPTY_BOOLEAN_RESULT' in str(res)
  return {'boolean':res,'volume':{'volume_mm3':0,'basis':'EMPTY_BOOLEAN_RESULT: empty common rolled back'} if empty else {}}
 v=volume(label); show(label,False)
 # Boolean tools can hide the sources. Keep physical parts visible.
 show('HeadEnvelope',False)
 return {'boolean':res,'volume':v}
def refine():
 values={'ClampHornHoleProfileX1':'=HornRadius','CutHornHoleProfileX1':'=HornRadius','MovingJawProfileY3':'=JawOutputArm','MovingJawProfileY4':'=JawOutputArm','CutterPinHolesProfileY1':'=-InputArm','CutterRotorX':'=-CutOutputArm','BeamDepth':3.5,'CableChannelLength':1,'MovingJawProfileY0':-27.5,'MovingJawProfileY1':-27.5}
 def quad(name,x0,x1,y0=None,y1=None):
  for n in [0,3]:values[name+'ProfileX'+str(n)]=x0
  for n in [1,2]:values[name+'ProfileX'+str(n)]=x1
  if y0 is not None:
   for n in [0,1]:values[name+'ProfileY'+str(n)]=y0
   for n in [2,3]:values[name+'ProfileY'+str(n)]=y1
 for i in range(1,5):
  values['FlangeScrew'+str(i)+'ProfileZ']=45
  values['FlangeScrewHead'+str(i)+'ProfileZ']=43
 for side,sign in [('L',-1),('R',1)]:
  quad('MountColumn'+side,sign*12-4,sign*12+4)
  values['MountColumn'+side+'ProfileZ']=16
  values['MountColumn'+side+'PadLength']=29
  values['MountColumn'+side+'BoltsProfileX0']=sign*12
  values['ColumnBolt'+side+'ProfileX0']=sign*12
  quad('NoseCheek'+side,-29 if side=='L' else 22,-22 if side=='L' else 29)
  values['NoseCheek'+side+'PadLength']=37
  values['CheekBolt'+side+'ProfileX0']=sign*25.5
  values['CheekM2'+side+'ProfileX0']=sign*25.5
 for tag in ['Clamp','Cut']:
  values[tag+'ServoPocketProfileZ']=16
  values[tag+'ServoPocketPadLength']=23
  quad(tag+'Link',-3.5,'= '+tag+'LinkLength + 3.5',-3.5,3.5)
 quad('FixedJaw',-9.5,-3.5)
 quad('FixedJawRoot',-9.5,-2.5)
 for i in range(2):values['FixedJawM2'+str(i)+'ProfileX0']=-6.5
 # The pilot and bolt circle now refer directly to the named interface cells.
 for name in ['FlangeBoltsProfileX0','FlangeScrew1ProfileX0','FlangeScrewHead1ProfileX0']:values[name]='=FlangePCD/2'
 for name in ['FlangeBoltsProfileX2','FlangeScrew3ProfileX0','FlangeScrewHead3ProfileX0']:values[name]='=-FlangePCD/2'
 for side in ['L','R']:
  values['CheekBolt'+side+'ProfileY0']=-12.5
  values['CheekM2'+side+'ProfileY0']=-12.5
 quad('BladeClamp',-27,-7,0,7)
 for i in range(2): values['BladeClampM2'+str(i)+'ProfileY0']=3.5
 for i in [0,6]: values['BladeLeverProfileX'+str(i)]=-4.5
 for i in [1,2,3]: values['BladeLeverProfileX'+str(i)]=4.5
 for i in [0,1]: values['BladeLeverProfileY'+str(i)]=-27.5
 setcells(values)
 code("import FreeCAD as App\nd=App.getDocument('StrawberryHead')\nfor o in d.Objects:\n if o.TypeId in ['PartDesign::Pad','PartDesign::Pocket']: o.setExpression('Length2','Length')\nprint('Unused second extrusion lengths are expression-driven too')")
 R['refinement']='6 mm M6 plate + 6 mm thread engagement; 7 mm wide printed links/cheeks; 2.3 mm minimum material around M2 clearance holes; minimum 3.5 mm jaw section in beam fallback.'
 persist()

def finish_parameters():
 values={'ClampHornHoleProfileX1':'=HornRadius','CutHornHoleProfileX1':'=HornRadius','MovingJawProfileY3':'=JawOutputArm','MovingJawProfileY4':'=JawOutputArm','CutterPinHolesProfileY1':'=-InputArm','CutterRotorX':'=-CutOutputArm'}
 def quad(name,x0,x1,y0,y1):
  for n,v in enumerate([x0,x1,x1,x0]):values[name+'ProfileX'+str(n)]=v
  for n,v in enumerate([y0,y0,y1,y1]):values[name+'ProfileY'+str(n)]=v
 for side in ['L','R']:
  values['CheekBolt'+side+'ProfileY0']=-12.5
  values['CheekM2'+side+'ProfileY0']=-12.5
 quad('BladeClamp',-27,-7,0,7)
 for i in range(2): values['BladeClampM2'+str(i)+'ProfileY0']=3.5
 for i in [0,6]: values['BladeLeverProfileX'+str(i)]=-4.5
 for i in [1,2,3]: values['BladeLeverProfileX'+str(i)]=4.5
 for i in [0,1]: values['BladeLeverProfileY'+str(i)]=-27.5
 setcells(values)


def plant():
 additions=[('TrussY',14),('TrussRise',4),('TrussZ',28),('TrussLength',120),('TargetStemLength',30),('CutHeight',6.7),('PlantStubZ',7.1),('PlantStubLength',16.9),('PilotRadialClearance',.1)]
 new=[]
 for alias,value in additions:
  row=len(M['parameters'])+1
  M['parameters'].append({'row':row,'alias':alias,'value':str(value),'description':alias})
  M['cells'][alias]='B'+str(row)
  new.extend([{'address':'A'+str(row),'value':alias},{'address':'B'+str(row),'value':str(value),'alias':alias}])
 call('spreadsheet_set_cells',sheet_name='Dims',cells=new)
 code("""import FreeCAD as App,math
D=App.getDocument('StrawberryHead')
D.Truss.setExpression('Placement.Base.y','Dims.TrussY')
D.Truss.setExpression('Placement.Base.z','Dims.TrussZ')
D.TargetStemPad.setExpression('Length','Dims.TargetStemLength')
for name,x in [('TargetBranch','0'),('NeighbourLBranch','-(Dims.BerryWidth + Dims.NeighbourGap)'),('NeighbourRBranch','Dims.BerryWidth + Dims.NeighbourGap')]:
 b=D.addObject('Part::Cylinder',name)
 b.setExpression('Radius','Dims.StemDia / 2')
 b.setExpression('Height','sqrt(Dims.TrussY^2 + Dims.TrussRise^2)')
 b.Placement=App.Placement(App.Vector(0,0,24),App.Rotation(App.Vector(-1,0,0),math.degrees(math.atan2(14,4))))
 b.setExpression('Placement.Base.x',x)
 b.setExpression('Placement.Base.z','Dims.TrussZ - Dims.TrussRise')
 b.setExpression('Placement.Rotation.Angle','atan2(Dims.TrussY, Dims.TrussRise)')
b=D.addObject('Part::Cylinder','PlantStemStub')
b.setExpression('Radius','Dims.StemDia / 2');b.setExpression('Height','Dims.PlantStubLength');b.setExpression('Placement.Base.z','Dims.PlantStubZ')
b=D.addObject('Part::Cylinder','WristPilotBoss')
b.setExpression('Radius','Dims.PilotDia / 2 - Dims.PilotRadialClearance');b.Height=7
b.Placement.Base=App.Vector(0,-65,48)
print('Connected truss branches, plant-side stub and wrist pilot added')
""")
 for n in ['TargetBranch','NeighbourLBranch','NeighbourRBranch','PlantStemStub','WristPilotBoss']:
  p={'name':n,'kind':'scene','material':'stem' if n!='WristPilotBoss' else 'wrist pilot','color':[.24,.46,.20] if n!='WristPilotBoss' else [.68,.74,.77]}
  M['parts'].append(p);M['scene'].append(n)
  call('set_color',obj_name=n,r=p['color'][0],g=p['color'][1],b=p['color'][2])
 show('PlantStemStub',False)
 (OUT/'design-manifest.json').write_text(json.dumps(M,indent=2))
 R['plant']='Truss offset to Y=14 mm with sloped pedicels; split target stem after cut; pilot boss mates to 31.5 mm adapter recess.'
 persist()

def motion_setup():
 state=call('get_mutation_readiness')
 while not state.get('ready',False):
  time.sleep(5);state=call('get_mutation_readiness')
 names=['HeadX','HeadY','HeadZ','JawAngle','CutAngle','ClampServoAngle','CutServoAngle','ClampLinkAngle','CutLinkAngle','TargetY','TargetZ','TargetStemLength']
 call('spreadsheet_create',sheet_name='Motion')
 cells=[]
 for i,n in enumerate(names,1):
  value=next(p['value'] for p in M['parameters'] if p['alias']==n)
  cells.extend([{'address':'A'+str(i),'value':n},{'address':'B'+str(i),'value':value,'alias':n}])
 call('spreadsheet_set_cells',sheet_name='Motion',cells=cells)
 code("""import FreeCAD as App
D=App.getDocument('StrawberryHead')
fields={'HeadX','HeadY','HeadZ','JawAngle','CutAngle','ClampServoAngle','CutServoAngle','ClampLinkAngle','CutLinkAngle','TargetY','TargetZ','TargetStemLength'}
count=0
for o in D.Objects:
 for prop,expr in list(o.ExpressionEngine):
  new=expr
  for name in fields:new=new.replace('Dims.'+name,'Motion.'+name)
  if new!=expr:o.setExpression(prop,new);count+=1
D.Motion.Label='Motion poses | mm and degrees | independent from static dimensions'
print('Moved '+str(count)+' placement/pose expressions to Motion spreadsheet; solid dimensions remain in Dims')
""")
 M['motion_cells']={n:'B'+str(i) for i,n in enumerate(names,1)}
 (OUT/'design-manifest.json').write_text(json.dumps(M,indent=2))
 R['motion_sheet']='Pose controls use a separate Motion spreadsheet so kinematic checks do not rebuild every printed feature. Dims retains the static dimensions and force calculations.'
 persist()

def manufacture():
 source=(ROOT/'scripts/demo/strawberry_model.py').read_text()
 header=source[:source.index('inputs=')]
 helpers=source[source.index('def body('):source.index('# Mount:')]
 setup='\nrow='+str(len(M['parameters']))+'\nnumeric={p["alias"]:float(S.get(p["alias"])) for p in '+repr(M['parameters'])+'}\n'
 action="""
b=D.FixedJaw
sk=poly_sketch(b,'IntegralFixedRootProfile',[(-9.5,-13),(-2.5,-13),(-2.5,-7),(-9.5,-7)],0)
feature(b,sk,'IntegralFixedRoot',11)
b=D.MovingJaw
sk=poly_sketch(b,'IntegralBackingProfile',[(-5.5,8),(-2.5,8),(-2.5,16),(-5.5,16)],0)
feature(b,sk,'IntegralBacking',6)
holes(D.WristAdapter,'ColumnTappedBores',[(12,-60,1.25),(-12,-60,1.25)],48,3)
D.FixedJawRoot.Category='reference'; D.PadBacking.Category='reference'
D.FixedJaw.Label='Fixed jaw with integral mounting root'
D.MovingJaw.Label='Moving jaw with integral pad backing'
print(json.dumps({'new_parameters':params,'last_row':row}))
"""
 result=code(header+setup+helpers+action)
 added=output_json(result)
 M['parameters']+=added['new_parameters']
 M['cells'].update({p['alias']:'B'+str(p['row']) for p in added['new_parameters']})
 M['printed']=[n for n in M['printed'] if n not in ['FixedJawRoot','PadBacking']]
 M['parts']=[p for p in M['parts'] if p['name'] not in ['FixedJawRoot','PadBacking']]
 (OUT/'design-manifest.json').write_text(json.dumps(M,indent=2))
 gui_batch(M['parts'],visible={'FixedJawRoot':False,'PadBacking':False,'HeadEnvelope':False,'Joints':False})
 R['manufacturing']='Fixed jaw root and moving pad backing are integral native additive features, not separate floating printed parts. Adapter has two 2.5 mm M3 tapping bores for column bolts. TPU cartridges use replaceable adhesive backing; adhesive film omitted from the simplified bought-part geometry.'
 persist()
 geometry()
 # Refresh references after the additive features changed the final tip faces.
 for n in ['Joint','Joint001']:call('delete_object',obj_name=n,force=True,required=False)
 def cyl(name):return next(f['name'] for f in R['geometry'][name]['faces'] if f['type']=='Cylinder' and (name not in ['MovingJaw','BladeLever'] or abs(f['center'][1])<2) and (name!='BladeLever' or abs(f['center'][0])<2))
 for tag,support,rotor,bname in [('jaw','JawForkLower','JawRotor','MovingJaw'),('cutter','CutterForkLower','CutterRotor','BladeLever')]:
  result=call('create_assembly_joint',assembly_name='PickingHead',joint_type='Revolute',ref1_component=support,ref2_component=rotor,ref1_element=cyl(support),ref2_element=bname+'.'+cyl(bname),label=tag+' revolute M3',solve=False,presolve=False)
  f1=next(f for f in R['geometry'][support]['faces'] if f['name']==cyl(support))
  f2=next(f for f in R['geometry'][bname]['faces'] if f['name']==cyl(bname))
  edit(result['joint'],Offset2={'Base':{'z':f1['center'][2]-f2['center'][2]}})
  R['assembly'][tag]=result
 R['assembly']['solve_after_manufacturing']=call('solve_assembly',assembly_name='PickingHead',required=False)
 gui_batch(visible={'Joints':False})
 pose('clamp')
 persist()

def final_mechanics():
 source=(ROOT/'scripts/demo/strawberry_model.py').read_text()
 header=source[:source.index('inputs=')]
 helpers=source[source.index('def body('):source.index('# Mount:')]
 setup='\nrow='+str(len(M['parameters']))+'\nnumeric={p["alias"]:float(S.get(p["alias"])) for p in '+repr(M['parameters'])+'}\n'
 action="""
# A single printed housing and a single printed nose remove assembly overlaps.
for name,value in [('ChassisProfileY0',-69),('ChassisProfileY1',-69),('CableChannelProfileY0',-69),('CableChannelProfileY1',-69),('BladeLeverProfileY3',7),('BladeLeverProfileY4',7),('CutterPinHolesProfileY2',3.5),('CutterPinHolesProfileY3',3.5),('IntegralFixedRootProfileY0',-16),('IntegralFixedRootProfileY1',-16),('JawForkLowerProfileX1',16),('JawForkLowerProfileX2',16),('JawForkUpperProfileX1',16),('JawForkUpperProfileX2',16)]:
 S.set(S.getCellFromAlias(name),str(value));numeric[name]=value
for tag in ['Clamp','Cut']:
 for i in range(2):
  for suffix,value in [('ProfileZ',14),('PadLength',20)]:S.set(S.getCellFromAlias(tag+'M2Screw'+str(i)+suffix),str(value))
# Factory tang-slot envelope and actual clamping-screw holes.
holes(D.BladeClamp,'BladeClampBores',[(-21,3.5,1.2),(-12,3.5,1.2)],6.7,3)
rectpocket(D.HobbyBlade,'BladeTangSlot',-25,2.3,16,2.4,7.1,1)
post=box('JawSupportPost',13,-16,-3,3,4,14)
post.Category='reference'
# Captive nuts in pockets open to the motor cavity; no nut protrudes into links.
for tag,cx,cy in [('Clamp',-15,-45),('Cut',16,-24)]:
 for i,sgn in enumerate([-1,1]):
  x=cx+sgn*14.8
  left=x-2.2 if sgn<0 else cx+11.55
  width=(cx-11.55-left) if sgn<0 else (x+2.2-left)
  rectpocket(D.getObject(tag+'ServoPocket'),tag+'NutTrap'+str(i),left,cy-2.4,width,4.8,18.2,2.4)
# Through bolts attach the printed nose to the printed drive housing.
for b,z in [(D.NoseBridge,13),(D.Chassis,16)]:
 holes(b,b.Name+'FrameMount',[(18.5,-12.5,1.2),(-18.5,-12.5,1.2)],z,4)
frame_names=['NoseCheekL','NoseCheekR','NoseBridge','FixedJaw','JawForkLower','JawForkUpper','CutterForkLower','CutterForkUpper','JawSupportPost']
housing_names=['Chassis','ClampServoPocket','CutServoPocket','MountColumnL','MountColumnR']
for name,refs in [('NoseFrame',frame_names),('DriveHousing',housing_names)]:
 o=D.addObject('Part::MultiFuse',name);D.PickingHead.addObject(o);o.Shapes=[D.getObject(n) for n in refs]
 o.Refine=True
 o.addProperty('App::PropertyString','Category','BOM');o.Category='printed'
 o.addProperty('App::PropertyString','MaterialNote','BOM');o.MaterialNote='PLA'
 o.addProperty('App::PropertyString','PrintFace','BOM');o.PrintFace='Nose: rear Y=-16 plane; housing: underside XY plane; use support for transverse bores'
 for n in refs:D.getObject(n).Category='reference'
for n in ['CheekM2L','CheekM2R']:D.getObject(n).Category='reference'
cell('NutRadius',2.2);cell('NutHeight',2);cell('FrameBoltX',18.5);cell('FrameBoltY',-12.5);cell('FrameBoltLength',12);cell('M2HeadRadius',1.9);cell('M2HeadHeight',1.2)
new_bought=[]
def hardware(name,x,y,z,r,h):
 o=D.addObject('Part::Cylinder',name);D.PickingHead.addObject(o)
 o.addProperty('App::PropertyString','Category','BOM');o.Category='bought'
 o.addProperty('App::PropertyString','MaterialNote','BOM');o.MaterialNote='steel'
 for prop,v in [('Radius',r),('Height',h),('Placement.Base.x',x),('Placement.Base.y',y),('Placement.Base.z',z)]:o.setExpression(prop,v)
 new_bought.append(name)
for tag in ['Clamp','Cut']:
 for i in range(2):hardware(tag+'CaptiveNut'+str(i),'Dims.'+tag+'M2Screw'+str(i)+'ProfileX0','Dims.'+tag+'M2Screw'+str(i)+'ProfileY0','Dims.ChassisProfileZ + Dims.ChassisPadLength','Dims.NutRadius','Dims.NutHeight')
for side,sgn in [('L','-'),('R','')]:
 x=sgn+'Dims.FrameBoltX';y='Dims.FrameBoltY';top='Dims.ChassisProfileZ + Dims.ChassisPadLength'
 hardware('FrameBolt'+side,x,y,top+' - Dims.FrameBoltLength','Dims.M2Clear / 2 - 0.2','Dims.FrameBoltLength')
 hardware('FrameHead'+side,x,y,top,'Dims.M2HeadRadius','Dims.M2HeadHeight')
 hardware('FrameNut'+side,x,y,'Dims.NoseBridgeProfileZ - Dims.NutHeight','Dims.NutRadius','Dims.NutHeight')
print(json.dumps({'new_parameters':params,'frame_sources':frame_names,'housing_sources':housing_names,'bought':new_bought}))
"""
 result=code(header+setup+helpers+action)
 added=output_json(result)
 M['parameters']+=added['new_parameters'];M['cells'].update({p['alias']:'B'+str(p['row']) for p in added['new_parameters']})
 removed=set(added['frame_sources']+added['housing_sources']+['CheekM2L','CheekM2R'])
 M['parts']=[p for p in M['parts'] if p['name'] not in removed]
 M['printed']=[n for n in M['printed'] if n not in removed]
 M['bought']=[n for n in M['bought'] if n not in removed]
 for n in ['NoseFrame','DriveHousing']:
  M['parts'].append({'name':n,'kind':'printed','material':'PLA','color':[.13,.47,.59]});M['printed'].append(n)
 for n in added['bought']:
  M['parts'].append({'name':n,'kind':'bought','material':'steel','color':[.59,.62,.65]});M['bought'].append(n)
 (OUT/'design-manifest.json').write_text(json.dumps(M,indent=2))
 gui_batch(M['parts'],visible={**{n:False for n in removed},'FixedJawRoot':False,'PadBacking':False,'JawSupportPost':False,'HeadEnvelope':False,'Joints':False})
 R['final_mechanics']='Nose and drive housing are each one printed fusion of expression-driven native pad/pocket bodies. M2x20 servo fasteners use captive nuts inside the housing, clear of link motion. Two M2x12 through bolts and nuts attach nose to housing. Blade clamp bores align with the represented tang slot.'
 R['fusion_validation']={n:call('validate_geometry',obj_name=n,required=False) for n in ['NoseFrame','DriveHousing']}
 pose('clamp')
 persist()

def recover_current():
 state=call('get_mutation_readiness')
 while not state.get('ready',False):
  time.sleep(5);state=call('get_mutation_readiness')
 data=code("""import FreeCAD as App,json
D=App.getDocument('StrawberryHead');S=D.Dims
params=[]
for i in range(1,6000):
 a='B'+str(i);v=S.getContents(a)
 if not v:break
 params.append({'row':i,'alias':S.getAlias(a),'value':v,'description':S.getContents('A'+str(i))})
parts=[];refs=[]
for o in D.Objects:
 if not hasattr(o,'Category'):continue
 if o.Category=='reference':refs.append(o.Name);continue
 if o.Category not in ['printed','bought']:continue
 color=[.59,.62,.65] if o.Category=='bought' else [.13,.47,.59]
 if o.MaterialNote=='TPU':color=[.22,.68,.57]
 elif o.Category=='printed' and any(k in o.Name for k in ['MovingJaw','ClampLink']):color=[.94,.62,.20]
 elif o.Category=='printed' and any(k in o.Name for k in ['Blade','CutLink']):color=[.43,.38,.65]
 parts.append({'name':o.Name,'kind':o.Category,'material':o.MaterialNote,'color':color})
print(json.dumps({'parameters':params,'parts':parts,'references':refs}))
""")
 recovered=output_json(data)
 M['parameters']=recovered['parameters'];M['cells']={p['alias']:'B'+str(p['row']) for p in M['parameters']}
 M['parts']=recovered['parts']+[p for p in M['parts'] if p['kind']=='scene']
 M['printed']=[p['name'] for p in M['parts'] if p['kind']=='printed'];M['bought']=[p['name'] for p in M['parts'] if p['kind']=='bought']
 M['references']=recovered['references']
 (OUT/'design-manifest.json').write_text(json.dumps(M,indent=2))
 R['final_mechanics']='Single printed nose frame and drive housing, captive M2x20 servo fasteners, M2x12 nose through bolts, and screw-clamped blade tang slot.'
 persist()

def pivot_finish():
 source=(ROOT/'scripts/demo/strawberry_model.py').read_text()
 header=source[:source.index('inputs=')]
 setup='\nrow='+str(len(M['parameters']))+'\nnumeric={p["alias"]:float(S.get(p["alias"])) for p in '+repr(M['parameters'])+'}\n'
 action="""
# Offset the blade from the pivot so steel, pin, spacers and clips cannot overlap.
updates={'CutPivotY':-3.5,'CutterRotorY':'=CutPivotY','CutterRotorX':'=CutPivotX','CutOutputArm':10.5,'CutLinkLength':(24**2+2.5**2)**.5,'HobbyBladeProfileX1':'=CutOutputArm','HobbyBladeProfileX0':'=-BladeLength+CutOutputArm','HobbyBladeProfileX3':'=-BladeLength+CutOutputArm','BladeLeverProfileY3':10.5,'BladeLeverProfileY4':10.5,'BladeClampProfileY0':3.5,'BladeClampProfileY1':3.5,'BladeClampProfileY2':10.5,'BladeClampProfileY3':10.5,'BladeTangSlotProfileY0':5.8,'BladeTangSlotProfileY1':5.8,'BladeTangSlotProfileY2':8.2,'BladeTangSlotProfileY3':8.2,'CutterPinHolesProfileY2':7,'CutterPinHolesProfileY3':7,'BladeClampBoresProfileY0':7,'BladeClampBoresProfileY1':7,'BladeClampM20ProfileY0':7,'BladeClampM21ProfileY0':7,'CutterPinProfileY0':-3.5,'CutterPinHeadProfileY0':-3.5,'CutterForkHoleLowerProfileY0':-3.5,'CutterForkHoleUpperProfileY0':-3.5}
for i in [0,1]:updates['HobbyBladeProfileY'+str(i)]=3.5
for i in [2,3]:updates['HobbyBladeProfileY'+str(i)]=9.5
for n,v in updates.items():S.set(S.getCellFromAlias(n),str(v))
D.PickingHead.addObject(D.JawSupportPost)
for n in ['FixedJawM20','FixedJawM21']:D.getObject(n).Category='reference'
cell('ClipRadius',3);cell('ClipThickness',.4);cell('ClipClearance',.2);cell('SpacerRadius',2.4)
new_bought=[]
def hardware(name,x,y,z,r,h):
 o=D.addObject('Part::Cylinder',name);D.PickingHead.addObject(o)
 o.addProperty('App::PropertyString','Category','BOM');o.Category='bought'
 o.addProperty('App::PropertyString','MaterialNote','BOM');o.MaterialNote='steel'
 for p,e in [('Radius',r),('Height',h),('Placement.Base.x',x),('Placement.Base.y',y),('Placement.Base.z',z)]:o.setExpression(p,e)
 new_bought.append(name)
for tag,pin,fork in [('Jaw','JawPin','JawForkUpper'),('Cut','CutterPin','CutterForkUpper')]:
 hardware(tag+'RetainingClip','Dims.'+pin+'ProfileX0','Dims.'+pin+'ProfileY0','Dims.'+fork+'ProfileZ + Dims.'+fork+'PadLength + Dims.ClipClearance','Dims.ClipRadius','Dims.ClipThickness')
for name,pin,z,h in [('JawLowerSpacer','JawPin','Dims.JawForkLowerProfileZ + Dims.JawForkLowerPadLength','Dims.MovingJawProfileZ - (Dims.JawForkLowerProfileZ + Dims.JawForkLowerPadLength)'),('JawUpperSpacer','JawPin','Dims.MovingJawProfileZ + Dims.MovingJawPadLength','Dims.JawForkUpperProfileZ - (Dims.MovingJawProfileZ + Dims.MovingJawPadLength)'),('CutLowerSpacer','CutterPin','Dims.CutterForkLowerProfileZ + Dims.CutterForkLowerPadLength','Dims.BladeLeverProfileZ - (Dims.CutterForkLowerProfileZ + Dims.CutterForkLowerPadLength)'),('CutUpperShim','CutterPin','Dims.BladeLeverProfileZ + Dims.BladeLeverPadLength','Dims.CutterForkUpperProfileZ - (Dims.BladeLeverProfileZ + Dims.BladeLeverPadLength)')]:
 hardware(name,'Dims.'+pin+'ProfileX0','Dims.'+pin+'ProfileY0',z,'Dims.SpacerRadius',h)
print(json.dumps({'new_parameters':params,'new_bought':new_bought}))
"""
 result=code(header+setup+action)
 added=output_json(result)
 M['parameters']+=added['new_parameters'];M['cells'].update({p['alias']:'B'+str(p['row']) for p in added['new_parameters']})
 for n in ['FixedJawM20','FixedJawM21']:
  M['parts']=[p for p in M['parts'] if p['name']!=n];M['bought']=[v for v in M['bought'] if v!=n]
 for n in added['new_bought']:
  M['parts'].append({'name':n,'kind':'bought','material':'steel','color':[.59,.62,.65]});M['bought'].append(n)
 (OUT/'design-manifest.json').write_text(json.dumps(M,indent=2))
 R['pivot_clearance']='Blade edge offset 3.5 mm from pivot; pin at (-8,-3.5), 8.73 mm from stem centre. Budget uses conservative 10.5 mm outer cutting reach. Steel spacers and retaining clips locate both rotating members axially.'
 persist()
 gui_batch(M['parts'],visible={**{n:False for n in M.get('references',[])},'FixedJawM20':False,'FixedJawM21':False,'HeadEnvelope':False,'Joints':False})
 R['fusion_validation']={n:call('validate_geometry',obj_name=n,required=False) for n in ['NoseFrame','DriveHousing']}
 pose('clamp')
 R['assembly']['solve_final']=call('solve_assembly',assembly_name='PickingHead',required=False)
 pose('clamp')
 persist()

def bore_finish():
 source=(ROOT/'scripts/demo/strawberry_model.py').read_text()
 header=source[:source.index('inputs=')]
 setup='\nrow='+str(len(M['parameters']))+'\nnumeric={p["alias"]:float(S.get(p["alias"])) for p in '+repr(M['parameters'])+'}\n'
 action="""
# Machine-ready bores are cut after structural unions so no overlapping source
# can fill another source's pivot hole. Provide 0.2 mm axial running clearance.
updates={'FixedJawProfileX0':-12,'FixedJawProfileX3':-12,'IntegralFixedRootProfileX0':-12,'IntegralFixedRootProfileX3':-12,'IntegralFixedRootLength':13,'JawPinPadLength':25,'CutterPinProfileZ':0,'CutterPinPadLength':20,'CutterPinHeadProfileZ':-1.5}
for n,v in updates.items():S.set(S.getCellFromAlias(n),str(v))
cell('PivotBoreHeight',24);cell('PivotBoreBottom',-6);cell('AxleAccessRadius',3.4);cell('AxleAccessHeight',3.1);cell('AxialClearance',.2);cell('LockNutRadius',3.2);cell('LockNutHeight',4)
refs=[];new_bought=[]
def cyl(name,x,y,z,r,h,kind='reference'):
 o=D.addObject('Part::Cylinder',name);D.PickingHead.addObject(o)
 o.addProperty('App::PropertyString','Category','BOM');o.Category=kind
 o.addProperty('App::PropertyString','MaterialNote','BOM');o.MaterialNote='steel' if kind=='bought' else 'construction'
 for p,e in [('Radius',r),('Height',h),('Placement.Base.x',x),('Placement.Base.y',y),('Placement.Base.z',z)]:o.setExpression(p,e)
 (new_bought if kind=='bought' else refs).append(name)
 return o
for tag,pin in [('Jaw','JawPin'),('Cut','CutterPin')]:
 cyl(tag+'PivotBore','Dims.'+pin+'ProfileX0','Dims.'+pin+'ProfileY0','Dims.PivotBoreBottom','Dims.M3Clear / 2','Dims.PivotBoreHeight')
slot=D.addObject('Part::Box','CutterArmRelief');D.PickingHead.addObject(slot)
slot.addProperty('App::PropertyString','Category','BOM');slot.Category='reference'
for name,value in [('ArmSlotX',-18),('ArmSlotY',-16),('ArmSlotZ',7),('ArmSlotLength',21),('ArmSlotWidth',9.5),('ArmSlotHeight',3.5)]:cell(name,value)
for p,e in [('Length','ArmSlotLength'),('Width','ArmSlotWidth'),('Height','ArmSlotHeight'),('Placement.Base.x','ArmSlotX'),('Placement.Base.y','ArmSlotY'),('Placement.Base.z','ArmSlotZ')]:slot.setExpression(p,'Dims.'+e)
refs.append(slot.Name)
tools=D.addObject('Part::Compound','NoseClearanceTools');D.PickingHead.addObject(tools);tools.Links=[D.JawPivotBore,D.CutPivotBore,slot]
tools.addProperty('App::PropertyString','Category','BOM');tools.Category='reference';refs.append(tools.Name)
access=cyl('JawAxleAccess','Dims.JawPinProfileX0','Dims.JawPinProfileY0','Dims.ChassisProfileZ','Dims.AxleAccessRadius','Dims.AxleAccessHeight')
for name,base,tool in [('NoseFrameReady','NoseFrame',tools),('DriveHousingReady','DriveHousing',access)]:
 o=D.addObject('Part::Cut',name);D.PickingHead.addObject(o);o.Base=D.getObject(base);o.Tool=tool;o.Refine=True
 o.addProperty('App::PropertyString','Category','BOM');o.Category='printed'
 o.addProperty('App::PropertyString','MaterialNote','BOM');o.MaterialNote='PLA'
 o.addProperty('App::PropertyString','PrintFace','BOM');o.PrintFace='Flat rear face for nose; flat XY underside for housing; support transverse holes'
 D.getObject(base).Category='reference';refs.append(base)
# Replace clip envelopes with stock locking-nut envelopes on M3x25/M3x20 pivots.
for n in ['JawRetainingClip','CutRetainingClip']:D.getObject(n).Category='reference';refs.append(n)
for tag,pin,z in [('Jaw','JawPin','Dims.NoseBridgeProfileZ + Dims.NoseBridgePadLength'),('Cut','CutterPin','Dims.CutterForkUpperProfileZ + Dims.CutterForkUpperPadLength')]:
 cyl(tag+'PivotLocknut','Dims.'+pin+'ProfileX0','Dims.'+pin+'ProfileY0',z,'Dims.LockNutRadius','Dims.LockNutHeight','bought')
D.JawUpperSpacer.setExpression('Height','Dims.JawForkUpperProfileZ - (Dims.MovingJawProfileZ + Dims.MovingJawPadLength) - Dims.AxialClearance')
D.CutLowerSpacer.setExpression('Placement.Base.z','Dims.FixedJawProfileZ + Dims.FixedJawPadLength')
D.CutLowerSpacer.setExpression('Height','Dims.BladeLeverProfileZ - (Dims.FixedJawProfileZ + Dims.FixedJawPadLength)')
D.CutUpperShim.setExpression('Height','Dims.CutterForkUpperProfileZ - (Dims.BladeLeverProfileZ + Dims.BladeLeverPadLength) - Dims.AxialClearance')
print(json.dumps({'new_parameters':params,'bought':new_bought,'references':refs}))
"""
 result=code(header+setup+action)
 added=output_json(result)
 M['parameters']+=added['new_parameters'];M['cells'].update({p['alias']:'B'+str(p['row']) for p in added['new_parameters']})
 removed=set(added['references'])
 M['parts']=[p for p in M['parts'] if p['name'] not in removed]
 M['printed']=[n for n in M['printed'] if n not in removed];M['bought']=[n for n in M['bought'] if n not in removed]
 M['references']=list(set(M.get('references',[]))|removed)
 for n in ['NoseFrameReady','DriveHousingReady']:
  M['parts'].append({'name':n,'kind':'printed','material':'PLA','color':[.13,.47,.59]});M['printed'].append(n)
 for n in added['bought']:
  M['parts'].append({'name':n,'kind':'bought','material':'steel','color':[.59,.62,.65]});M['bought'].append(n)
 (OUT/'design-manifest.json').write_text(json.dumps(M,indent=2))
 gui_batch(M['parts'],visible={**{n:False for n in M['references']},'HeadEnvelope':False,'Joints':False})
 pose('clamp')
 R['fusion_validation']={n:call('validate_geometry',obj_name=n,required=False) for n in ['NoseFrameReady','DriveHousingReady']}
 R['pivot_clearance']='Blade offset 3.5 mm from M3 pivot, 10.5 mm conservative cutting reach; post-union pivot bores, arm-relief window, standard M3x25/M3x20 axle screws with locking nuts and 0.2 mm axial clearance.'
 persist()

def final_clearance():
 rows=[]
 for alias,value in [('NoseRearSpine',3),('NoseSlotBottom',3.8)]:
  if alias in M['cells']:continue
  row=len(M['parameters'])+1;M['parameters'].append({'row':row,'alias':alias,'value':str(value),'description':alias});M['cells'][alias]='B'+str(row)
  rows.extend([{'address':'A'+str(row),'value':alias},{'address':'B'+str(row),'value':str(value),'alias':alias}])
 if rows:call('spreadsheet_set_cells',sheet_name='Dims',cells=rows)
 code("""import FreeCAD as App
D=App.getDocument('StrawberryHead')
D.JawAxleAccess.setExpression('Height','Dims.LockNutHeight + Dims.AxialClearance')
new=[]
for name,props in [('LeftShankRoofClearance',{'Length':'Dims.ArmSlotX - (Dims.NoseCheekLProfileX0 - Dims.M2Clear/2)','Width':'(Dims.ArmSlotY + Dims.ArmSlotWidth) - (Dims.NoseCheekLProfileY0 + Dims.NoseRearSpine)','Height':'Dims.ArmSlotHeight','Placement.Base.x':'Dims.NoseCheekLProfileX0 - Dims.M2Clear/2','Placement.Base.y':'Dims.NoseCheekLProfileY0 + Dims.NoseRearSpine','Placement.Base.z':'Dims.ArmSlotZ'}),('LeftNoseBladeWindow',{'Length':'Dims.NoseCheekLProfileX1 - Dims.NoseCheekLProfileX0 + Dims.M2Clear','Width':'Dims.NoseCheekLProfileY2 - (Dims.NoseCheekLProfileY0 + Dims.NoseRearSpine) + Dims.M2Clear/2','Height':'Dims.ArmSlotZ + Dims.ArmSlotHeight - Dims.NoseSlotBottom','Placement.Base.x':'Dims.NoseCheekLProfileX0 - Dims.M2Clear/2','Placement.Base.y':'Dims.NoseCheekLProfileY0 + Dims.NoseRearSpine','Placement.Base.z':'Dims.NoseSlotBottom'})]:
 o=D.addObject('Part::Box',name);D.PickingHead.addObject(o)
 o.addProperty('App::PropertyString','Category','BOM');o.Category='reference'
 for p,e in props.items():o.setExpression(p,e)
 new.append(o)
tool=D.addObject('Part::MultiFuse','NoseClearanceUnion');D.PickingHead.addObject(tool)
tool.Shapes=list(D.NoseClearanceTools.Links)+new;tool.Refine=True
 tool_marker=True
""".replace(' tool_marker=True','tool.addProperty("App::PropertyString","Category","BOM");tool.Category="reference"\nD.NoseFrameReady.Tool=tool\nprint("Left nose relief preserves a 3 mm rear spine; fruit-facing outline is unchanged")'))
 M['references']=list(set(M.get('references',[]))|{'LeftShankRoofClearance','LeftNoseBladeWindow','NoseClearanceUnion'})
 (OUT/'design-manifest.json').write_text(json.dumps(M,indent=2))
 gui_batch(M['parts'],visible={**{n:False for n in M['references']},'HeadEnvelope':False,'Joints':False})
 pose('clamp')
 R['fusion_validation']={n:call('validate_geometry',obj_name=n,required=False) for n in ['NoseFrameReady','DriveHousingReady']}
 R['nominal_frozen']='Nominal design frozen after pivot bores, blade/arm relief, standard pivot fasteners and axial spacers. Lower nose outside outline remains X=±29 mm and is deliberately retained for the 10 mm neighbour case.'
 persist()


def validate_freeze():
 state=call('get_mutation_readiness')
 while not state.get('ready',False):time.sleep(5);state=call('get_mutation_readiness')
 gui_batch(M['parts'],visible={**{n:False for n in M.get('references',[])},**{'World_'+p['name']:False for p in M['parts']},'World_NoseCheekL':False,'World_NoseCheekR':False,'HeadEnvelope':False,'Joints':False})
 pose('clamp')
 R['fusion_validation']={n:call('validate_geometry',obj_name=n,required=False) for n in ['NoseFrameReady','DriveHousingReady']}
 R['force_cells']=call('spreadsheet_get_cells',sheet_name='Dims',addresses=[M['cells'][n] for n in ['StallTorque','TorqueSafety','WorkTorque','HornRadius','InputArm','JawOutputArm','CutOutputArm','ClampForce','CutForce','ClampMargin','CutMargin']])
 R['nominal_frozen']='Nominal structure has post-union pivot bores and arm/blade relief. Outer lower nose remains at X=±29 mm, deliberately unchanged for the 10 mm case.'
 call('save_document',selector={'document_name':DOC},required=False)
 persist()


def wall_finish():
 code("""import FreeCAD as App
D=App.getDocument('StrawberryHead')
for i in [8,11]:D.NoseBridgeProfile.setExpression('Constraints['+str(i)+']','Dims.IntegralFixedRootProfileY2 + 100')
for i in [4,7]:D.MovingJawProfile.setExpression('Constraints['+str(i)+']','Dims.M3Clear/2 + Dims.Wall + 100')
D.MovingJawProfile.setExpression('Constraints[19]','-Dims.M3Clear/2 - Dims.Wall + 100')
base='Dims.JawPivotX + Dims.M3Clear/2 + Dims.Wall + 2*Dims.AxialClearance'
for i in [1,10]:D.JawSupportPostProfile.setExpression('Constraints['+str(i)+']',base+' + 100')
for i in [4,7]:D.JawSupportPostProfile.setExpression('Constraints['+str(i)+']',base+' + Dims.JawSupportPostProfileX1 - Dims.JawSupportPostProfileX0 + 100')
print('Minimum bearing ligaments >=2.4 mm; 0.4 mm moving-jaw/post clearance; bridge front follows integral root')
""")
 pose('clamp')
 res=code("""import FreeCAD as App,json
D=App.getDocument('StrawberryHead')
print(json.dumps({n:{'solids':len(D.getObject(n).Shape.Solids),'volume_mm3':D.getObject(n).Shape.Volume} for n in ['NoseFrameReady','DriveHousingReady','MovingJaw']}))
""")
 R['manufacturing_solids']=output_json(res)
 geometry()
 call('save_document',selector={'document_name':DOC},required=False)
 persist()


def link_finish():
 result=code("""import FreeCAD as App,json
D=App.getDocument('StrawberryHead');new=[]
# Link pins are headed pins retained in a reamed press fit in the links,
# with free clearance in the horn and lever. Tail stays below the housing.
for tag,lever in [('Clamp','MovingJaw'),('Cut','BladeLever')]:
 pin=D.getObject(tag+'LeverLinkPin')
 D.getObject(tag+'LeverLinkPinProfile').setExpression('Placement.Base.z','Dims.'+lever+'ProfileZ')
 expr=('Dims.'+tag+'LinkProfileZ + Dims.'+tag+'LinkPadLength - Dims.'+lever+'ProfileZ - '+('Dims.AxialClearance + Dims.PilotRadialClearance' if tag=='Clamp' else 'Dims.PilotRadialClearance'))
 D.getObject(tag+'LeverLinkPinPad').setExpression('Length',expr)
 for i in [2,5]:D.getObject(tag+'LinkHolesProfile').setExpression('Constraints['+str(i)+']','Dims.M2Clear/2 - Dims.AxialClearance - Dims.PilotRadialClearance/10')
 for endpoint in ['Horn','Lever']:
  o=D.addObject('Part::Cylinder',tag+endpoint+'PinHead');D.getObject(tag+'LinkRotor').addObject(o)
  o.addProperty('App::PropertyString','Category','BOM');o.Category='bought'
  o.addProperty('App::PropertyString','MaterialNote','BOM');o.MaterialNote='steel'
  o.setExpression('Radius','Dims.M2HeadRadius')
  if endpoint=='Horn':
   o.setExpression('Height','Dims.AxialClearance + Dims.PilotRadialClearance')
   o.setExpression('Placement.Base.z','Dims.'+tag+'HornProfileZ + Dims.'+tag+'HornPadLength')
  else:
   o.setExpression('Height','2*Dims.ClipThickness')
   o.setExpression('Placement.Base.z','Dims.'+lever+'ProfileZ - 2*Dims.ClipThickness')
   o.setExpression('Placement.Base.x','Dims.'+tag+'LinkLength')
  new.append(o.Name)
print(json.dumps(new))
""")
 for n in output_json(result):
  M['parts'].append({'name':n,'kind':'bought','material':'steel','color':[.59,.62,.65]});M['bought'].append(n)
 (OUT/'design-manifest.json').write_text(json.dumps(M,indent=2))
 gui_batch(M['parts'],visible={**{n:False for n in M.get('references',[])},'HeadEnvelope':False,'Joints':False})
 pose('clamp')
 geometry()
 R['link_pins']='Four 2 mm headed pins: press retained in 1.98 mm reamed link holes, free in 2.4 mm horn/lever holes. Lever-end pin reaches through both members and stops below the housing. Bought pin heads are separate simple grey subshapes.'
 call('save_document',selector={'document_name':DOC},required=False)
 persist()


def join_frame():
 code("""import FreeCAD as App
D=App.getDocument('StrawberryHead');new=[]
# Tie the fixed-jaw/anvil floor around the cutter window to the left spine.
for name,y in [('AnvilRearTie','Dims.IntegralFixedRootProfileY0'),('AnvilFrontTie','Dims.FixedJawProfileY0')]:
 o=D.addObject('Part::Box',name);D.PickingHead.addObject(o)
 o.addProperty('App::PropertyString','Category','BOM');o.Category='reference'
 for p,e in [('Length','Dims.IntegralFixedRootProfileX0 + Dims.Wall - Dims.NoseCheekLProfileX1'),('Width','Dims.M3Clear'),('Height','Dims.NoseSlotBottom'),('Placement.Base.x','Dims.NoseCheekLProfileX1'),('Placement.Base.y',y),('Placement.Base.z','Dims.FixedJawProfileZ')]:o.setExpression(p,e)
 new.append(o)
ledge=D.addObject('Part::Box','AnvilLedge');D.PickingHead.addObject(ledge)
ledge.addProperty('App::PropertyString','Category','BOM');ledge.Category='reference'
for p,e in [('Length','Dims.Wall + Dims.PadThick'),('Width','Dims.PadDepth'),('Height','Dims.Wall'),('Placement.Base.x','Dims.FixedTPUProfileX0 - Dims.Wall'),('Placement.Base.y','Dims.FixedTPUProfileY0'),('Placement.Base.z','Dims.FixedJawPadLength - Dims.Wall')]:ledge.setExpression(p,e)
D.FixedTPUPad.setExpression('Length','Dims.FixedJawPadLength - Dims.Wall')
D.FixedTPUPad.setExpression('Length2','Length')
D.NoseFrame.Shapes=list(D.NoseFrame.Shapes)+new+[ledge]
print('Two under-blade ties join the anvil floor to the rear spine; ledge reaches stem above replaceable TPU')
""")
 M['references']=list(set(M.get('references',[]))|{'AnvilRearTie','AnvilFrontTie','AnvilLedge'})
 (OUT/'design-manifest.json').write_text(json.dumps(M,indent=2))
 gui_batch(M['parts'],visible={**{n:False for n in M['references']},'HeadEnvelope':False,'Joints':False})
 pose('clamp')
 res=code("""import FreeCAD as App,json
D=App.getDocument('StrawberryHead')
print(json.dumps({n:{'solids':len(D.getObject(n).Shape.Solids),'volume_mm3':D.getObject(n).Shape.Volume} for n in ['NoseFrameReady','DriveHousingReady','MovingJaw']}))
""")
 R['manufacturing_solids']=output_json(res)
 R['anvil']='Fixed TPU pad height 4.2 mm; integral 2.4 mm anvil ledge reaches the stem, at Z=6.6 mm under the Z=6.7 mm blade. Two 3.2 mm wide under-blade ties keep the nose frame one connected solid.'
 geometry()
 call('save_document',selector={'document_name':DOC},required=False)
 persist()


def clamp_fasteners():
 state=call('get_mutation_readiness')
 while not state.get('ready',False):time.sleep(5);state=call('get_mutation_readiness')
 result=code("""import FreeCAD as App,json
D=App.getDocument('StrawberryHead');added=[]
# Standard M2x12 clamp screws with separate head and nut envelopes.
for i in range(2):
 stem='BladeClampM2'+str(i)
 D.getObject(stem+'Profile').setExpression('Placement.Base.z','Dims.BladeClampProfileZ')
 D.getObject(stem+'Pad').setExpression('Length','Dims.FrameBoltLength')
 for suffix,z,h,r in [('Head','Dims.BladeClampProfileZ - Dims.M2HeadHeight','Dims.M2HeadHeight','Dims.M2HeadRadius'),('Nut','Dims.BladeLeverProfileZ + Dims.BladeLeverPadLength','Dims.NutHeight','Dims.NutRadius')]:
  o=D.addObject('Part::Cylinder',stem+suffix);D.CutterRotor.addObject(o)
  o.addProperty('App::PropertyString','Category','BOM');o.Category='bought'
  o.addProperty('App::PropertyString','MaterialNote','BOM');o.MaterialNote='steel'
  for p,e in [('Radius',r),('Height',h),('Placement.Base.x','Dims.'+stem+'ProfileX0'),('Placement.Base.y','Dims.'+stem+'ProfileY0'),('Placement.Base.z',z)]:o.setExpression(p,e)
  added.append(o.Name)
D.LeftNoseBladeWindow.setExpression('Placement.Base.z','Dims.NoseSlotBottom - 10*Dims.PilotRadialClearance')
D.LeftNoseBladeWindow.setExpression('Height','Dims.ArmSlotZ + Dims.ArmSlotHeight - Dims.NoseSlotBottom + 10*Dims.PilotRadialClearance')
print(json.dumps(added))
""")
 for n in output_json(result):
  M['parts'].append({'name':n,'kind':'bought','material':'steel','color':[.59,.62,.65]});M['bought'].append(n)
 (OUT/'design-manifest.json').write_text(json.dumps(M,indent=2))
 gui_batch(M['parts'],visible={**{n:False for n in M.get('references',[])},**{'World_'+p['name']:False for p in M['parts']},'HeadEnvelope':False,'Joints':False})
 pose('clamp')
 geometry()
 res=code("""import FreeCAD as App,json
D=App.getDocument('StrawberryHead')
print(json.dumps({n:{'solids':len(D.getObject(n).Shape.Solids),'volume_mm3':D.getObject(n).Shape.Volume} for n in ['NoseFrameReady','DriveHousingReady','MovingJaw']}))
""")
 R['manufacturing_solids']=output_json(res)
 R['blade_fasteners']='Two M2x12 screws with heads and nuts clamp the tang-slot blade. Left carrier relief clears the bought screw heads while keeping the original lower nose outline.'
 call('save_document',selector={'document_name':DOC},required=False)
 persist()


def final_checks():
 state=call('get_mutation_readiness')
 while not state.get('ready',False):time.sleep(5);state=call('get_mutation_readiness')
 pose('clamp')
 R['fusion_validation']={n:call('validate_geometry',obj_name=n,required=False) for n in ['NoseFrameReady','DriveHousingReady','MovingJaw']}
 res=code("""import FreeCAD as App,json
D=App.getDocument('StrawberryHead')
print(json.dumps({n:{'solids':len(D.getObject(n).Shape.Solids),'volume_mm3':D.getObject(n).Shape.Volume} for n in ['NoseFrameReady','DriveHousingReady','MovingJaw']}))
""")
 R['manufacturing_solids']=output_json(res)
 R['blade_fasteners']='Two M2x12 clamp screws, heads and nuts, all modelled as grey bought subshapes. Lower nose blade window clears the heads; fruit-facing outline stays unchanged.'
 call('save_document',selector={'document_name':DOC},required=False)
 persist()
 engineering()
 fem()
 mass()


def housing_clearance():
 result=code("""import FreeCAD as App
D=App.getDocument('StrawberryHead');tools=[D.JawAxleAccess]
for tag in ['Clamp','Cut']:
 for kind in ['Motor','Cable']:
  n=tag+kind+'FinalClearance';o=D.addObject('Part::Box',n);D.PickingHead.addObject(o)
  o.addProperty('App::PropertyString','Category','BOM');o.Category='reference'
  if kind=='Motor':
   p=tag+'MotorCavityProfile'
   expressions={'Length':'Dims.'+p+'X1 - Dims.'+p+'X0','Width':'Dims.'+p+'Y2 - Dims.'+p+'Y0','Height':'Dims.'+tag+'MotorCavityLength','Placement.Base.x':'Dims.'+p+'X0','Placement.Base.y':'Dims.'+p+'Y0','Placement.Base.z':'Dims.'+p+'Z - Dims.'+tag+'MotorCavityLength'}
  else:
   p=tag+'CableProfile'
   expressions={'Length':'Dims.'+p+'X1 - Dims.'+p+'X0 + 2*Dims.PilotRadialClearance','Width':'Dims.'+p+'Y2 - Dims.'+p+'Y0 + 2*Dims.PilotRadialClearance','Height':'Dims.'+tag+'CablePadLength + 2*Dims.PilotRadialClearance','Placement.Base.x':'Dims.'+p+'X0 - Dims.PilotRadialClearance','Placement.Base.y':'Dims.'+p+'Y0 - Dims.PilotRadialClearance','Placement.Base.z':'Dims.'+p+'Z - Dims.PilotRadialClearance'}
  for p,e in expressions.items():o.setExpression(p,e)
  tools.append(o)
union=D.addObject('Part::MultiFuse','HousingFinalClearanceTools');D.PickingHead.addObject(union);union.Shapes=tools;union.Refine=True
union.addProperty('App::PropertyString','Category','BOM');union.Category='reference'
D.DriveHousingReady.Tool=union
for tag in ['Clamp','Cut']:
 for axis,fn in [('x','cos'),('y','sin')]:D.getObject(tag+'LinkRotor').setExpression('Placement.Base.'+axis,'Dims.'+tag+'HornRotor'+axis.upper()+' + Dims.HornRadius * '+fn+'(Motion.'+tag+'ServoAngle * 1 deg)')
# Purchased wrist pilot is wholly parameterized; its inner overlap is scene only.
D.WristPilotBoss.setExpression('Height','Dims.PlateThickness + Dims.PilotDepth')
D.WristPilotBoss.setExpression('Placement.Base.y','Dims.WristAdapterProfileY0')
D.WristPilotBoss.setExpression('Placement.Base.z','Dims.WristAdapterProfileZ + Dims.PlateThickness - Dims.PilotDepth')
print('Post-union motor/cable pockets remove column intrusions. Head geometry only loses material; checked clearances remain conservative bounds.')
""")
 M['references']=list(set(M.get('references',[]))|{'ClampMotorFinalClearance','ClampCableFinalClearance','CutMotorFinalClearance','CutCableFinalClearance','HousingFinalClearanceTools'})
 (OUT/'design-manifest.json').write_text(json.dumps(M,indent=2))
 gui_batch(M['parts'],visible={**{n:False for n in M['references']},'HeadEnvelope':False,'Joints':False})
 pose('clamp')
 R['housing_final_validation']=call('validate_geometry',obj_name='DriveHousingReady',required=False)
 R['housing_relief']='Final post-union motor and flexible-cable relief removes material from the checked envelope. Existing zero-intersection/path results remain valid; reported distances are conservative lower bounds. Outer nose and all moving members are unchanged.'
 # Refresh only changed physical mass/COM data; other part measurements stay valid.
 R['mass']['DriveHousingReady']={'volume':volume('DriveHousingReady'),'com':call('center_of_mass',obj_name='DriveHousingReady',required=False)}
 R['mass']['HeadEnvelope']={'volume':volume('HeadEnvelope'),'com':call('center_of_mass',obj_name='HeadEnvelope',required=False)}
 persist()
 call('save_document',selector={'document_name':DOC},required=False)

def mass_sheet():
 def vol(n):return R['mass'][n]['volume'].get('volume_mm3',0)
 pla_v=sum(vol(p['name']) for p in M['parts'] if p['kind']=='printed' and p['material']!='TPU')
 tpu_v=sum(vol(p['name']) for p in M['parts'] if p['kind']=='printed' and p['material']=='TPU')
 steel_v=sum(v['volume_mm3'] for v in R['bought_volumes'].values() if v['material']=='steel')
 total=pla_v*.00124*.4+tpu_v*.0012+steel_v*.00785+18+.6+1.3+.2
 R['total_mass']={'printed_PLA_g':pla_v*.00124*.4,'solid_TPU_g':tpu_v*.0012,'steel_fasteners_g':steel_v*.00785,'servos_including_tabs_shafts_cables_g':18,'horns_g':.6,'blade_g':1.3,'adhesive_allowance_g':.2,'total_g':total}
 moments=[0.,0.,0.];mass_sum=0.
 def add(m,c):
  nonlocal mass_sum
  mass_sum+=m
  for i,v in enumerate(c):moments[i]+=m*v
 for p in M['parts']:
  if p['kind']=='printed':
   data=R['mass'][p['name']];m=vol(p['name'])*(.0012 if p['material']=='TPU' else .00124*.4)
   add(m,[data['com'][a] for a in ['x','y','z']])
 for n,v in R['bought_volumes'].items():
  if v['material']=='steel':add(v['volume_mm3']*.00785,v['com'])
 for n,m in [('ClampServo',9),('CutServo',9),('ClampHorn',.3),('CutHorn',.3),('HobbyBlade',1.3)]:add(m,R['bought_volumes'][n]['com'])
 add(.2,[0,0,2.55])
 R['weighted_com']={**{a:moments[i]/mass_sum for i,a in enumerate(['x','y','z'])},'unit':'mm','frame':'world','method':'measured geometry plus density, infill and bought-mass allowances'}
 call('spreadsheet_create',sheet_name='Mass')
 rows=[('Measured PLA volume mm3',pla_v,'PLAVolume'),('Measured TPU volume mm3',tpu_v,'TPUVolume'),('Measured steel envelope volume mm3',steel_v,'SteelVolume'),('TPU density g/cm3',1.2,'TPUDensity'),('Steel density g/cm3',7.85,'SteelDensity'),('Servo quantity',2,'ServoQty'),('Servo mass g','=Dims.ServoMass','ServoUnitMass'),('Blade mass allowance g','=Dims.BladeMass','BladeAllowance'),('Horn quantity',2,'HornQty'),('Horn mass allowance g',.3,'HornUnitMass'),('Adhesive allowance g',.2,'AdhesiveAllowance'),('Printed PLA mass g','=B1 / 1000 * Dims.PLADensity * Dims.Infill','PLAMass'),('TPU mass g','=B2 / 1000 * B4','TPUMass'),('Steel mass g','=B3 / 1000 * B5','SteelMass'),('Estimated complete head mass g','=B12 + B13 + B14 + B6 * B7 + B8 + B9 * B10 + B11','HeadMass')]
 cells=[]
 for i,(label,value,alias) in enumerate(rows,1):cells.extend([{'address':'A'+str(i),'value':label},{'address':'B'+str(i),'value':str(value),'alias':alias}])
 call('spreadsheet_set_cells',sheet_name='Mass',cells=cells)
 R['mass_sheet']=call('spreadsheet_get_cells',sheet_name='Mass',addresses=['B12','B13','B14','B15'])
 R['source_audits']={n:call('audit_hardcoded_dimensions',body_name=n,required=False) for n in M.get('references',[]) if n in ['NoseCheekL','NoseCheekR','NoseBridge','FixedJaw','JawForkLower','JawForkUpper','CutterForkLower','CutterForkUpper','JawSupportPost','Chassis','ClampServoPocket','CutServoPocket','MountColumnL','MountColumnR']}
 findings=[f for a in {**R.get('audits',{}),**R.get('source_audits',{})}.values() for f in a.get('findings',[])]
 R['expression_audit_readback']=output_json(code("""import FreeCAD as App,json
D=App.getDocument('StrawberryHead');findings="""+repr(findings)+"""
result=[]
for f in findings:
 o=D.getObject(f['object']);p='Constraints['+str(f['index'])+']' if f['kind']=='sketch_constraint' else f.get('property','')
 table=dict(o.ExpressionEngine);e=table.get(p)
 try:g=str(o.getExpression(p))
 except Exception as ex:g=type(ex).__name__+': '+str(ex)
 result.append({'object':o.Name,'property':p,'expression':str(e) if e is not None else None,'getter':g})
print(json.dumps(result))
"""))
 R['final_printed_solids']=output_json(code("""import FreeCAD as App,json
D=App.getDocument('StrawberryHead')
print(json.dumps({o.Name:{'solids':len(o.Shape.Solids),'state':list(o.State)} for o in D.Objects if hasattr(o,'Category') and o.Category=='printed' and hasattr(o,'Shape')}))
"""))
 persist()

def resume_paths():
 call('get_worker_status',required=False)
 state=call('get_mutation_readiness',required=False)
 while not state.get('ready',False):
  time.sleep(5);state=call('get_mutation_readiness',required=False)
 R['path_initial_failure']=R.get('paths',{})
 R['paths']={}
 for name,points in [('approach',[{'x':0,'y':0,'z':float(z)} for z in [15,12,9,6,3,0]]),('withdraw',[{'x':0,'y':-25*t/5,'z':20*t/5} for t in range(6)])]:
  pose('approach_path_reference',-18,13,0,0) if name=='approach' else pose('cut',0,-13)
  chunks=[]
  for point in points:
   result=call('common_volume_along_path',moving_object='HeadEnvelope',obstacle_objects=['NeighbourLBerry','NeighbourLCap','NeighbourRBerry','NeighbourRCap'],samples=[point],required=False)
   chunks.append(result)
   R['paths'][name]={'sample_count':len(chunks),'requested_samples':points,'chunks':chunks,'batching':'One position per call to stay below the 30-second native GUI deadline'}
   persist()
   if not events[-1]['result']['ok']:raise RuntimeError('Path sample failed; GUI liveness must be checked before further work')
 pose('clamp')
 persist()


def travel_checks():
 # Measure moving-member interference across actual travel, excluding intentional pin contacts.
 R['travel']=[]
 for n in range(7):
  ja=-18+3*n; ca=13-4*n; pose('travel',ja,ca)
  checks={}
  for a,b in [('MovingJaw','ClampLink'),('MovingJaw','BladeLever'),('BladeLever','CutLink'),('ClampLink','CutLink'),('BladeLever','DriveHousingReady'),('MovingJaw','DriveHousingReady'),('MovingJaw','NoseFrameReady'),('BladeLever','NoseFrameReady'),('HobbyBlade','CutterPin'),('HobbyBlade','NoseFrameReady'),('HobbyBlade','CutLowerSpacer'),('BladeClamp','NoseFrameReady'),('CutLink','DriveHousingReady')]:
   checks[a+'--'+b]=common(a,b,'Travel'+str(n)+a+b)
  R['travel'].append({'jaw_angle':ja,'cutter_angle':ca,'checks':checks}); persist()
 # Stem intersection across cutting edge sweep; records blade/target-stem overlap.
 R['blade_crossing']=[]
 for ca in [13,9,4,0,-4,-9,-13]:
  pose('blade',0,ca)
  R['blade_crossing'].append({'angle':ca,'intersection':common('HobbyBlade','TargetStem','BladeStem'+str(ca).replace('-','m'))})
  persist()
 pose('clamp')

def geometry():
 data=code("""import FreeCAD as App,json
D=App.getDocument('StrawberryHead')
print(json.dumps({n:{'state':list(D.getObject(n).State),'volume':D.getObject(n).Shape.Volume,'faces':[{'name':'Face'+str(i+1),'type':type(f.Surface).__name__,'center':list(f.CenterOfMass),'area':f.Area} for i,f in enumerate(D.getObject(n).Shape.Faces)]} for n in ['MovingJaw','JawForkLower','BladeLever','CutterForkLower','TargetBerry','HeadEnvelope']}))
""")
 R['geometry']=output_json(data); persist()
def assembly():
 geometry()
 def cyl(name): return next(f['name'] for f in R['geometry'][name]['faces'] if f['type']=='Cylinder' and (name not in ['MovingJaw','BladeLever'] or abs(f['center'][1])<2) and (name!='BladeLever' or abs(f['center'][0])<2))
 R['assembly']={}
 for support in ['JawForkLower','CutterForkLower']:
  R['assembly']['ground_'+support]=call('create_assembly_grounded_joint',assembly_name='PickingHead',component_name=support,required=False)
 for tag,support,rotor,body in [('jaw','JawForkLower','JawRotor','MovingJaw'),('cutter','CutterForkLower','CutterRotor','BladeLever')]:
  R['assembly'][tag]=call('create_assembly_joint',assembly_name='PickingHead',joint_type='Revolute',ref1_component=support,ref2_component=rotor,ref1_element=cyl(support),ref2_element=body+'.'+cyl(body),label=tag+' revolute M3',solve=False,presolve=False,required=False)
  joint=R['assembly'][tag].get('joint')
  if joint:
   f1=next(f for f in R['geometry'][support]['faces'] if f['name']==cyl(support))
   f2=next(f for f in R['geometry'][body]['faces'] if f['name']==cyl(body))
   delta=f1['center'][2]-f2['center'][2]
   R['assembly'][tag+'_axial_offset']=edit(joint,Offset2={'Base':{'z':delta}})
 R['assembly']['solve']=call('solve_assembly',assembly_name='PickingHead',required=False)
 gui_batch(visible={'Joints':False})
 persist()
 # Restore expression placements even if the native solver changed a component.
 pose('clamp')
def engineering():
 R['transmission']={tag:[linkage(tag,a)[1] for a in (range(-18,1,2) if tag=='Clamp' else range(-13,14,2))] for tag in ['Clamp','Cut']}
 R['poses']={}
 for name,ja,ca,hz,hy,target in [('approach',-18,13,15,0,False),('clamp',0,13,0,0,False),('cut',0,-13,0,0,False),('withdraw',0,-13,20,-25,True)]:
  p=pose(name,ja,ca,hz,hy,target)
  p['assembly']=call('solve_assembly',assembly_name='PickingHead',required=False)
  # Solver checks joints; expression placements are the authoritative pose fallback.
  pose(name,ja,ca,hz,hy,target)
  p['clearances']={}
  for fruit in ['TargetBerry','TargetCap','NeighbourLBerry','NeighbourLCap','NeighbourRBerry','NeighbourRCap']:
   dist=call('measure_distance',shape1_ref='HeadEnvelope',shape2_ref=fruit,required=False)
   intersection=common('HeadEnvelope',fruit,name+'_'+fruit+'_Common')
   p['clearances'][fruit]={'distance':dist,**intersection}
  p['jaw_gap']=call('measure_distance',shape1_ref='FixedTPU',shape2_ref='MovingTPU',required=False)
  R['poses'][name]=p; persist()
 pose('clamp')
 R['paths']={}
 for name,pts in [('approach',[{'x':0,'y':0,'z':float(z)} for z in range(15,-1,-1)]),('withdraw',[{'x':0,'y':-25*i/20,'z':float(i)} for i in range(21)])]:
  pose('approach_path_reference',-18,13,0,0) if name=='approach' else pose('cut',0,-13)
  R['paths'][name]=call('common_volume_along_path',moving_object='HeadEnvelope',obstacle_objects=['NeighbourLBerry','NeighbourLCap','NeighbourRBerry','NeighbourRCap','Truss','TargetBranch','NeighbourLBranch','NeighbourRBranch','NeighbourLStem','NeighbourRStem'],samples=pts,required=False)
  persist()
 # Measure moving-member interference across actual travel, excluding intentional pin contacts.
 R['travel']=[]
 for n in range(7):
  ja=-18+3*n; ca=13-4*n; pose('travel',ja,ca)
  checks={}
  for a,b in [('MovingJaw','ClampLink'),('MovingJaw','BladeLever'),('BladeLever','CutLink'),('ClampLink','CutLink'),('BladeLever','DriveHousingReady'),('MovingJaw','DriveHousingReady'),('MovingJaw','NoseFrameReady'),('BladeLever','NoseFrameReady'),('HobbyBlade','CutterPin'),('HobbyBlade','NoseFrameReady'),('HobbyBlade','CutLowerSpacer'),('BladeClamp','NoseFrameReady'),('CutLink','DriveHousingReady')]:
   checks[a+'--'+b]=common(a,b,'Travel'+str(n)+a+b)
  R['travel'].append({'jaw_angle':ja,'cutter_angle':ca,'checks':checks}); persist()
 # Stem intersection across cutting edge sweep; records blade/target-stem overlap.
 R['blade_crossing']=[]
 for ca in [13,9,4,0,-4,-9,-13]:
  pose('blade',0,ca)
  R['blade_crossing'].append({'angle':ca,'intersection':common('HobbyBlade','TargetStem','BladeStem'+str(ca).replace('-','m'))})
  persist()
 pose('clamp')
def fem():
 R['fem']={}
 R['fem']['analysis']=call('create_object',obj_type='Fem::AnalysisPython',obj_name='JawAnalysis',required=False)
 R['fem']['material']=call('create_object',obj_type='Fem::MaterialCommon',obj_name='JawPLA',analysis_name='JawAnalysis',obj_properties={'Material':{'Name':'PLA','YoungModulus':'3500 MPa','PoissonRatio':'0.36','Density':'1240 kg/m^3','YieldStrength':'50 MPa'}},required=False)
 # The cylindrical jaw pin face is fixed; load the face closest to the pad backing.
 faces=R['geometry']['MovingJaw']['faces']
 fixed=next(f['name'] for f in faces if f['type']=='Cylinder' and abs(f['center'][1])<2)
 load=min((f for f in faces if f['type']=='Plane'),key=lambda f:sum((f['center'][i]-[-5.5,12,3][i])**2 for i in range(3)))['name']
 R['fem']['fixed']=call('create_object',obj_type='Fem::ConstraintFixed',obj_name='PinFixed',analysis_name='JawAnalysis',obj_properties={'References':[{'object_name':'MovingJaw','face':fixed}]},required=False)
 R['fem']['load']=call('create_object',obj_type='Fem::ConstraintForce',obj_name='PadLoad10N',analysis_name='JawAnalysis',obj_properties={'References':[{'object_name':'MovingJaw','face':load}],'Force':10},required=False)
 R['fem']['mesh']=call('create_object',obj_type='Fem::FemMeshGmsh',obj_name='JawCoarseMesh',analysis_name='JawAnalysis',obj_properties={'Shape':'MovingJaw','CharacteristicLengthMax':3,'CharacteristicLengthMin':1.5,'ElementOrder':'1st'},required=False)
 R['fem']['solve']=call('run_fem_analysis',analysis_name='JawAnalysis',timeout=45,required=False)
 R['fem']['beam']=call('spreadsheet_get_cells',sheet_name='Dims',addresses=[M['cells'][x] for x in ['YoungMPa','YieldMPa','BeamLength','BeamWidth','BeamDepth','BeamI','BeamStress','BeamDeflection','BeamSF']])
 persist()
def mass():
 R['mass']={}; R['audits']={}
 for name in M['printed']:
  R['mass'][name]={'volume':volume(name),'com':call('center_of_mass',obj_name=name,required=False)}
  R['audits'][name]=call('audit_hardcoded_dimensions',body_name=name,required=False)
  persist()
 bought_mass()

def bought_mass():
 R['mass']['HeadEnvelope']={'volume':volume('HeadEnvelope'),'com':call('center_of_mass',obj_name='HeadEnvelope',required=False)}
 res=code("""import FreeCAD as App,json
d=App.getDocument('StrawberryHead');result={}
for o in d.Objects:
 if not hasattr(o,'Category') or o.Category!='bought' or not hasattr(o,'Shape'):continue
 shape=o.Shape;v=sum(s.Volume for s in shape.Solids);c=App.Vector()
 for s in shape.Solids:c+=s.CenterOfMass*s.Volume
 if v>0:c=c/v
 c=o.getGlobalPlacement().multVec(o.Placement.inverse().multVec(c))
 result[o.Name]={'volume_mm3':v,'com':list(c),'material':o.MaterialNote}
print(json.dumps(result))
""")
 R['bought_volumes']=output_json(res) or {}
 def vv(data):return data.get('volume_mm3',0)
 pla=sum(vv(R['mass'].get(p['name'],{}).get('volume',{}))*.00124*.4 for p in M['parts'] if p['kind']=='printed' and p['material']!='TPU')
 tpu=sum(vv(R['mass'].get(p['name'],{}).get('volume',{}))*.0012 for p in M['parts'] if p['kind']=='printed' and p['material']=='TPU')
 steel=sum(v['volume_mm3']*.00785 for v in R['bought_volumes'].values() if v['material']=='steel')
 R['total_mass']={'printed_PLA_g':pla,'solid_TPU_g':tpu,'steel_fasteners_g':steel,'servos_including_tabs_shafts_cables_g':18,'horns_g':.6,'blade_g':1.3,'total_g':pla+tpu+steel+18+.6+1.3}
 R['parts_list']=call('get_parts_list',required=False)
 persist()
def narrow():
 pose('clamp')
 setcells({'NeighbourGap':10})
 pose('clamp')
 R['narrow']={}
 for side in ['L','R']:
  R['narrow'][side]={'distance':call('measure_distance',shape1_ref='NoseCheek'+side,shape2_ref='Neighbour'+side+'Berry',required=False),'intersection':common('NoseCheek'+side,'Neighbour'+side+'Berry','NarrowClash'+side)}
  # Show the actual computed common shape in bright red.
  edit('NarrowClash'+side,ViewObject={'Visibility':True,'ShapeColor':[1,0,0]})
 R['narrow']['whole_head']={}
 for name in ['NeighbourLBerry','NeighbourLCap','NeighbourLStem','NeighbourRBerry','NeighbourRCap','NeighbourRStem']:
  R['narrow']['whole_head'][name]={'distance':call('measure_distance',shape1_ref='HeadEnvelope',shape2_ref=name,required=False),'intersection':common('HeadEnvelope',name,'NarrowHead'+name)}
 R['narrow']['carrier_stem']=common('BladeLever','NeighbourLStem','NarrowCarrierStemL')
 if R['narrow']['carrier_stem'].get('volume',{}).get('volume_mm3',0)>0:
  edit('NarrowCarrierStemL',ViewObject={'Visibility':True,'ShapeColor':[1,0,0]})
 persist()
 if __name__=='__main__': pass

def view_from(eye):
 def norm(v):
  l=math.sqrt(sum(x*x for x in v));return [x/l for x in v]
 def cross(a,b):return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
 z=norm(eye);x=norm(cross([0,0,1],z));y=cross(z,x)
 # Camera basis: local X/Y in the screen, local +Z points toward viewer.
 m=[[x[i],y[i],z[i]] for i in range(3)]
 t=sum(m[i][i] for i in range(3));w=math.sqrt(1+t)/2
 return [(m[2][1]-m[1][2])/(4*w),(m[0][2]-m[2][0])/(4*w),(m[1][0]-m[0][1])/(4*w),w]

def stills():
 setcells({'NeighbourGap':15})
 pose('clamp',0,13)
 # Consistent colours on both the Body and its final feature. Geometry remains native.
 gui_batch(M['parts'])
 show('HeadEnvelope',False)
 for name in ['NarrowClashL','NarrowClashR']:
  if R.get('narrow'):show(name,False)
 call('set_section_view',enabled=False)
 capture('01_scene.png','STRAWBERRY PICKING HEAD | DESIGN GATE',
  'Mounted, driven picking head | touches the stem | 15 mm neighbour gap',
  ['Clamp first, shear above the clamp, withdraw with the berry hanging, lower into the tray, open.',
   'Grey = bought hardware | teal / amber / violet = printed parts | green = replaceable TPU pads'],
  orientation=view_from([1,2,1.7]),camera={'center':[-15,35,7],'height':380})
 pose('cut',0,-13)
 # Section through the contact plane. Hide rear drive only to expose the cutting geometry.
 gui_batch(visible={n:False for n in ['NeighbourLBerry','NeighbourLCap','NeighbourRBerry','NeighbourRCap']})
 call('set_section_view',enabled=True,base=[0,0,0],normal=[0,1,0],no_manip=True)
 capture('02_closeup.png','STEM CONTACT | CLAMP BEFORE CUT',
  'Section at Y = 0 | parallel 3 mm pad gap | blade plane Z = 6.7 mm, on the plant side',
  ['Moving pad Z = 0–6 mm; fixed pad Z = 0–4.2 mm; bypass blade Z = 6.7–7.1 mm.',
   'The fruit and green cap stay below the jaws. M3 pivots and actual screw-clamped blade are shown.'],
  view='viewFront',camera={'center':[0,0,-2],'height':46})
 call('set_section_view',enabled=False)
 gui_batch(visible={n:True for n in ['NeighbourLBerry','NeighbourLCap','NeighbourRBerry','NeighbourRCap']})
 pose('clamp',0,13)
 gui_batch([{**p,'transparency':75 if p['name'] in ['DriveHousingReady','ClampServo','CutServo','WristAdapter','BladeLever','HobbyBlade','BladeClamp'] else 0} for p in M['parts']])
 gui_batch(visible={'RobotWrist':False,'WristPilotBoss':False,'Tray':False})
 capture('03_top.png','NOMINAL GAP | DRIVE AND CLEARANCE',
  'Top view | translucent drive covers reveal the linkages | 15 mm between fruit envelopes',
  ['Nose outside edges X = ±29 mm; nearest neighbour fruit surfaces X = ±30 mm at nominal gap.',
   'Exact 3D distances, Boolean results and sampled approach / withdraw checks are in design-notes.md.'],
  view='viewTop',camera={'center':[0,-35,0],'height':165})
 gui_batch(M['parts'])
 # Exploded copies of actual native part shapes; the assembly itself stays assembled.
 res=code("""import FreeCAD as App,Part,json
D=App.getDocument('StrawberryHead'); group=D.addObject('App::Part','ExplodedView')
names=[]
for b in D.Objects:
 if not hasattr(b,'Category') or b.Category not in ['printed','bought'] or not hasattr(b,'Shape'):continue
 n=b.Name; x=y=z=0
 if n.startswith('NoseFrame'):y=30;z=-15
 elif n.startswith('DriveHousing'):y=-15
 elif 'Adapter' in n or 'Flange' in n:x=0;y=-15;z=50
 elif 'Column' in n:z=22;x=-15 if 'L' in n else 15
 elif 'Servo' in n or 'M2Screw' in n or 'M2Head' in n or 'OutputShaft' in n or 'Cable' in n:
  x=-42 if n.startswith('Clamp') else 42;y=5;z=35 if ('ServoPocket' not in n) else 5
 elif 'NoseCheek' in n or 'CheekM2' in n:x=-30 if n.endswith('L') else 30;y=20
 elif n.startswith('Fixed'):x=-15;y=55;z=-10
 elif any(k in n for k in ['Blade','Cutter','CutHorn','CutLink','CutLever']):x=-25;y=40;z=30
 elif any(k in n for k in ['Moving','PadBacking','Jaw','ClampHorn','ClampLink','ClampLever']):x=25;y=45;z=10
 elif 'NoseBridge' in n:y=20
 o=D.addObject('Part::Feature','Exploded_'+n); group.addObject(o)
 shape=b.Shape.copy(); shape.Placement=b.getGlobalPlacement(); shape.translate(App.Vector(x,y,z));o.Shape=shape
 names.append({'name':o.Name,'source':n,'category':b.Category})
print(json.dumps(names))
""")
 copies=output_json(res) or []
 gui_batch(visible={p['name']:False for p in M['parts']})
 gui_batch([{'name':p['name'],'color':next(q for q in M['parts'] if q['name']==p['source'])['color']} for p in copies])
 capture('04_parts.png','PRINTED PARTS + BOUGHT HARDWARE',
  'Exploded actual part geometry | flat print faces | servo pockets, pins, fasteners and blade clamp',
  ['Teal = structure | amber = jaw and clamp link | violet = cutter and cut link | green = TPU cartridges.',
   'Grey = bought hardware. Full quantities, materials and mass estimate are in design-notes.md.'],
  orientation=view_from([1,2,1.7]),camera={'center':[0,-10,37],'height':310})
 show('ExplodedView',False)
 gui_batch(visible={p['name']:True for p in M['parts']})
 narrow()
 gui_batch([{**p,'transparency':75 if p['name'] in ['NoseFrameReady','BladeLever','HobbyBlade','BladeClamp'] else 0} for p in M['parts']],visible={n:False for n in ['RobotWrist','WristPilotBoss','WristAdapter','DriveHousingReady','ClampServo','CutServo','Tray']})
 # Fade neighbouring bodies so computed red intersections are legible.
 for side in ['L','R']:
  edit('Neighbour'+side+'Berry',ViewObject={'Transparency':55,'Visibility':True})
  show('NarrowClash'+side,True)
 carrier_clash=R['narrow']['carrier_stem'].get('volume',{}).get('volume_mm3',0)>0
 capture('05_narrow_gap.png','10 mm GAP | NOSE INTERFERENCE',
  'Intentionally retained for stage 2 | red = actual Boolean common volume',
  ['The neighbour gap changed from 15 mm to 10 mm using one spreadsheet cell.',
   'Nose clashes with fruit'+('; open cutter carrier also meets left stem.' if carrier_clash else '.')+' No repair applied.'],
  view='viewTop',camera={'center':[0,-4,-8],'height':94})
 for side in ['L','R']:
  edit('Neighbour'+side+'Berry',ViewObject={'Transparency':0})
  show('NarrowClash'+side,False)
 if carrier_clash:show('NarrowCarrierStemL',False)
 setcells({'NeighbourGap':15})
 gui_batch(M['parts'])
 gui_batch(visible={p['name']:False for p in M['parts']})
 for n in ['MovingJaw','MovingTPU','JawPin']:show(n,True)
 capture('06_fem.png','JAW LEVER | BEAM-CALCULATION FALLBACK',
  'FEM setup failure recorded by MCP | conservative minimum-section estimate at 10 N',
  ['The right-hand image is the actual printed moving jaw and M3 pin from the model.',
   'Beam result is not a stress plot. Pin-hole stress concentration and print anisotropy need validation.'],
  view='viewTop',camera={'center':[-7,-18,3],'height':62},
  card=['PLA | PIN-FIXED CANTILEVER','Pad force F = 10 N; reach L = 15 mm',
        'Minimum section b = 6 mm; h = 3.5 mm','E = 3500 MPa; yield = 50 MPa',
        'I = b h³ / 12 = 21.4375 mm⁴','Stress = F L h / (2 I) = 12.245 MPa',
        'Deflection = F L³ / (3 E I) = 0.150 mm','Safety factor = 50 / 12.245 = 4.08',
        'Target SF >= 3: met by beam estimate','FEM: see exact failure in design-notes.md'])
 gui_batch(visible={p['name']:True for p in M['parts']})
 show('HeadEnvelope',False)
 show('ExplodedView',False)
 pose('clamp',0,13)
 capture('saved-view.png','STRAWBERRY PICKING HEAD',camera={'center':[0,-10,0],'height':175})
 call('save_document',selector={'document_name':DOC},required=False)
 persist()

def finalize():
 call('save_document',selector={'document_name':DOC},required=False)

def finish_evidence():
 R['analytic_sizes']=output_json(code("""import FreeCAD as App,json
D=App.getDocument('StrawberryHead')
r=sorted(set(round(e.Curve.Radius,9) for e in D.TargetBerry.Shape.Edges if hasattr(e.Curve,'Radius')))
print(json.dumps({'berry_circle_radii_mm':r,'berry_max_diameter_mm':2*max(r),'revolution_angle_deg':float(D.TargetRevolution.Angle),'blade_longest_edge_mm':max(e.Length for e in D.HobbyBlade.Shape.Edges),'blade_thickness_mm':float(D.HobbyBladePad.Length)}))
"""))
 persist()

def polish_stills():
 # Presentation revisions after inspecting the six native exports.
 gui_batch(M['parts'],visible={'HeadEnvelope':False,'ExplodedView':False})
 call('set_section_view',enabled=False)
 capture('01_scene.png','STRAWBERRY PICKING HEAD | DESIGN GATE',
  'Mounted, driven picking head | touches the stem | 15 mm neighbour gap',
  ['Clamp first, shear above the clamp, withdraw with the berry hanging, lower into the tray, open.',
   'Grey = bought hardware | teal / amber / violet = printed parts | green = replaceable TPU pads'],
  orientation=view_from([1,2,1.7]),camera={'center':[-15,35,7],'height':380})
 code("""import FreeCAD as App
D=App.getDocument('StrawberryHead')
for n,offset in [('MovingTPU',(35,55,25)),('HobbyBlade',(-25,40,45)),('BladeClamp',(-25,40,58))]:
 o=D.getObject('Exploded_'+n);p=o.Placement;p.Base=D.getObject(n).getGlobalPlacement().Base+App.Vector(*offset);o.Placement=p
print('Separated pad, bought blade and blade clamp in the exploded presentation only')
""")
 gui_batch(visible={**{p['name']:False for p in M['parts']},'ExplodedView':True})
 capture('04_parts.png','PRINTED PARTS + BOUGHT HARDWARE',
  'Exploded actual part geometry | flat print faces | servo pockets, pins, fasteners and blade clamp',
  ['Teal = structure | amber = jaw and clamp link | violet = cutter and cut link | green = TPU cartridges.',
   'Grey = bought hardware. Full quantities, materials and mass estimate are in design-notes.md.'],
  orientation=view_from([1,2,1.7]),camera={'center':[0,-10,37],'height':310})
 gui_batch(M['parts'],visible={'ExplodedView':False})
 pose('cut',0,-13)
 keep={'NoseFrameReady','MovingJaw','MovingTPU','FixedTPU','BladeLever','HobbyBlade','BladeClamp','JawPin','CutterPin','JawLowerSpacer','JawUpperSpacer','CutLowerSpacer','JawPivotLocknut','CutPivotLocknut','TargetBerry','TargetCap','TargetStem','PlantStemStub'}
 keep.update(p['name'] for p in M['parts'] if p['name'].startswith('BladeClampM2'))
 gui_batch([{**p,'transparency':75} for p in M['parts'] if p['name'] in ['BladeLever','BladeClamp']],visible={p['name']:p['name'] in keep for p in M['parts']})
 call('set_section_view',enabled=True,base=[0,0,0],normal=[0,1,0],no_manip=True)
 capture('02_closeup.png','STEM CONTACT | CLAMP BEFORE CUT',
  'Section at Y = 0 | parallel 3 mm pad gap | blade plane Z = 6.7 mm, on the plant side',
  ['Moving pad Z = 0–6 mm; fixed pad Z = 0–4.2 mm; bypass blade Z = 6.7–7.1 mm.',
   'Rear drive hidden; cutter carrier translucent. Fruit and cap remain below the jaws.'],
  view='viewFront',camera={'center':[0,0,-2],'height':46})
 call('set_section_view',enabled=False)
 gui_batch(M['parts'])
 pose('clamp',0,13)
 capture('saved-view.png','STRAWBERRY PICKING HEAD',orientation=view_from([1,2,1.7]),camera={'center':[-15,35,7],'height':380})
 R['final_controls']=call('spreadsheet_get_cells',sheet_name='Motion',addresses=list(M['motion_cells'].values()))
 R['final_scene_readback']=output_json(code("""import FreeCAD as App,json
D=App.getDocument('StrawberryHead')
def bounds(n):
 b=D.getObject(n).Shape.BoundBox;return [b.XLength,b.YLength,b.ZLength]
print(json.dumps({'berry_dimensions_mm':{n:bounds(n) for n in ['TargetBerry','NeighbourLBerry','NeighbourRBerry']},'servo_dimensions_mm':{n:bounds(n) for n in ['ClampServo','CutServo']},'stem_diameter_mm':D.TargetStem.Shape.BoundBox.XLength,'neighbour_centres_x_mm':[D.NeighbourL.Placement.Base.x,D.NeighbourR.Placement.Base.x],'physical_parts':sum(1 for o in D.Objects if hasattr(o,'Category') and o.Category in ['printed','bought'])}))
"""))
 call('save_document',selector={'document_name':DOC},required=False)
 persist()

def travel_endpoint():
 # The seven regular samples end at -11 degrees; explicitly include full cut.
 pose('travel_endpoint',0,-13)
 pairs=[('MovingJaw','ClampLink'),('MovingJaw','BladeLever'),('BladeLever','CutLink'),('ClampLink','CutLink'),('BladeLever','DriveHousingReady'),('MovingJaw','DriveHousingReady'),('MovingJaw','NoseFrameReady'),('BladeLever','NoseFrameReady'),('HobbyBlade','CutterPin'),('HobbyBlade','NoseFrameReady'),('HobbyBlade','CutLowerSpacer'),('BladeClamp','NoseFrameReady'),('CutLink','DriveHousingReady')]
 checks={a+'--'+b:common(a,b,'Endpoint'+a+b) for a,b in pairs}
 R['travel'].append({'jaw_angle':0,'cutter_angle':-13,'checks':checks})
 persist()
 pose('clamp')

def path_stems():
 R['neighbour_stem_paths']={}
 for name,points in [('approach',[{'x':0,'y':0,'z':float(z)} for z in [15,12,9,6,3,0]]),('withdraw',[{'x':0,'y':-25*t/5,'z':20*t/5} for t in range(6)])]:
  pose('approach_path_reference',-18,13,0,0) if name=='approach' else pose('cut',0,-13)
  chunks=[]
  for point in points:
   result=call('common_volume_along_path',moving_object='HeadEnvelope',obstacle_objects=['NeighbourLStem','NeighbourRStem','NeighbourLBranch','NeighbourRBranch'],samples=[point],required=False)
   chunks.append(result)
   R['neighbour_stem_paths'][name]={'sample_count':len(chunks),'requested_samples':points,'chunks':chunks}
   persist()
   if not events[-1]['result']['ok']:raise RuntimeError('Stem path sample failed; check native readiness')
 pose('clamp')

def correct_approach_paths():
 # The world-space aggregate embeds the head offset in its geometry. Path
 # samples are absolute object placements, so generate it with HeadZ=0 first.
 R['discarded_offset_approach']={'fruit_cap':R['paths']['approach'],'stem_branch':R.get('neighbour_stem_paths',{}).get('approach')}
 R['transmission']={tag:[linkage(tag,a/10)[1] for a in (range(-180,1) if tag=='Clamp' else range(-130,131))] for tag in ['Clamp','Cut']}
 pose('approach_path_reference',-18,13,0,0)
 points=[{'x':0,'y':0,'z':float(z)} for z in [15,12,9,6,3,0]]
 for group,obstacles in [('fruit_cap',['NeighbourLBerry','NeighbourLCap','NeighbourRBerry','NeighbourRCap']),('stem_branch',['NeighbourLStem','NeighbourRStem','NeighbourLBranch','NeighbourRBranch'])]:
  chunks=[]
  for point in points:
   result=call('common_volume_along_path',moving_object='HeadEnvelope',obstacle_objects=obstacles,samples=[point],required=False)
   chunks.append(result)
   data={'sample_count':len(chunks),'requested_samples':points,'chunks':chunks,'reference':'World geometry regenerated at HeadZ=0; samples are absolute placements'}
   if group=='fruit_cap':R['paths']['approach']=data
   else:R['neighbour_stem_paths']['approach']=data
   persist()
   if not events[-1]['result']['ok']:raise RuntimeError('Corrected approach sample failed; check native readiness')
 R['path_frame_correction']='Initial approach results embedded the 15 mm offset in the validation compound and were discarded. Corrected results regenerate the compound at HeadZ=0, then sample absolute Z=15 to 0 mm. Withdraw was already generated at HeadZ=0 and is unchanged.'
 pose('clamp')
 persist()
 call('save_document',selector={'document_name':DOC},required=False)

def resume_gate():
 R['capture_start_request_status']=call('get_request_status',request_id='844e2d39-6f7f-56d7-a0bb-af160889e9b3',required=False)
 state=call('get_mutation_readiness',required=False)
 recompute_requested=False
 while not state.get('ready',False):
  if 'pending_recompute' in state.get('reasons',[]) and not any(d.get('notification_replay') or d.get('recomputing') for d in state.get('documents',[])) and not recompute_requested:
   R['recovery_recompute']=call('recompute_document',required=False)
   recompute_requested=True
   persist()
  time.sleep(5);state=call('get_mutation_readiness',required=False)
 gap=call('spreadsheet_get_cells',sheet_name='Dims',addresses=[M['cells']['NeighbourGap']])
 for cell in gap.get('cells',[]):_cell_cache[cell['alias']]=cell['value']
 motion=call('spreadsheet_get_cells',sheet_name='Motion',addresses=list(M['motion_cells'].values()))
 for cell in motion.get('cells',[]):_cell_cache[cell['alias']]=cell['value']
 if 'NeighbourGap' not in M.get('motion_cells',{}):
  row=len(M['motion_cells'])+1
  call('spreadsheet_set_cells',sheet_name='Motion',cells=[{'address':'A'+str(row),'value':'Neighbour surface gap mm'},{'address':'B'+str(row),'value':str(_cell_cache['NeighbourGap']),'alias':'NeighbourGap'}])
  M['motion_cells']['NeighbourGap']='B'+str(row)
  (OUT/'design-manifest.json').write_text(json.dumps(M,indent=2))
  R['gap_motion_control']=output_json(code("""import FreeCAD as App,json
D=App.getDocument('StrawberryHead');changed=[]
for o in D.Objects:
 for p,e in list(getattr(o,'ExpressionEngine',[])):
  if 'Dims.NeighbourGap' in str(e):
   o.setExpression(p,str(e).replace('Dims.NeighbourGap','Motion.NeighbourGap'));changed.append([o.Name,p])
print(json.dumps({'bindings':changed,'note':'Motion.NeighbourGap is the driving scene control; Dims.NeighbourGap retains the nominal design input. No printed or bought part geometry changes.'}))
"""))
  persist()
 R['final_printed_solids']=output_json(code("""import FreeCAD as App,json
D=App.getDocument('StrawberryHead')
print(json.dumps({o.Name:{'solids':len(o.Shape.Solids),'state':list(o.State)} for o in D.Objects if hasattr(o,'Category') and o.Category=='printed' and hasattr(o,'Shape')}))
"""))
 persist()
 correct_approach_paths()
 stills()

def final_stage():
 housing_clearance()
 path_stems()
 travel_endpoint()
 mass_sheet()
 stills()

def all_checks():
 engineering()
 fem()
 mass()

def remaining_checks():
 resume_paths()
 travel_checks()
 fem()
 mass()

if __name__=='__main__':
 try: globals()[sys.argv[1]]()
 finally: C.close()
