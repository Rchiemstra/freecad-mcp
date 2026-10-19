#!/usr/bin/env python3
"""Validate delivered artifacts and retained engineering evidence; never start CAD."""
import hashlib,json,re,struct,subprocess,zipfile
from collections import Counter
from fractions import Fraction
from pathlib import Path
import xml.etree.ElementTree as ET
from urllib.parse import unquote
R=Path(__file__).resolve().parents[2];E=R/'examples/strawberry-picker';O=R/'demo-out';S=O/'stage3'
def probe(p):return json.loads(subprocess.check_output(['ffprobe','-v','error','-show_format','-show_streams','-show_chapters','-of','json',str(p)]))
def stl(p):
 data=p.read_bytes();n=struct.unpack_from('<I',data,80)[0];assert len(data)==84+50*n,p
 edges=Counter()
 for i in range(n):
  vs=[tuple(round(x,5) for x in struct.unpack_from('<3f',data,84+i*50+12+k*12)) for k in range(3)]
  for a,b in zip(vs,vs[1:]+vs[:1]):edges[tuple(sorted([a,b]))]+=1
 assert edges and all(n==2 for n in edges.values()),p
 return n
def links(p):
 for raw in re.findall(r'\]\(([^)]+)\)',p.read_text()):
  target=raw.split(' ')[0].strip('<>')
  if re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*:',target) or target.startswith('#'):continue
  target=unquote(target.split('#')[0]);assert (p.parent/target).exists(),(p,target)
for p in [R/'README.md',E/'README.md',R/'scripts/demo/README.md']:links(p)
names=['01_scene','02_closeup','03_top','04_parts','05_narrow_gap','06_fem','07_narrow_fixed']
for n in names:
 data=(O/'stills3'/f'{n}.png').read_bytes();assert data[:8]==b'\x89PNG\r\n\x1a\n';assert struct.unpack('>II',data[16:24])==(1600,1000)
for p in E.rglob('*.FCStd'):
 with zipfile.ZipFile(p) as z:assert z.testzip() is None;assert 'Document.xml' in z.namelist()
assert hashlib.sha256((E/'strawberry-head.FCStd').read_bytes()).digest()==hashlib.sha256((O/'strawberry-head-v2.FCStd').read_bytes()).digest()
with zipfile.ZipFile(E/'strawberry-head.FCStd') as z:root=ET.fromstring(z.read('Document.xml'))
for name in ['RobotWrist','WristPilotBoss']:
 obj=next(o for o in root.findall('.//Object') if o.get('name')==name and o.find('Properties') is not None)
 expr={e.get('path','').lstrip('.'):e.get('expression','') for e in obj.findall('.//Expression')}
 for axis in 'xyz':assert 'Motion.Head'+axis.upper() in expr.get('Placement.Base.'+axis,''),(name,axis,expr)
proof=json.loads((E/'evidence/reference-checkpoint.json').read_text());assert proof['result']=='PASS' and proof['before']==proof['after']
parts=list((E/'parts').glob('*.stl'));assert len(parts)==10
triangles={p.name:stl(p) for p in parts}
for p in [E/'assembly.step',*(E/'parts').glob('*.step')]:
 text=p.read_text();assert 'ISO-10303-21;' in text and 'END-ISO-10303-21;' in text,p
size=sum(p.stat().st_size for p in E.rglob('*') if p.is_file());assert size<=15_000_000,size
checks=json.loads((E/'evidence/stage2-checks.json').read_text());fem=json.loads((E/'evidence/fem.json').read_text())
for p in checks['poses'].values():assert all(v['intersection']['volume']['volume_mm3']==0 for v in p['clearances'].values())
for p in checks['paths'].values():assert len(p['results'])==6 and all(v['max_common_volume_mm3']==0 for v in p['results'])
assert len(checks['poses'])==8 and len(checks['paths'])==4 and len(checks['travel'])==8
assert abs(min(x['force'] for x in checks['transmission']['Clamp'])-23.138)<.001
assert abs(min(x['force'] for x in checks['transmission']['Cut'])-33.417)<.001
assert fem['results']['mesh_volumes']==1063
assert checks['fem_geometry_match']['matches']
live_fem=json.loads((S/'replay-fem.json').read_text());assert live_fem['solver']['return_code']==0
assert (live_fem['result']['nodes'],live_fem['result']['elements'])==(367,1063)
for live,retained in [('stress_MPa','max_von_mises_MPa'),('displacement_mm','max_displacement_mm'),('yield_safety_factor','safety_factor')]:
 assert abs(live_fem['result'][live]-fem['results'][retained])<1e-10
live_clearance=json.loads((S/'replay-clearance.json').read_text())
assert live_clearance['distance']['distance']>0 and live_clearance['common']['max_common_volume_mm3']==0
live_narrow=json.loads((S/'replay-narrow.json').read_text());assert live_narrow['fixed']['max_common_volume_mm3']==0
for name,expected in [('BaselineYellow_NeighbourLBerry',583.615),('BaselineYellow_NeighbourRBerry',583.602),('BaselineYellow_NeighbourLStem',3.195)]:
 assert abs(live_narrow['original'][name]['volume_mm3']-expected)<.001

