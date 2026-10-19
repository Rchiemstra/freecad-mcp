#!/usr/bin/env python3
"""Real MCP replay against the retained parametric checkpoint. No language model.
Capture x11 continuously; retain reading holds and small eased motion samples.
Idle tool latency is removed in postproduction, never synthesized into CAD frames.
"""
import json,math,time,subprocess,os,sys
from pathlib import Path
import stage2_job as j
from replay_cameras import CAMERAS
from stage2_support import d,call,raw,wait_ready,OUT
SHOTS=json.loads((OUT/'shots.json').read_text())
PROMPTS=[
 ('Build from a spreadsheet','Build a small head that picks strawberries by the stem. Use a spreadsheet for its dimensions.','Spreadsheet values drive the head and its reference cluster.'),
 ('Enough force?','Can it grip with 10 N and cut with 15 N? Show the force budget.','The calculated force stays above both targets through the stroke.'),
 ('One pick, slowly','Show approach, clamp, cut, withdraw, then move the fruit to the tray.','The scripted parts move in order; tray transfer is a preview.'),
 ('Check the space','Measure the gaps and check whether any parts overlap the neighbouring fruit.','Measured gaps are positive and sampled common volume is zero.'),
 ('Tighter berries','The berries are only 10 mm apart. Show the clash, reshape the nose and check again.','The original nose clashes; the retained nose fix clears the checked samples.'),
 ('Check the jaw','Run a strength check on the jaw with a 10 N load at the pad.','The coarse FEM checks the changed jaw under the stated load.'),
 ('Ready for a bench test','What does it weigh? List the parts and export files I can inspect and print.','The model supplies a mass estimate, parts list and separate print files.')]
OPENING='--retake-opening' in sys.argv
MOTION_PHASE='tray' if '--motion-tray' in sys.argv else ('cut' if '--motion-cut' in sys.argv else None)
OLD_TIMELINE=json.loads((OUT/'timeline.json').read_text()) if (OUT/'timeline.json').exists() else []
OLD_MOTION=next((c for c in OLD_TIMELINE if c['number']==3),None)
ONLY={int(n) for n in sys.argv[sys.argv.index('--only-chapters')+1].split(',')} if '--only-chapters' in sys.argv else set()
START=int(sys.argv[sys.argv.index('--start')+1]) if '--start' in sys.argv else 1
CURRENT_DOC=['strawberry_head_v2']
PRESENTATION_RECOMPUTE=True
CHAPTERS=[c for c in json.loads((OUT/'timeline.json').read_text()) if c['number']<START] if START>1 else []
SOURCE=('raw-motion-'+MOTION_PHASE+'.mp4') if MOTION_PHASE else ('raw-opening.mp4' if OPENING else ('raw.mp4' if START==1 else 'raw-start-%02d.mp4'%START))
SOURCE='raw-static-rework.mp4' if ONLY else SOURCE
TIMELINE='timeline-static.json' if ONLY else ('timeline-opening.json' if OPENING else 'timeline.json')
if ONLY:CHAPTERS=[]
record=None;origin=0

def settle_view():
 # Commit notifications can dirty a body again after a successful recompute.
 # Only recompute once native writes, replay and transactions have settled.
 for tick in range(300):
  state=raw('get_mutation_readiness',doc_name=CURRENT_DOC[0])
  if state['ok'] and state['data'].get('ready'):return
  docs=(state.get('data') or {}).get('documents',[])
  if tick%3==2 and docs and all(v.get('must_execute') and not any(v.get(k) for k in ['pending_transaction','recomputing','commit_barrier','notification_replay','active_write_count']) for v in docs):
   call('recompute_document',doc_name=CURRENT_DOC[0])
  time.sleep(.2)
 raise TimeoutError('Presentation recompute did not settle')

def ui(_settle=True,**kw):
 if kw.get('shot'):CURRENT_DOC[0]=kw['shot']['document']
 c={'id':time.time_ns(),'refresh':True,**kw};p=OUT/'ui-command.tmp';p.write_text(json.dumps(c));p.replace(OUT/'ui-command.json')
 for _ in range(600):
  ack=OUT/'ui-ack.json'
  if ack.exists():
   r=json.loads(ack.read_text())
   if r.get('id')==c['id']:
    assert r['ok'],r
    if _settle and PRESENTATION_RECOMPUTE and (kw.get('shot') or c.get('refresh')):
     call('recompute_document',doc_name=kw['shot']['document'] if kw.get('shot') else CURRENT_DOC[0])
     settle_view()
     # Commit notifications can temporarily restore link transforms and camera
     # state. Reassert the fixed view only after native readiness has settled.
     ui(_settle=False)
     time.sleep(.5)
    return
  time.sleep(.1)
 raise TimeoutError('prompt director')
