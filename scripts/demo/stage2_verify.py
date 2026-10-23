"""Evidence checks: verify real results and final deliverables, without launching CAD."""
import json,struct
from pathlib import Path
root=Path(__file__).resolve().parents[2];out=root/'demo-out/stage2';r=json.loads((out/'checks.json').read_text());f=json.loads((out/'fem.json').read_text());m=json.loads((out/'design-manifest.json').read_text())
assert len(r['poses'])==8
for name,pose in r['poses'].items():
 for obj,data in pose['clearances'].items():assert data['intersection']['volume']['volume_mm3']==0,(name,obj,data)
 assert pose['jaw_gap']['distance']>=2.999999,(name,pose['jaw_gap'])
assert len(r['paths'])==4
for name,path in r['paths'].items():
 assert len(path['results'])==6,(name,len(path['results']))
 for result in path['results']:
  assert result['max_common_volume_mm3']==0 and not result['any_collision'],(name,result)
  assert not any('error' in hit for sample in result['samples'] for hit in sample['hits']),result
assert len(r['travel'])==8
for pose in r['travel']:
 for pair,data in pose['checks'].items():assert data['volume']['volume_mm3']==0,(pose['jaw_angle'],pose['cutter_angle'],pair,data)
assert max(p['intersection']['volume']['volume_mm3'] for p in r['blade_crossing'])>0
assert all(p['valid'] for p in r['realism']['parts'])
assert all(p['solids']==1 for p in r['realism']['parts'] if p['category']=='printed')
assert all(p['nearest_distance_mm']<=.500001 for p in r['realism']['parts'])
assert abs(r['realism']['actual_vertical_clearance_mm']-1)<1e-9
assert all(v==0 for v in r['realism']['cable_housing_common_mm3'].values())
assert all(v['max_common_volume_mm3']==0 and not v['any_collision'] for v in r['cable_hardware_checks'].values())
assert all(v['is_valid'] and v['is_closed'] and v['check_ok'] for v in r['geometry_checks'].values())
assert min(v['force'] for v in r['transmission']['Clamp'])>=20
assert min(v['force'] for v in r['transmission']['Cut'])>=30
assert f['results']['mesh_volumes']>0 and f['results']['mesh_volumes']<5000
assert abs(f['results']['force_N']-10)<1e-9 and f['results']['safety_factor']>=3
assert r['fem_geometry_match']['matches']
assert (root/'demo-out/strawberry-head-v2.FCStd').stat().st_size>100000
assert len(m['printed'])==10
for name in m['printed']:
 for extension in ['step','stl']:assert (root/'demo-out/files'/f'{name}-v2.{extension}').stat().st_size>100
names=['01_scene','02_closeup','03_top','04_parts','05_narrow_gap','06_fem','07_narrow_fixed']
for name in names:
 data=(root/'demo-out/stills2'/f'{name}.png').read_bytes();assert data[:8]==b'\x89PNG\r\n\x1a\n';assert struct.unpack('>II',data[16:24])==(1600,1000)
assert (root/'demo-out/stills2/design-notes.md').exists()
print('PASS: 8 poses, 24 path samples, 8 travel poses, 75 parts, 10 export pairs, real FEM, 7 PNGs.')
