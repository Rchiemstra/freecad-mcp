"""Run after replay, before stopping its single GUI: read and validate every STEP."""
import json
from stage2_support import d,call,OUT,wait_ready
try:
 d.DOC='strawberry_head_v2';wait_ready()
 code="""import FreeCAD as App,Part,json
from pathlib import Path
D=App.getDocument('strawberry_head_v2');base=Path('/demo/examples/strawberry-picker');rows=[]
for path in [base/'assembly.step']+sorted((base/'parts').glob('*.step')):
 s=Part.Shape();s.read(str(path))
 expected=sum(o.Shape.Volume for o in D.Objects if hasattr(o,'Category') and o.Category in ['printed','bought'] and hasattr(o,'Shape')) if path.name=='assembly.step' else D.getObject(path.stem).Shape.Volume
 row={'file':str(path.relative_to(base)),'valid':s.isValid(),'solids':len(s.Solids),'volume_mm3':s.Volume,'native_volume_mm3':expected,'matches':abs(s.Volume-expected)<max(.01,expected*1e-6)}
 assert row['valid'] and row['solids'] and row['matches'],row
 rows.append(row)
print(json.dumps(rows))
"""
 result=call('execute_code',document=d.DOC,execution_mode='gui',recompute='none',code=code,allow_gui_geometry_loop=True)
 (OUT/'export-inspection.json').write_text(json.dumps(result,indent=2))
finally:d.C.close()
