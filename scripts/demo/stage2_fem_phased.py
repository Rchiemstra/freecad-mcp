# Executed by fem.py: every stage below is an MCP execute_code request.
def run_phased_fem():
 F['phased_fallback']={'reason':'Public run_fem_analysis rejects UNSUPPORTED_NATIVE_PHASE_BOUNDARY. Use separate native commit boundaries; no intermediate recompute or GUI attachment in model callbacks.'}
 def mesh_stage():
  F['mesh_generation']=ec("""import FreeCAD as App,json
from femmesh.gmshtools import GmshTools
D=App.getDocument('JawFEM');gm=GmshTools(D.JawCoarseMesh);gm.create_mesh()
assert D.JawCoarseMesh.FemMesh.VolumeCount>0,'Gmsh produced no solid elements'
print(json.dumps({'nodes':D.JawCoarseMesh.FemMesh.NodeCount,'volume_elements':D.JawCoarseMesh.FemMesh.VolumeCount,'working_directory':D.JawCoarseMesh.WorkingDirectory}))
""")
 phase('fem_gmsh_generate',mesh_stage)
 (OUT/'fem.json').write_text(json.dumps(F,indent=2))
 assert F.get('mesh_generation'), 'Meshing failed'
 def setup_solver():
  F['solver_setup']=ec("""import FreeCAD as App,json,os
from rpc_server.fem_executor_ops.solver_resolution import defer_fem_presentation,resolve_solver
D=App.getDocument('JawFEM')
with defer_fem_presentation(D) as pending:
 solver=resolve_solver(D,D.JawAnalysis)
 solver.AnalysisType='static'
 solver.WorkingDir='/demo/demo-out/stage2/fem_solver/solve'
os.makedirs(solver.WorkingDir,exist_ok=True)
App._ab_fem_deferred=getattr(App,'_ab_fem_deferred',[])+[pending]
print(json.dumps({'solver':solver.Name,'type':solver.TypeId,'analysis_type':solver.AnalysisType}))
""")
 phase('fem_solver_setup',setup_solver)
 (OUT/'fem.json').write_text(json.dumps(F,indent=2))
 assert F.get('solver_setup'), 'Solver setup failed'
 def execute_solver():
  F['solver_execution']=ec("""import FreeCAD as App,json,os,subprocess
from pathlib import Path
from femtools import ccxtools
D=App.getDocument('JawFEM');solver=D.getObject(%r)
fea=ccxtools.FemToolsCcx(analysis=D.JawAnalysis,solver=solver)
fea.update_objects();fea.setup_working_dir('/demo/demo-out/stage2/fem_solver/solve');fea.setup_ccx()
prereq=fea.check_prerequisites();assert not prereq,prereq
fea.write_inp_file();assert fea.inp_file_name,'No input file'
input_path=Path(fea.inp_file_name)
proc=subprocess.run([fea.ccx_binary,'-i',input_path.stem],cwd=str(input_path.parent),env={**os.environ,'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'},capture_output=True,text=True,timeout=90)
fea.ccx_stdout=proc.stdout;fea.ccx_stderr=proc.stderr;rc=proc.returncode
(input_path.parent/'ccx.stdout').write_text(proc.stdout);(input_path.parent/'ccx.stderr').write_text(proc.stderr)
assert rc==0,{'return_code':rc,'stdout':fea.ccx_stdout,'stderr':fea.ccx_stderr}
assert os.path.isfile(os.path.splitext(fea.inp_file_name)[0]+'.frd')
print(json.dumps({'return_code':rc,'input_file':fea.inp_file_name,'ccx_stdout':fea.ccx_stdout}))
"""%F['solver_setup']['solver'])
 phase('fem_ccx_execute',execute_solver)
 (OUT/'fem.json').write_text(json.dumps(F,indent=2))
 assert F.get('solver_execution'),'Solver failed'
 def import_results():
  inp=F['solver_execution']['input_file']
  F['solver_import']=ec("""import FreeCAD as App,json,os,ObjectsFem
from rpc_server.fem_executor_ops.solver_resolution import defer_fem_presentation
from feminout.importCcxFrdResults import read_frd_result
from feminout import importToolsFem
from femresult import resulttools
D=App.getDocument('JawFEM');parsed=read_frd_result(os.path.splitext(%r)[0]+'.frd')
assert len(parsed['Results'])==1,'Expected one static load increment'
with defer_fem_presentation(D) as pending:
 r=ObjectsFem.makeResultMechanical(D,'JawResults')
 rm=ObjectsFem.makeMeshResult(D,'JawResultsMesh');rm.FemMesh=importToolsFem.make_femmesh(parsed);r.Mesh=rm
 importToolsFem.fill_femresult_mechanical(r,parsed['Results'][0]);D.JawAnalysis.addObject(r)
 resulttools.add_disp_apps(r);resulttools.add_von_mises(r);resulttools.add_principal_stress_std(r);resulttools.fill_femresult_stats(r)
App._ab_fem_deferred=getattr(App,'_ab_fem_deferred',[])+[pending]
print(json.dumps({'result_object':r.Name,'nodes':len(r.vonMises),'max_von_mises_MPa':max(r.vonMises),'max_displacement_mm':max(r.DisplacementLengths),'import':'Official FRD parser, mechanical filler, displacement/von Mises helpers; no VTK pipeline or intermediate recompute.'}))
"""%inp)
 phase('fem_import_results',import_results)
 assert F.get('solver_import'),'Result import failed'
 (OUT/'fem.json').write_text(json.dumps(F,indent=2))
