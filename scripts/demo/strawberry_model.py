"""Executed ONLY by the MCP execute_code tool. Native parametric sketches/pads/pockets.
All numeric design inputs, including sketch coordinates, are spreadsheet cells.
No direct RPC, GUI geometry, imported BREP, or external CAD generation.
"""
import FreeCAD as App
import Part, Sketcher, math, json
D=App.getDocument('StrawberryHead')
S=D.getObject('Dims')
row=0
params=[]
numeric={}
def cell(alias,value,description=''):
 global row
 row+=1
 S.set('A'+str(row),description or alias)
 S.set('B'+str(row),str(value))
 S.setAlias('B'+str(row),alias)
 numeric[alias]=eval(str(value).lstrip('=').replace('Dims.','').replace('^','**'),{'__builtins__':{}},numeric)
 params.append({'row':row,'alias':alias,'value':str(value),'description':description or alias})
 return 'Dims.'+alias

def val(expr):
 if isinstance(expr,(int,float)): return float(expr)
 return float(eval(expr.replace('Dims.','').replace('^','**'),{'__builtins__':{}},numeric))

inputs=[('BerryWidth',30),('BerryLength',35),('StemDia',3),('NeighbourGap',15),('CapRadius',9),('CapThickness',2),('BerryTop',-8),('Wall',2.4),('PlateThickness',6),('FlangePCD',50),('PilotDia',31.5),('PilotDepth',3),('M6Clear',6.6),('ThreadEngage',6),('ScrewLength','=PlateThickness + ThreadEngage'),('ServoX',22.5),('ServoY',12.2),('ServoZ',22.7),('ServoTabs',32.2),('M2Clear',2.4),('M3Clear',3.2),('PadThick',2),('PadHeight',6),('PadDepth',8),('JawWidth',7),('JawThickness',6),('JawPivotX',9),('JawPivotY',-12),('CutPivotX',-8),('CutPivotY',0),('InputArm',24),('JawOutputArm',15),('CutOutputArm',8),('HornRadius',6),('BladeLength',39),('BladeThick',0.4),('BladeWidth',6),('BladeZ',6.7),('StallTorque',176),('TorqueSafety',2),('WorkTorque','=StallTorque / TorqueSafety'),('ClampForce','=WorkTorque / HornRadius * InputArm / JawOutputArm'),('CutForce','=WorkTorque / HornRadius * InputArm / CutOutputArm'),('ClampRequired',10),('CutRequired',15),('ClampMargin','=ClampForce / ClampRequired'),('CutMargin','=CutForce / CutRequired'),('YoungMPa',3500),('YieldMPa',50),('BeamLength',15),('BeamWidth',6),('BeamDepth',3.5),('BeamLoad',10),('BeamI','=BeamWidth * BeamDepth^3 / 12'),('BeamStress','=BeamLoad * BeamLength * BeamDepth / (2 * BeamI)'),('BeamDeflection','=BeamLoad * BeamLength^3 / (3 * YoungMPa * BeamI)'),('BeamSF','=YieldMPa / BeamStress'),('PLADensity',1.24),('Infill',0.4),('ServoMass',9),('BladeMass',1.3),('HeadX',0),('HeadY',0),('HeadZ',0),('JawAngle',0),('CutAngle',12),('ClampServoAngle',90),('CutServoAngle',-90),('ClampLinkLength',math.hypot(24,3)),('CutLinkLength',math.hypot(24,6)),('ClampLinkAngle',math.degrees(math.atan2(3,24))),('CutLinkAngle',math.degrees(math.atan2(6,-24))),('TargetY',0),('TargetZ',0),('Explode',0)]
for a,v in inputs: cell(a,v)
# Labels deliberately contain no supplier names. Dimensions identify commodity parts.
printed=[]; bought=[]; scene=[]; parts=[]
colors={'printed':(0.13,0.47,0.59),'jaw':(0.94,0.62,0.20),'cutter':(0.43,0.38,0.65),'pad':(0.22,0.68,0.57),'bought':(0.59,0.62,0.65),'scene':(0.65,0.69,0.72),'berry':(0.78,0.12,0.18),'cap':(0.24,0.46,0.20)}