v=probe(O/'strawberry-picker.mp4');duration=float(v['format']['duration'])
assert 180<=duration<=300,duration;assert len(v['chapters'])==7
assert (v['streams'][0]['width'],v['streams'][0]['height'])==(1600,1000)
assert Fraction(v['streams'][0]['avg_frame_rate'])==10
media=json.loads((S/'media-report.json').read_text());assert len(media['chapters'])==7
for ch in media['chapters']:
 assert ch['start_hold_seconds']-ch['fade_seconds']>=3
 assert ch['end_hold_seconds']-ch['fade_seconds']>=3
 for moment in ['start','one-third','two-thirds','middle','end']:assert (S/'qc'/f'{ch["number"]:02d}-{moment}.png').is_file()
poses=[json.loads(line) for line in (S/'wrist-poses.jsonl').read_text().splitlines()]
assert all(all(abs(a-b)<1e-6 for a,b in zip(p['wrist_mm'],p['head_mm'])) for p in poses)
assert poses and all(p['offset_mm']<1e-6 and p['pilot_error_mm']<1e-6 and abs(p['rotation_error_rad'])<1e-6 for p in poses)
for xyz in [(0,0,15),(0,0,0),(0,-25,20),(-125,22.5,20)]:
 assert any(all(abs(a-b)<1e-6 for a,b in zip(p['head_mm'],xyz)) for p in poses),xyz
assert any(abs(p['jaw_deg']+18)<1e-6 for p in poses)
assert any(abs(p['cut_deg']+13)<1e-6 for p in poses)
review=json.loads((S/'visual-review.json').read_text());assert review['result']=='PASS'
for name in names:
 assert hashlib.sha256((O/'stills3'/f'{name}.png').read_bytes()).hexdigest()==review['stills_sha256'][name+'.png']
for n in range(1,8):
 for moment in ['start','one-third','middle','two-thirds','end']:
  name=f'{n:02d}-{moment}.png';assert hashlib.sha256((S/'qc'/name).read_bytes()).hexdigest()==review['chapter_samples_sha256'][name]
gifs={}
for name,budget in [('strawberry-picker.gif',5_000_000),('strawberry-picker-03-motion.gif',3_000_000),('strawberry-picker-05-clearance.gif',3_000_000),('strawberry-picker-06-fem.gif',3_000_000)]:
 p=R/'assets'/name;q=probe(p);s=q['streams'][0]
 assert s['width']==960 and Fraction(s['avg_frame_rate'])==10,(name,s)
 assert p.stat().st_size<=budget,(name,p.stat().st_size);gifs[name]=p.stat().st_size
 for i in range(3):
  sample=p.stem+'-'+str(i)+'.png';assert hashlib.sha256((S/'qc'/sample).read_bytes()).hexdigest()==review['gif_samples_sha256'][sample]
# The exact stage list deliberately excludes all runtime artifacts and the MP4.
paths=['README.md']+[str(p.relative_to(R)) for p in sorted((R/'assets').glob('strawberry-picker*.gif'))]+[str(p.relative_to(R)) for base in [E,R/'scripts/demo'] for p in sorted(base.rglob('*')) if p.is_file() and '__pycache__' not in p.parts]
assert all(not p.startswith('demo-out/') and not p.endswith('.mp4') for p in paths)
handoff=S/'handoff';handoff.mkdir(exist_ok=True)
(handoff/'strawberry-demo-paths.txt').write_text('\n'.join(paths)+'\n')
Path('/tmp/strawberry-demo-paths.txt').write_text('\n'.join(paths)+'\n')
Path('/tmp/strawberry-demo-commit-msg.txt').write_text('docs: add strawberry picker MCP replay and verified print files\n\nReplace the demo section with a seven-chapter strawberry picker story.\nInclude condensed GIFs, retained Stage 2a geometry, native wrist bindings and print\nexports, per-check evidence, print notes and a practical bench test plan.\nRetain bounded replay scripts and disclose checkpoint regeneration,\nscripted motion, estimated forces and remaining engineering gaps.\nBind the visual wrist reference to every head pose, suppress the cursor,\nfit chapter cameras, shorten still label leaders and review four moments\nper chapter. Regenerate the video and all four bounded previews.\nRestore caption/readback panels in post and disclose that restoration.\n')
(handoff/'strawberry-demo-commit-msg.txt').write_text(Path('/tmp/strawberry-demo-commit-msg.txt').read_text())
report={'result':'PASS','video_seconds':duration,'chapters':7,'example_bytes':size,'gif_bytes':gifs,'stl_triangles':triangles,'stage_paths':len(paths),'review':{'result':review['result'],'video_samples':len(review['chapter_samples_sha256']),'stills':len(review['stills_sha256']),'gif_samples':len(review['gif_samples_sha256'])}}
(S/'delivery-checks.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