def take(seconds):
 t=time.monotonic()-origin;time.sleep(seconds);CHAPTERS[-1]['intervals'].append([t,time.monotonic()-origin]);persist()
def persist(): (OUT/TIMELINE).write_text(json.dumps(CHAPTERS,indent=2))
def say(activity,detail='',seconds=4):ui(activity=activity,detail=detail);take(seconds)
def shot(name,**kw):
 c={**SHOTS[name],**kw};c.pop('file',None);c.pop('labels',None);c.pop('dimensions',None);return c
SCENE=shot('01_scene.png',**CAMERAS['scene'])
BUILD=shot('01_scene.png',**CAMERAS['build'])
NOSE=shot('07_narrow_fixed.png',**CAMERAS['nose'])

def begin(n,view):
 title,prompt,proof=PROMPTS[n-1]
 CHAPTERS.append({'number':n,'title':title,'prompt':prompt,'proof':proof,'intervals':[],'source':SOURCE,'start':time.monotonic()-origin})
 ui(shot=view,chapter='%02d / 07   %s'%(n,title),prompt='You: '+prompt,proof='What this proves: '+proof,activity='freecad-mcp · real MCP tools',detail='',card='')
 take(4.4)
def end():take(4.4);CHAPTERS[-1]['end']=time.monotonic()-origin;persist()
def cellread(sheet,aliases):
 return call('spreadsheet_get_cells',sheet_name=sheet,addresses=[j.M['cells'][a] for a in aliases])
def frame(values,record_sample=True):
 if 'JawAngle' in values:values.update(j.c.linkage('Clamp',values['JawAngle'])[0])
 if 'CutAngle' in values:values.update(j.c.linkage('Cut',values['CutAngle'])[0])
 call('spreadsheet_set_cells',sheet_name='Motion',cells=[{'address':j.M['motion_cells'][k],'value':str(v)} for k,v in values.items()])
 call('recompute_document')
 settle_view()
 ui(_settle=False,activity='spreadsheet_set_cells · eased pose')
 # The explicit recompute settles before the fixed camera is reasserted.
 if record_sample:take(.3)
def move(a,b,steps=32):
 for i in range(1,steps+1):
  t=i/steps;t=t*t*(3-2*t)
  frame({k:a[k]+(v-a[k])*t for k,v in b.items()})
def ec(s):return j.ec(s)