def exprval(x,alias):
 if isinstance(x,str): return cell(alias,'='+x)
 return cell(alias,x)

def body(name,kind='printed',material='PLA',color=None,parent=None):
 b=D.addObject('PartDesign::Body',name)
 b.addProperty('App::PropertyString','Category','BOM'); b.Category=kind
 b.addProperty('App::PropertyString','MaterialNote','BOM'); b.MaterialNote=material
 b.addProperty('App::PropertyString','PrintFace','BOM'); b.PrintFace='Flat XY face; 2.4 mm minimum housing walls' if kind=='printed' else 'Purchased or scene reference'
 (printed if kind=='printed' else bought if kind=='bought' else scene).append(name)
 parts.append({'name':name,'kind':kind,'material':material,'color':color or colors.get(material,colors.get(kind,colors['scene']))})
 if parent: D.getObject(parent).addObject(b)
 return b

def poly_sketch(b,name,pts,z):
 sk=D.addObject('Sketcher::SketchObject',name); b.addObject(sk)
 # Offset avoids zero-valued DistanceX/DistanceY constraints.
 sk.Placement.Base=App.Vector(-100,-100,0)
 sk.setExpression('Placement.Base.z',exprval(z,name+'Z'))
 refs=[]
 for i,(x,y) in enumerate(pts):
  refs.append((exprval(x,name+'X'+str(i)),exprval(y,name+'Y'+str(i))))
 coords=[(val(x)+100,val(y)+100) for x,y in refs]
 for i,(x,y) in enumerate(coords):
  nx,ny=coords[(i+1)%len(coords)]
  sk.addGeometry(Part.LineSegment(App.Vector(x,y,0),App.Vector(nx,ny,0)),False)
 for i in range(len(coords)):
  sk.addConstraint(Sketcher.Constraint('Coincident',i,2,(i+1)%len(coords),1))
  for axis,j in [('DistanceX',0),('DistanceY',1)]:
   ci=sk.addConstraint(Sketcher.Constraint(axis,i,1,coords[i][j]))
   sk.setExpression('Constraints['+str(ci)+']',refs[i][j]+' + 100')
 return sk

def circle_sketch(b,name,circles,z):
 sk=D.addObject('Sketcher::SketchObject',name); b.addObject(sk)
 sk.Placement.Base=App.Vector(-100,-100,0); sk.setExpression('Placement.Base.z',exprval(z,name+'Z'))
 for i,(x,y,r) in enumerate(circles):
  xr,yr,rr=[exprval(v,name+k+str(i)) for v,k in [(x,'X'),(y,'Y'),(r,'R')]]
  gi=sk.addGeometry(Part.Circle(App.Vector(val(xr)+100,val(yr)+100,0),App.Vector(0,0,1),val(rr)),False)
  for typ,extra,vv,ee in [('DistanceX',[gi,3],val(xr)+100,xr+' + 100'),('DistanceY',[gi,3],val(yr)+100,yr+' + 100'),('Radius',[gi],val(rr),rr)]:
   ci=sk.addConstraint(Sketcher.Constraint(typ,*extra,vv)); sk.setExpression('Constraints['+str(ci)+']',ee)
 return sk

def feature(b,sk,name,length,pocket=False):
 f=b.newObject('PartDesign::Pocket' if pocket else 'PartDesign::Pad',name)
 f.Profile=sk; f.setExpression('Length',exprval(length,name+'Length')); f.setExpression('Length2','Length')
 b.Tip=f
 return f

def polygon(name,pts,z,t,kind='printed',material='PLA',color=None,parent=None):
 b=body(name,kind,material,color,parent)
 sk=poly_sketch(b,name+'Profile',pts,z); feature(b,sk,name+'Pad',t)
 return b

