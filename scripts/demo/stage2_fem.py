from stage2_support import *
d.DOC='JawFEM'
F={}
def ec(s):return d.output_json(d.code(s))
def fem_setup():
 call('create_document',name='JawFEM')
 call('create_object',obj_type='Part::Feature',obj_name='MovingJaw')
 F['geometry']=ec("""import FreeCAD as App,json
D=App.getDocument('JawFEM');source=App.getDocument('StrawberryHead').MovingJaw
D.MovingJaw.Shape=source.Shape.copy()
print(json.dumps({'source':'StrawberryHead.MovingJaw','volume_mm3':source.Shape.Volume,'solid_count':len(source.Shape.Solids),'faces':[{'name':'Face'+str(i+1),'type':type(f.Surface).__name__,'center':list(f.CenterOfMass),'area':f.Area,'radius':getattr(f.Surface,'Radius',None),'normal':list(f.normalAt(0,0)) if type(f.Surface).__name__=='Plane' else None} for i,f in enumerate(source.Shape.Faces)]}))
""")
 assert F['geometry']['solid_count']==1,F['geometry']
 call('create_object',obj_type='Fem::AnalysisPython',obj_name='JawAnalysis')
 F['material']=call('create_object',obj_type='Fem::MaterialCommon',obj_name='JawPLA',analysis_name='JawAnalysis',obj_properties={'Material':{'Name':'PLA','YoungsModulus':'3500 MPa','PoissonRatio':'0.36','Density':'1240 kg/m^3','YieldStrength':'50 MPa'}})
 faces=F['geometry']['faces']
 fixed=[f['name'] for f in faces if f['type']=='Cylinder' and abs(f['center'][0])<.01 and abs(f['center'][1])<.01 and abs(f['radius']-1.6)<.1]
 if not fixed:
  bores=[f for f in faces if f['type']=='Cylinder' and abs(f['radius']-1.6)<.1]
  assert bores,'Pin bore not found in real jaw geometry'
  fixed=[min(bores,key=lambda f:f['center'][0]**2+f['center'][1]**2)['name']]
 pad=min((f for f in faces if f['type']=='Plane' and abs(f['normal'][0])>.9),key=lambda f:sum((f['center'][i]-[-5.5,12,3][i])**2 for i in range(3)))
 F['fixed_faces']=fixed;F['pad_face']=pad
 call('create_object',obj_type='Fem::ConstraintFixed',obj_name='PinFixed',analysis_name='JawAnalysis',obj_properties={'References':[{'object_name':'MovingJaw','face':f} for f in fixed]})
 F['load_conversion']=ec("import FreeCAD as App,json\nq=App.Units.Quantity('10 N')\nprint(json.dumps({'internal_value':q.Value,'force_N':float(q.getValueAs('N'))}))")
 assert abs(F['load_conversion']['force_N']-10)<1e-10
 call('create_object',obj_type='Fem::ConstraintForce',obj_name='PadLoad10N',analysis_name='JawAnalysis',obj_properties={'References':[{'object_name':'MovingJaw','face':pad['name']}],'Force':F['load_conversion']['internal_value']})
 F['mesh']=call('create_object',obj_type='Fem::FemMeshGmsh',obj_name='JawCoarseMesh',analysis_name='JawAnalysis',obj_properties={'Shape':'MovingJaw','CharacteristicLengthMax':3,'CharacteristicLengthMin':1.5,'ElementOrder':'1st'})
 (OUT/'fem.json').write_text(json.dumps(F,indent=2))
phase('fem_setup',fem_setup)
if not F.get('mesh'):d.C.close();sys.exit(1)
phase('fem_solver',lambda:F.update(solve=call('run_fem_analysis',analysis_name='JawAnalysis',timeout=180,required=False)))
(OUT/'fem.json').write_text(json.dumps(F,indent=2))
if not F.get('solve',{}).get('success'):
 exec((d.ROOT/'scripts/demo/stage2_fem_phased.py').read_text(),globals())
 run_phased_fem()
def results():
 F['results']=ec("""import FreeCAD as App,json,glob,shutil,os
D=App.getDocument('JawFEM')
rs=[o for o in D.Objects if hasattr(o,'vonMises') and len(o.vonMises)]
assert rs,'No solver result exists'
r=rs[-1];mesh=D.JawCoarseMesh.FemMesh
print(json.dumps({'result_object':r.Name,'node_count':len(r.vonMises),'mesh_nodes':mesh.NodeCount,'mesh_volumes':mesh.VolumeCount,'max_von_mises_MPa':max(r.vonMises),'min_von_mises_MPa':min(r.vonMises),'max_displacement_mm':max(r.DisplacementLengths),'safety_factor':50/max(r.vonMises),'material':D.JawPLA.Material,'force_N':float(D.PadLoad10N.Force.getValueAs('N')),'force_direction':list(D.PadLoad10N.DirectionVector),'mesh_min_mm':float(D.JawCoarseMesh.CharacteristicLengthMin),'mesh_max_mm':float(D.JawCoarseMesh.CharacteristicLengthMax),'addon_files':{name:os.path.realpath(module.__file__) for name,module in list(__import__('sys').modules.items()) if name.endswith(('cad_methods_ops.typed_rpc_document','rpc_server.rpc_server')) and getattr(module,'__file__',None)}}))
for path in glob.glob('/tmp/freecad_mcp_fem_*')+glob.glob('/tmp/fcfem_*')+glob.glob('/tmp/fem_*'):shutil.copytree(path,'/demo/demo-out/stage2/fem_solver/'+os.path.basename(path),dirs_exist_ok=True)
from pathlib import Path
for solver in D.JawAnalysis.Group:
 path=getattr(solver,'WorkingDir',None)
 if path and os.path.isdir(str(path)) and os.path.abspath(str(path)) not in ['/','/demo']:
  dest=Path('/demo/demo-out/stage2/fem_solver')/('actual_'+Path(str(path)).name);dest.mkdir(parents=True,exist_ok=True)
  for pattern in ['*.inp','*.frd','*.dat','*.sta','*.cvg','*.geo','*.msh','*.brep']:
   for file in Path(str(path)).glob(pattern):shutil.copy2(str(file),str(dest/file.name))
""")
 assert F['results'] and F['results']['mesh_volumes']>0
 (OUT/'fem.json').write_text(json.dumps(F,indent=2))
phase('fem_results',results)
if not F.get('results'):d.C.close();sys.exit(1)
phase('fem_save',lambda:call('save_document_as',selector={'document_name':'JawFEM'},destination='/demo/demo-out/stage2/fem.FCStd',overwrite=True))
d.C.close()