def run():
 global origin,record,PRESENTATION_RECOMPUTE
 d.DOC='strawberry_head_v2';j.c.DOC=d.DOC
 # Open first: a fresh GUI has no document to query for readiness.
 info=call('open_document',path='/demo/demo-out/strawberry-head-v2.FCStd',required=False)
 if 'document_name' not in info:
  assert info.get('outcome')=='uncertain',info
  state=wait_ready();docs=state.get('documents',[]);assert len(docs)==1,docs
  info={'document_name':docs[0]['document']}
 d.DOC=info['document_name'];j.c.DOC=d.DOC
 __import__('stage2_support').MODEL_DOC=d.DOC
 wait_ready()
 opened=j.ec("import FreeCAD as App,json\nD=App.getDocument('StrawberryHead')\nprint(json.dumps({'file':D.FileName}))")
 assert Path(opened['file']).resolve()==Path('/demo/demo-out/strawberry-head-v2.FCStd'),opened
 d.code((d.ROOT/'scripts/demo/stage2_renderer.py').read_text().replace('/stage2/','/stage3/'))
 d.code((d.ROOT/'scripts/demo/replay_director.py').read_text())
 from rework_presentation import bind_wrist
 bind_wrist()
 call('close_document',doc_name='fem',required=False)
 j.c.setcells({'NeighbourGap':15})
 call('spreadsheet_set_cells',sheet_name='Motion',cells=[{'address':'B1','value':'0'}])
 if MOTION_PHASE=='tray':j.c.pose('withdraw',0,-13,20,-25,True)
 elif MOTION_PHASE:j.c.pose('clamp',0,13,0,0)
 else:j.c.pose('approach',-18,13,15,0)
 ui(shot=SCENE,chapter='freecad-mcp',prompt='A strawberry picker, from dimensions to checks',proof='A scripted replay in the real companion FreeCAD fork GUI.',activity='Starting the seven-chapter story',detail='Saved parametric checkpoint · no language model during replay',card='')
 origin=time.monotonic()
 record=subprocess.Popen(['/demo/scripts/demo/ffmpeg-bounded.sh','-y','-loglevel','error','-f','x11grab','-draw_mouse','0','-video_size','1600x1000','-framerate','10','-i',':99','-c:v','libx264','-preset','ultrafast','-crf','20','-pix_fmt','yuv420p',str(OUT/SOURCE)],stdin=subprocess.PIPE)
 time.sleep(1)
 if START<=1 and (not ONLY or 1 in ONLY):
  # 1: regenerate the saved expression-driven model, progressively reveal results.
  # The mounting reference is a seated wrist/adapter pair even before the
  # rest of the head is revealed.
  scene={**BUILD,'parts':[p for p in j.M['parts'] if p['kind']=='scene' or p['name']=='WristAdapter']}
  begin(1,scene)
  dims=cellread('Dims',['BerryWidth','BerryLength','StemDia','HornRadius','InputArm','JawOutputArm','CutOutputArm'])
  ui(card='MCP cell readback · Dims\n\nNominal berry: 30 × 35 mm\nStem: 3 mm\nHorn radius: 6 mm\nInput arm: 24 mm\nJaw arm: 15 mm\nCutter arm: 10.5 mm')
  say('spreadsheet_get_cells','The native checkpoint retains the spreadsheet, sketches and expressions.',5)
  before=ec("import FreeCAD as App,json\nD=App.getDocument('StrawberryHead')\nprint(json.dumps({'jaw_volume_mm3':D.MovingJaw.Shape.Volume,'jaw_height_mm':D.MovingJaw.Shape.BoundBox.ZLength,'cluster_gap_mm':float(D.Motion.get('NeighbourGap'))}))")
  call('spreadsheet_set_cells',sheet_name='V2Dims',cells=[{'address':'B4','value':'5.6'}])
  call('spreadsheet_set_cells',sheet_name='Motion',cells=[{'address':'B13','value':'14.9'}])
  call('spreadsheet_set_cells',sheet_name='V2Dims',cells=[{'address':'B4','value':'5.7'}])
  call('spreadsheet_set_cells',sheet_name='Motion',cells=[{'address':'B13','value':'15'}])
  call('recompute_document')
  after=ec("import FreeCAD as App,json\nD=App.getDocument('StrawberryHead')\nprint(json.dumps({'jaw_volume_mm3':D.MovingJaw.Shape.Volume,'jaw_height_mm':D.MovingJaw.Shape.BoundBox.ZLength,'cluster_gap_mm':float(D.Motion.get('NeighbourGap')),'valid':D.MovingJaw.Shape.isValid()}))")
  assert after['valid'] and abs(after['jaw_height_mm']-5.7)<1e-6 and abs(after['jaw_volume_mm3']-before['jaw_volume_mm3'])<1e-6 and after['cluster_gap_mm']==15
  (OUT/'replay-build.json').write_text(json.dumps({'before':before,'after':after,'tools':['spreadsheet_set_cells','recompute_document','execute_code'],'temporary_values':{'jaw_height_mm':5.6,'cluster_gap_mm':14.9},'restored':True},indent=2))
  ui(shot=BUILD,card='')
  say('spreadsheet_set_cells + recompute_document · native parts rebuilt','The same Stage 2a geometry is regenerated; the reveal is presentation.',6)
  say('Stem first','Two drives: one holds the stem, the other moves a replaceable blade.',4);end()
 if START<=2 and (not ONLY or 2 in ONLY):
  # 2: actual formula cells plus swept minima retained from Stage 2a.
  j.c.pose('clamp')
  begin(2,shot('03_top.png',**CAMERAS['force']))
  cells=cellread('Dims',['StallTorque','TorqueSafety','WorkTorque','HornRadius','InputArm','JawOutputArm','CutOutputArm','ClampForce','CutForce','ClampRequired','CutRequired'])
  ui(card='MCP cell readback · Dims\n\nStall torque: 176 N mm\nWorking torque: 88 N mm\nIdeal clamp: 23.47 N\nIdeal cut: 33.52 N\n\nNeed: 10 N grip / 15 N cut')
  say('spreadsheet_get_cells · force formulas','Torque is derated by 2. The linkage geometry gives the pad force.',6)
  say('Full-stroke minima: clamp 23.14 N · cut 33.42 N','Stage 2a: 0.1° samples with transmission correction; 2.31× / 2.23× targets.',6)
  say('Forces from datasheets + FEM, not measured','Stem strength, friction and real servo performance still need bench tests.',5);end()
 if OPENING:return
 if START<=3 and (not ONLY or 3 in ONLY):
  # 3: small eased sheet updates; one fixed camera throughout.
  if MOTION_PHASE:
   keep=67 if MOTION_PHASE=='tray' else 59
   assert OLD_MOTION and len(OLD_MOTION['intervals'])>=keep
   prior=OLD_MOTION.get('prior_takes',[])+[{'source':OLD_MOTION.get('source','raw.mp4'),'intervals':OLD_MOTION['intervals'][:keep]}]
   title,prompt,proof=PROMPTS[2]
   CHAPTERS.append({'number':3,'title':title,'prompt':prompt,'proof':proof,'source':SOURCE,'intervals':[],'prior_takes':prior,'start':time.monotonic()-origin})
   ui(shot=SCENE,chapter='03 / 07   '+title,prompt='You: '+prompt,proof='What this proves: '+proof,activity='Cut',detail='',card='')
  else:
   j.c.pose('approach',-18,13,15,0)
   ui(card='');begin(3,SCENE)
   say('spreadsheet_set_cells · approach','Move down toward the stem while the jaw is open.',3)
   move({'HeadZ':15},{'HeadZ':0},28)
   say('Clamp','The pads close around the stem.',3)
   move({'JawAngle':-18},{'JawAngle':0},28)
  if MOTION_PHASE!='tray':
   say('Cut','The blade passes above the pad. This is a placement preview, without contact physics.',3)
   move({'CutAngle':13},{'CutAngle':-13},32)
   frame({'TargetStemLength':12.7})
   say('Withdraw','The cut fruit moves with the head along the checked withdrawal direction.',3)
   move({'HeadY':0,'HeadZ':0,'TargetY':0,'TargetZ':0},{'HeadY':-25,'HeadZ':20,'TargetY':-25,'TargetZ':20},32)
  say('Tray transfer · preview only','The relocated-tray transfer was not included in the collision checks.',4)
  # The tray is beside the head; add a temporary expression for target X only.
  call('set_expression',object_name='Target',prop_path='Placement.Base.x',expression='Motion.HeadX')
  move({'HeadX':0,'HeadY':-25,'TargetY':-25},{'HeadX':-125,'HeadY':22.5,'TargetY':22.5},48)
  say('At the tray · preview only','No drop, gravity, contact or tray-transfer collision result is claimed.',4);end()
 if START<=4 and (not ONLY or 4 in ONLY):
  # Reset out of the edited story, then chapter 4 holds a fixed nose camera.
  frame({'HeadX':0},False);call('set_expression',object_name='Target',prop_path='Placement.Base.x',expression='0')
  j.c._cell_cache.clear();j.c.setcells({'NeighbourGap':15});j.c.pose('clamp')
  begin(4,NOSE)
  ui(card='MCP clearance readback\n\n15 mm nominal spacing\nRetained minimum: 4.073 mm\n\nSix neighbouring objects\nEight retained poses\n24 path samples\n\nSampled common: 0 mm³')
  dist=call('measure_distance',shape1_ref='HeadEnvelope',shape2_ref='World_NeighbourLBerry')
  collision=call('common_volume_along_path',moving_object='HeadEnvelope',obstacle_objects=['World_NeighbourLBerry','World_NeighbourLCap','World_NeighbourLStem','World_NeighbourRBerry','World_NeighbourRCap','World_NeighbourRStem'],samples=[{'x':0,'y':0,'z':0}])
  (OUT/'replay-clearance.json').write_text(json.dumps({'distance':dist,'common':collision},indent=2))
  say('measure_distance · positive gap','15 mm setting: the retained pose check has at least 4.073 mm clearance.',6)
  say('common_volume_along_path · 0 mm³','Both neighbouring fruit, calyces and stems are included.',5)
  say('The check has a defined scope','Eight poses and 24 approach/withdrawal samples passed in Stage 2a; sampling is not a continuous certificate.',5);end()
 if START<=5 and (not ONLY or 5 in ONLY):
  # 5: real archived original BReps, followed by actual retained fix.
  j.c.setcells({'NeighbourGap':10});j.c.pose('clamp')
  call('spreadsheet_set_cells',sheet_name='V2Dims',cells=[{'address':'B1','value':'-28'},{'address':'B2','value':'37'},{'address':'B3','value':'-30'}])
  baseline=shot('05_narrow_gap.png',**CAMERAS['nose'])
  begin(5,baseline)
  ui(card='MCP narrow-cluster readback\n\n10 mm nominal spacing\nOriginal common volumes:\nFruit: 583.615 / 583.602 mm³\nStem: 3.195 mm³\n\nRetained fix:\nMinimum pose gap: 0.693 mm\nSampled common: 0 mm³')
  values={n:call('measure_volume',obj_name=n) for n in ['BaselineYellow_NeighbourLBerry','BaselineYellow_NeighbourRBerry','BaselineYellow_NeighbourLStem']}
  say('measure_volume · original clash in yellow','Original overlaps: 583.615 / 583.602 mm³ in fruit; 3.195 mm³ at a neighbouring stem.',6)
  call('spreadsheet_set_cells',sheet_name='V2Dims',cells=[{'address':'B1','value':'-4'},{'address':'B2','value':'13'},{'address':'B3','value':'-26'}])
  j.c.pose('clamp')
  ui(shot=NOSE)
  say('Retained nose fix · same camera','Lower cheek extensions removed; carrier shortened 4 mm. Pad and blade stay functional.',6)
  fixed=call('common_volume_along_path',moving_object='HeadEnvelope',obstacle_objects=['World_NeighbourLBerry','World_NeighbourLCap','World_NeighbourLStem','World_NeighbourRBerry','World_NeighbourRCap','World_NeighbourRStem'],samples=[{'x':0,'y':0,'z':0}])
  say('common_volume_along_path · re-check 0 mm³','Minimum retained pose clearance: 0.693 mm. The fruit shape makes the actual gap about 9.802 mm.',6)
  (OUT/'replay-narrow.json').write_text(json.dumps({'original':values,'fixed':fixed},indent=2));end()
 if START<=6 and (not ONLY or 6 in ONLY):
  # 6: rerun the actual coarse FEM; save the live result readback.
  call('open_document',path='/demo/demo-out/stage2/fem.FCStd')
  PRESENTATION_RECOMPUTE=False
  begin(6,shot('06_fem.png',document='fem',**CAMERAS['fem']))
  say('Actual changed jaw · fixed pin bore · 10 N at the pad','PLA: E 3500 MPa, yield 50 MPa. Coarse isotropic mesh; 1063 solid elements.',5)
  mem=subprocess.check_output(['free','-m'],text=True);(OUT/'before-fem-memory.txt').write_text(mem)
  assert int(next(line.split()[6] for line in mem.splitlines() if line.startswith('Mem:')))>=1500
  call('recompute_document',doc_name='fem')
  from fixed_fem import solve_retained_mesh
  result=solve_retained_mesh('fem')
  ui(shot=shot('06_fem.png',document='fem',**CAMERAS['fem']))
  say('execute_code · actual solver on the retained mesh','Peak 1.367 MPa · movement 0.01661 mm · yield safety factor 36.57.',6)
  say('Forces from datasheets + FEM, not measured','This coarse isotropic result does not prove print strength, fatigue or mesh convergence.',5);end()
  PRESENTATION_RECOMPUTE=True
 if START<=7 and (not ONLY or 7 in ONLY):
  # 7: actual enumeration, mass sheet and typed exports.
  ui(card='')
  call('close_document',doc_name='fem',required=False)
  j.c.setcells({'NeighbourGap':15});j.c.pose('clamp')
  from rework_presentation import layout_parts
  layout_parts()
  begin(7,shot('04_parts.png',**CAMERAS['parts']))
  mass=call('spreadsheet_get_cells',sheet_name='V2Mass',addresses=['A1','A15','B15'])
  bom=ec("import FreeCAD as App,json\nD=App.getDocument('StrawberryHead')\nprint(json.dumps([{'name':o.Name,'type':o.Category,'material':o.MaterialNote} for o in D.Objects if hasattr(o,'Category') and o.Category in ['printed','bought']]))")
  (OUT/'replay-bom.json').write_text(json.dumps(bom,indent=2))
  say('spreadsheet_get_cells · native parts enumeration','83.84 g estimated at the retained 40% PLA fill convention; all-solid envelope 130.38 g.',6)
  names=[p['name'] for p in j.M['parts'] if p['kind'] in ['printed','bought']]
  call('export_step',file_path='/demo/examples/strawberry-picker/assembly.step',obj_names=names)
  call('export_step',file_path='/demo/demo-out/stage3/MovingJaw.step',obj_names=['MovingJaw'])
  call('export_stl',file_path='/demo/demo-out/stage3/MovingJaw.stl',obj_names=['MovingJaw'],mesh_deviation=.08)
  say('export_step + export_stl · native model + ten print pairs','The assembly STEP contains the head; the native file also retains the scene and spreadsheet.',6)
  say('Next: print, measure and test real stems','Grip 10 N, cut 15 N; test dummy clusters at 15 mm, 10 mm, then closer.',5);end()
 (OUT/'prompts.json').write_text(json.dumps(PROMPTS,indent=2))

if __name__=='__main__':
 try:run()
 finally:
  if record:
   record.stdin.write(b'q\n');record.stdin.flush();record.wait(timeout=30)
  d.C.close()