def box(name,x,y,z,l,w,h,**kw):
 def add(a,b): return str(a)+' + ('+str(b)+')'
 return polygon(name,[(x,y),(add(x,l),y),(add(x,l),add(y,w)),(x,add(y,w))],z,h,**kw)

def cylinder(name,x,y,z,r,h,**kw):
 b=body(name,**kw); sk=circle_sketch(b,name+'Profile',[(x,y,r)],z); feature(b,sk,name+'Pad',h); return b

def holes(b,name,cs,z,depth):
 sk=circle_sketch(b,name+'Profile',cs,z); return feature(b,sk,name,depth,True)

def rectpocket(b,name,x,y,l,w,z,depth):
 sk=poly_sketch(b,name+'Profile',[(x,y),(str(x)+'+('+str(l)+')',y),(str(x)+'+('+str(l)+')',str(y)+'+('+str(w)+')'),(x,str(y)+'+('+str(w)+')')],z)
 return feature(b,sk,name,depth,True)

# Mount: four bolt seats, underside pilot recess, continuous load path to pods.
plate=cylinder('WristAdapter',0,-65,45,34,'Dims.PlateThickness')
holes(plate,'FlangeBolts',[(25,-65,'Dims.M6Clear/2'),(0,-40,'Dims.M6Clear/2'),(-25,-65,'Dims.M6Clear/2'),(0,-90,'Dims.M6Clear/2')],51,8)
holes(plate,'PilotRecess',[(0,-65,'Dims.PilotDia/2')],51,'Dims.PilotDepth')
for i,(x,y) in enumerate([(25,-65),(0,-40),(-25,-65),(0,-90)]):
 cylinder('FlangeScrew'+str(i+1),x,y,45,3,'Dims.ScrewLength',kind='bought',material='steel')
 cylinder('FlangeScrewHead'+str(i+1),x,y,43,5,2,kind='bought',material='steel')
# Two columns screw to adapter; thick floor joins the servo pockets and nose.
for sign in [-1,1]:
 x=sign*12-4
 b=box('MountColumn'+('L' if sign<0 else 'R'),x,-69,16,8,18,29)
 holes(b,b.Name+'Bolts',[(sign*12,-60,1.7)],45,35)
 cylinder('ColumnBolt'+('L' if sign<0 else 'R'),sign*12,-60,12,1.5,36,kind='bought',material='steel')
base=box('Chassis',-34,-57,13,68,48,3)
rectpocket(base,'ClampFloorClearance',-26.55,-51.4,23.1,12.8,16,4)
rectpocket(base,'CutFloorClearance',4.45,-30.4,23.1,12.8,16,4)
# Relief below servo outputs, cable route through the rear edge.
holes(base,'OutputReliefs',[(-15,-45,4.5),(16,-24,4.5)],16,5)
rectpocket(base,'CableChannel',-5,-57,10,28,16,1)
for tag,cx,cy in [('Clamp',-15,-45),('Cut',16,-24)]:
 b=box(tag+'ServoPocket',cx-19,cy-9,16,38,18,23)
 rectpocket(b,tag+'MotorCavity',cx-11.55,cy-6.4,23.1,12.8,39,26)
 # Tab seats are 2 mm below tabs; M2 clearance passes through the ledges.
 rectpocket(b,tag+'TabRecess',cx-17,cy-6.4,34,12.8,39,7)
 holes(b,tag+'TabHoles',[(cx-14.8,cy,1.2),(cx+14.8,cy,1.2)],34,24)
 rectpocket(b,tag+'WireExit',cx-3,cy-9,6,3,22,6)
 box(tag+'Servo',cx-11.25,cy-6.1,15 if tag=='Cut' else 14,22.5,12.2,22.7,kind='bought',material='micro servo envelope')
 tab=box(tag+'ServoTabs',cx-16.1,cy-6.1,32,'Dims.ServoTabs','Dims.ServoY',2,kind='bought',material='servo tabs')
 holes(tab,tag+'TabScrewHoles',[(cx-14.8,cy,1.2),(cx+14.8,cy,1.2)],34,3)
 cylinder(tag+'OutputShaft',cx,cy,9.5,2.5,5.5 if tag=='Cut' else 4.5,kind='bought',material='servo output')
 for i,s in enumerate([-1,1]):
  cylinder(tag+'M2Screw'+str(i),cx+s*14.8,cy,26,1,9,kind='bought',material='steel')
  cylinder(tag+'M2Head'+str(i),cx+s*14.8,cy,34,1.9,1.2,kind='bought',material='steel')
 # Small cable in the channel, exits behind chassis.
 box(tag+'Cable',cx-1.5,cy-14,17,3,8,2,kind='bought',material='cable')
