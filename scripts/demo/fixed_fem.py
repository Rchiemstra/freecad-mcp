"""Re-solve the retained coarse jaw mesh through real MCP execute_code calls.
A public remesh can change the coarse mesh; this keeps Stage 2a comparable.
"""
import json
from stage2_support import d,OUT

def solve_retained_mesh(document='fem'):
 old=d.DOC;d.DOC=document
 try:
  solved=d.output_json(d.code("""import FreeCAD as App,json,os,subprocess,shutil
from pathlib import Path
from femtools import ccxtools
D=App.getDocument(%r);mesh=D.JawCoarseMesh.FemMesh
assert mesh.VolumeCount==1063 and mesh.NodeCount==367,(mesh.VolumeCount,mesh.NodeCount)
assert abs(D.MovingJaw.Shape.Volume-1886.0366874981528)<1e-6
assert abs(float(D.PadLoad10N.Force.getValueAs('N'))-10)<1e-9
solver=next(o for o in D.JawAnalysis.Group if hasattr(o,'AnalysisType') and hasattr(o,'WorkingDir'))
solver.AnalysisType='static'
work=Path('/demo/demo-out/stage3/fem-fixed');work.mkdir(exist_ok=True)
fea=ccxtools.FemToolsCcx(analysis=D.JawAnalysis,solver=solver)
fea.update_objects();fea.setup_working_dir(str(work));fea.setup_ccx()
prereq=fea.check_prerequisites();assert not prereq,prereq
fea.write_inp_file();inp=Path(fea.inp_file_name);assert inp.is_file()
assert D.JawCoarseMesh.FemMesh.VolumeCount==1063,'The retained mesh was changed'
proc=subprocess.run([fea.ccx_binary,'-i',inp.stem],cwd=str(inp.parent),env={**os.environ,'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'},capture_output=True,text=True,timeout=90)
(inp.parent/'solver.stdout').write_text(proc.stdout);(inp.parent/'solver.stderr').write_text(proc.stderr)
assert proc.returncode==0,{'return_code':proc.returncode,'stdout':proc.stdout,'stderr':proc.stderr}
frd=inp.with_suffix('.frd');assert frd.is_file()
print(json.dumps({'input':str(inp),'frd':str(frd),'return_code':proc.returncode,'nodes':mesh.NodeCount,'elements':mesh.VolumeCount,'force_N':float(D.PadLoad10N.Force.getValueAs('N')),'geometry_volume_mm3':D.MovingJaw.Shape.Volume,'mesh_reused':True}))
"""%document))
  assert solved and solved['return_code']==0
  result=d.output_json(d.code("""import FreeCAD as App,json,ObjectsFem
from rpc_server.fem_executor_ops.solver_resolution import defer_fem_presentation
from feminout.importCcxFrdResults import read_frd_result
from feminout import importToolsFem
from femresult import resulttools
D=App.getDocument(%r);parsed=read_frd_result(%r)
assert len(parsed['Results'])==1
with defer_fem_presentation(D) as pending:
 r=ObjectsFem.makeResultMechanical(D,'ReplayJawResults')
 rm=ObjectsFem.makeMeshResult(D,'ReplayJawResultsMesh');rm.FemMesh=importToolsFem.make_femmesh(parsed);r.Mesh=rm
 importToolsFem.fill_femresult_mechanical(r,parsed['Results'][0]);D.JawAnalysis.addObject(r)
 resulttools.add_disp_apps(r);resulttools.add_von_mises(r);resulttools.add_principal_stress_std(r);resulttools.fill_femresult_stats(r)
App._demo_fem_deferred=getattr(App,'_demo_fem_deferred',[])+[pending]
print(json.dumps({'result_object':r.Name,'stress_MPa':max(r.vonMises),'displacement_mm':max(r.DisplacementLengths),'yield_safety_factor':50/max(r.vonMises),'nodes':len(r.vonMises),'elements':D.JawCoarseMesh.FemMesh.VolumeCount,'force_N':float(D.PadLoad10N.Force.getValueAs('N')),'mesh_reused':True}))
"""%(document,solved['frd'])))
  assert result and result['elements']==1063 and result['nodes']==367,result
  assert abs(result['stress_MPa']-1.3673728648580374)<1e-6,result
  assert abs(result['displacement_mm']-.016612515745117476)<1e-7,result
  (OUT/'replay-fem.json').write_text(json.dumps({'solver':solved,'result':result,'mcp_tool':'execute_code','method':'Actual solver re-run on the unchanged retained mesh; official result importer'},indent=2))
  return result
 finally:d.DOC=old
