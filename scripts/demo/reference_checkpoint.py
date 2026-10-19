"""Persist only the wrist reference bindings in a clean native checkpoint.
Close the unsaved replay first, then reopen a copy of the packaged input so
presentation layouts and temporary replay edits never enter the checkpoint.
"""
import json,shutil,time,sys
from pathlib import Path
import stage2_job as j
from stage2_support import d,call,wait_ready,OUT
from rework_presentation import bind_wrist

def snapshot():
 return j.ec("""import FreeCAD as App,json
D=App.getDocument('StrawberryHead')
print(json.dumps({'printed':{n:{'volume_mm3':D.getObject(n).Shape.Volume,'bounds_mm':[D.getObject(n).Shape.BoundBox.XMin,D.getObject(n).Shape.BoundBox.XMax,D.getObject(n).Shape.BoundBox.YMin,D.getObject(n).Shape.BoundBox.YMax,D.getObject(n).Shape.BoundBox.ZMin,D.getObject(n).Shape.BoundBox.ZMax]} for n in %r},'sheets':{sheet.Name:{cell:sheet.getContents(cell) for cell in sheet.getUsedCells()} for sheet in D.Objects if sheet.TypeId=='Spreadsheet::Sheet'}}))
"""%j.M['printed'])

if __name__=='__main__':
 try:
  if '--resume-open' in sys.argv:
   source=max(OUT.glob('reference-input-*/strawberry-head-v2.FCStd'),key=lambda p:p.stat().st_mtime)
   state=wait_ready();docs=state.get('documents',[]);assert len(docs)==1,docs
   d.DOC=docs[0]['document'];j.c.DOC=d.DOC
   __import__('stage2_support').MODEL_DOC=d.DOC
   opened=j.ec("import FreeCAD as App,json\nD=App.getDocument('StrawberryHead')\nprint(json.dumps({'name':D.Name,'file':D.FileName}))")
   assert Path(opened['file']).resolve()==source.resolve(),opened
  else:
   backup=OUT/('reference-input-'+str(time.time_ns()));backup.mkdir()
   source=backup/'strawberry-head-v2.FCStd'
   shutil.copyfile('/demo/examples/strawberry-picker/strawberry-head.FCStd',source)
   wait_ready();call('close_document',doc_name=d.DOC)
   info=call('open_document',path=str(source));d.DOC=info['document_name'];j.c.DOC=d.DOC
  import stage2_support
  stage2_support.MODEL_DOC=d.DOC
  wait_ready();before=snapshot();bind_wrist();wait_ready();after=snapshot()
  assert before==after,'Wrist bindings changed manufacturing geometry or spreadsheet contents'
  refs=j.ec("""import FreeCAD as App,json
D=App.getDocument('StrawberryHead')
print(json.dumps({n:list(D.getObject(n).ExpressionEngine) for n in ['RobotWrist','WristPilotBoss']}))
""")
  call('save_document_as',selector={'document_name':d.DOC},destination='/demo/demo-out/strawberry-head-v2.FCStd',overwrite=True)
  (OUT/'reference-checkpoint.json').write_text(json.dumps({'result':'PASS','printed_geometry_and_cells_unchanged':True,'before':before,'after':after,'reference_expressions':refs},indent=2)+'\n')
 finally:d.C.close()