# Nose cheek rails deliberately retain a 10 mm neighbour-gap interference.
for tag,x in [('L',-29),('R',22)]:
 b=box('NoseCheek'+tag,x,-16,-28,7,20,37)
 holes(b,'CheekBolt'+tag,[(x+3.5,-12.5,1.2)],11,8)
 cylinder('CheekM2'+tag,x+3.5,-12.5,4,1,10,kind='bought',material='steel')
# Front bridge connects the rail, fixed jaw and the two fork supports.
box('NoseBridge',-29,-16,9,58,7,4)
fixed=box('FixedJaw',-9.5,-7,0,6,14,6.6,color=colors['jaw'])
box('FixedJawRoot',-9.5,-13,0,7,6,11,color=colors['jaw'])
# Screw attached fixed jaw root to bridge; the pad is a slide-in replaceable cartridge.
for i,y in enumerate([-10,-3]): cylinder('FixedJawM2'+str(i),-6.5,y,2,1,9,kind='bought',material='steel')
box('FixedTPU',-3.5,-4,0,'Dims.PadThick','Dims.PadDepth','Dims.PadHeight',material='TPU',color=colors['pad'])
# Jaw rotor local origin is its pin, ensuring a true revolute placement.
D.addObject('App::Part','JawRotor')
jaw=polygon('MovingJaw',[(-5.5,-27.5),(3.5,-27.5),(3.5,3),(-2,15),(-5.5,15),(-5.5,9),(-3.5,-1)],0,'Dims.JawThickness',color=colors['jaw'],parent='JawRotor')
holes(jaw,'JawPinHole',[(0,0,'Dims.M3Clear/2'),(0,'-Dims.InputArm',1.2)],6,8)
# Pad x=1.5 in the clamped pose; flat pad face parallel to fixed TPU.
box('MovingTPU',-7.5,8,0,'Dims.PadThick','Dims.PadDepth','Dims.PadHeight',material='TPU',color=colors['pad'],parent='JawRotor')
# The pad backing connects to the lever's angled tip.
box('PadBacking',-5.5,8,0,3,8,6,color=colors['jaw'],parent='JawRotor')
for z,n in [(-3,'Lower'),(9,'Upper')]:
 b=box('JawFork'+n,5,-16,z,9,9,2,color=colors['printed'])
 holes(b,'JawForkHole'+n,[(9,-12,1.6)],z+2,4)
