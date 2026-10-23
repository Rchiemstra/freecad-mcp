"""Bind the visual wrist reference and inspect the retained scene; no design edits."""
import json
import stage2_job as j
from stage2_support import d,call,wait_ready,OUT

def bind_wrist():
 for axis in 'xyz':
  call('set_expression',object_name='RobotWrist',prop_path='Placement.Base.'+axis,expression='Motion.Head'+axis.upper())
 for axis,base in [('x','0'),('y','Dims.WristAdapterProfileY0'),('z','Dims.WristAdapterProfileZ + Dims.PlateThickness - Dims.PilotDepth')]:
  call('set_expression',object_name='WristPilotBoss',prop_path='Placement.Base.'+axis,expression=base+' + Motion.Head'+axis.upper())
 call('recompute_document')

def layout_parts():
 # Rearrange only the existing display copies. Native manufacturing parts,
 # the packaged checkpoint and the retained parts still remain unchanged.
 return j.ec("""import FreeCAD as App,json
D=App.getDocument('StrawberryHead')
rows=[['WristAdapter','DriveHousingReady','NoseFrameReady','MovingJaw','BladeLever'],['ClampLink','CutLink','BladeClamp','FixedTPU','MovingTPU']]
for row,names in enumerate(rows):
 for col,name in enumerate(names):
  o=D.getObject('V2Display_'+name);bb=o.Shape.BoundBox
  o.Placement.Base+=App.Vector(-160+80*col-(bb.XMin+bb.XMax)/2,45-85*row-(bb.YMin+bb.YMax)/2,0)
for name in ['ClampServo','CutServo','HobbyBlade','JawPin','CutterPin','FrameBoltL','FlangeScrew1','ClampM2Screw0','JawPivotLocknut','BladeClampM20']:
 o=D.getObject('V2Display_'+name);bb=o.Shape.BoundBox
 o.Placement.Base.y+=-110-(bb.YMin+bb.YMax)/2
print(json.dumps({'display_only':True,'rows':rows,'bought_hardware_y_mm':-110}))
""")

if __name__=='__main__':
 try:
  info=call('open_document',path='/demo/demo-out/strawberry-head-v2.FCStd')
  d.DOC=info['document_name'];j.c.DOC=d.DOC
  (OUT/'document-name.json').write_text(json.dumps({'document_name':d.DOC}))
  wait_ready();bind_wrist()
  print(j.ec("""import FreeCAD as App,json
D=App.getDocument('StrawberryHead')
print(json.dumps({'head':list(D.PickingHead.Placement.Base),'wrist':list(D.RobotWrist.Placement.Base),'adapter':list(D.WristAdapter.getGlobalPlacement().Base),'bounds':{n:[list(D.getObject(n).Shape.BoundBox.getPoint(i)) for i in range(8)] for n in ['RobotWrist','Tray','TargetBerry','WristAdapter']}}))
"""),flush=True)
  d.code((d.ROOT/'scripts/demo/stage2_renderer.py').read_text().replace('/stage2/','/stage3/'))
 finally:d.C.close()