cylinder('JawPin',9,-12,-3,1.5,15,kind='bought',material='steel')
cylinder('JawPinHead',9,-12,-4.5,2.7,1.5,kind='bought',material='steel')
# Cutting pivot and blade clamp. #11 envelope, edge sweeps across plant-side stem.
D.addObject('App::Part','CutterRotor')
cut=polygon('BladeLever',[(-4.5,-27.5),(4.5,-27.5),(4.5,-3),(4.5,3),(-30,3),(-30,-3),(-4.5,-3)],7.2,3,color=colors['cutter'],parent='CutterRotor')
holes(cut,'CutterPinHoles',[(0,0,1.6),(0,-24,1.2),(-21,0,1.2),(-12,0,1.2)],10.2,4)
blade=polygon('HobbyBlade',[('-Dims.BladeLength+10.5',0),(10.5,0),(2,6),('-Dims.BladeLength+10.5',6)],'Dims.BladeZ','Dims.BladeThick',kind='bought',material='hobby blade steel',parent='CutterRotor')
# Printed two screw clamp holds blade shank against the lever; blade is removable.
box('BladeClamp',-27,0,4.3,20,7,2.4,color=colors['cutter'],parent='CutterRotor')
for i,x in enumerate([-21,-12]): cylinder('BladeClampM2'+str(i),x,3.5,3.5,1,8,kind='bought',material='steel',parent='CutterRotor')
for z,n in [(3,'Lower'),(10.5,'Upper')]:
 b=box('CutterFork'+n,-12,-13,z,8,17,2.4)
 holes(b,'CutterForkHole'+n,[(-8,0,1.6)],z+2.4,4)
cylinder('CutterPin',-8,0,2.5,1.5,12,kind='bought',material='steel')
cylinder('CutterPinHead',-8,0,1,2.7,1.5,kind='bought',material='steel')
# Horns and couplers use actual four-bar endpoint positions. Both pad and cutter
# force budgets use the same radius/lever cells that drive these sketches.
for tag,cx,cy,z in [('Clamp',-15,-45,8.5),('Cut',16,-24,12.5)]:
 D.addObject('App::Part',tag+'HornRotor')
 h=box(tag+'Horn',-2,-2,z,'Dims.HornRadius+4',4,2,kind='bought',material='servo horn',parent=tag+'HornRotor')
 holes(h,tag+'HornHole',[(0,0,1),(6,0,1.2)],z+2,3)
 D.addObject('App::Part',tag+'LinkRotor')
 link=box(tag+'Link',-3.5,-3.5,z-2.2,'Dims.'+tag+'LinkLength+7',7,2,color=colors['cutter'] if tag=='Cut' else colors['jaw'],parent=tag+'LinkRotor')
 holes(link,tag+'LinkHoles',[(0,0,1.2),('Dims.'+tag+'LinkLength',0,1.2)],z-0.2,3)
 for endpoint in ['Horn','Lever']:
  # Pins are placed by expressions after the loops are solved in driver.
  cylinder(tag+endpoint+'LinkPin',0,0,z-2.2,1,4.5,kind='bought',material='steel',parent=tag+'LinkRotor')
# Scene: smooth revolved strawberry bodies, cap and stem. Each fruit has a
# separate placement carrier so target moves with the head after the cut.
for tag in ['Target','NeighbourL','NeighbourR']:
 root=D.addObject('App::Part',tag)
 b=body(tag+'Berry','scene','berry',colors['berry'],tag)
 # Revolve a sampled fruit profile about its vertical sketch axis, a true solid
 # of revolution, not a display mesh or overlapping primitives.
 pts=[(0,0),(3,1),(7,4),(11,9),(14,16),(15,22),(14,28),(11,33),(7,35),(0,35)]
 scaled=[('Dims.BerryWidth * '+str(x/30),'Dims.BerryLength * '+str(y/35)) for x,y in pts]
 sk=poly_sketch(b,tag+'FruitProfile',scaled,0)
 # Profile is in XZ: translate the sketch offset and rotate the sketch plane.
 sk.Placement=App.Placement(App.Vector(-100,0,-143),App.Rotation(App.Vector(1,0,0),90))
 # rotation maps sketch y -> z, with offset chosen to retain -43..-8 extent
 sk.setExpression('Placement.Base.z','Dims.BerryTop - Dims.BerryLength - 100')
 rev=b.newObject('PartDesign::Revolution',tag+'Revolution'); rev.Profile=sk
 # vertical local sketch axis passes through sketch x=100; custom axis reference
 # is a construction line in the same plane, not the shifted V_Axis.
 ai=sk.addGeometry(Part.LineSegment(App.Vector(100,90,0),App.Vector(100,150,0)),True)
 rev.ReferenceAxis=(sk,['Axis0']); rev.Angle=360; b.Tip=rev
 cap=cylinder(tag+'Cap',0,0,'Dims.BerryTop', 'Dims.CapRadius','Dims.CapThickness',kind='scene',material='cap',color=colors['cap'],parent=tag)
 stem=cylinder(tag+'Stem',0,0,'Dims.BerryTop+Dims.CapThickness','Dims.StemDia/2',30,kind='scene',material='stem',color=colors['cap'],parent=tag)
 root.setExpression('Placement.Base.x', '0' if tag=='Target' else ('-' if tag=='NeighbourL' else '')+'(Dims.BerryWidth + Dims.NeighbourGap)')
 if tag=='Target':
  root.setExpression('Placement.Base.y','Dims.TargetY'); root.setExpression('Placement.Base.z','Dims.TargetZ')
# Truss with three downward pedicels. A horizontal cylinder is expression-driven.
truss=cylinder('Truss',0,0,0,2.5,120,kind='scene',material='stem',color=colors['cap'])
truss.Placement=App.Placement(App.Vector(-60,0,24),App.Rotation(App.Vector(0,1,0),90))
# Tray is a single printable/reference shell with 3 mm base and 3 mm sides.
tray=box('Tray',-75,35,-68,150,95,18,kind='scene',material='tray',color=(0.68,0.76,0.79))
rectpocket(tray,'TrayInterior',-72,38,144,89,-50,15)
wrist=cylinder('RobotWrist',0,-65,51,28,37,kind='scene',material='robot wrist',color=(0.69,0.72,0.75))
holes(wrist,'WristPilot',[(0,-65,15.75)],54,3)
# Numeric linkage poses are updated by the scripted client from exact circle
# intersections, then stored in the spreadsheet; all geometry reads expressions.
for name,x,y,angle in [('JawRotor',9,-12,'JawAngle'),('CutterRotor',-8,0,'CutAngle'),('ClampHornRotor',-15,-45,'ClampServoAngle'),('CutHornRotor',16,-24,'CutServoAngle')]:
 o=D.getObject(name); o.Placement.Rotation=App.Rotation(App.Vector(0,0,1),val('Dims.'+angle))
 o.setExpression('Placement.Base.x',exprval(x,name+'X')); o.setExpression('Placement.Base.y',exprval(y,name+'Y'))
 o.setExpression('Placement.Rotation.Angle','Dims.'+angle+' * 1 deg')
for tag,cx,cy in [('Clamp',-15,-45),('Cut',16,-24)]:
 o=D.getObject(tag+'LinkRotor')
 o.Placement.Rotation=App.Rotation(App.Vector(0,0,1),0)
 o.setExpression('Placement.Base.x','Dims.'+tag+'HornRotorX + Dims.HornRadius * cos(Dims.'+tag+'ServoAngle * 1 deg)')
 o.setExpression('Placement.Base.y','Dims.'+tag+'HornRotorY + Dims.HornRadius * sin(Dims.'+tag+'ServoAngle * 1 deg)')
 o.setExpression('Placement.Rotation.Angle','Dims.'+tag+'LinkAngle * 1 deg')
 D.getObject(tag+'LeverLinkPin').setExpression('Placement.Base.x','Dims.'+tag+'LinkLength')
# A coarse FEM model will reference the real moving-jaw tip, not a dummy beam.
S.Label='Design parameters | mm, N, MPa, g | formulas in B cells'
print(json.dumps({'parameters':params,'printed':printed,'bought':bought,'scene':scene,'parts':parts,'cells':{x['alias']:'B'+str(x['row']) for x in params}}))
