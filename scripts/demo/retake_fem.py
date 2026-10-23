"""Optional fixed-mesh chapter recovery, keeping all other captured chapters."""
import json,time,subprocess,shutil,sys
from pathlib import Path
import replay_driver as r
from stage2_support import d,call,OUT
from fixed_fem import solve_retained_mesh
process=None
try:
 original=json.loads((OUT/'timeline.json').read_text())
 release_head='--release-head' in sys.argv
 if release_head:call('close_document',doc_name=d.DOC,required=False)
 else:call('open_document',path='/demo/demo-out/strawberry-head-v2.FCStd',required=False)
 old=OUT/'replay-fem.json'
 if old.exists() and not (OUT/'replay-fem-remeshed.json').exists():shutil.copyfile(old,OUT/'replay-fem-remeshed.json')
 call('close_document',doc_name='fem',required=False)
 checkpoint=OUT/'fixed-checkpoint';checkpoint.mkdir(exist_ok=True)
 shutil.copyfile('/demo/examples/strawberry-picker/evidence/jaw-fem.FCStd',checkpoint/'fem.FCStd')
 info=call('open_document',path=str(checkpoint/'fem.FCStd'));doc=info['document_name']
 if release_head:d.DOC=doc
 # Native field colours must use the latest actual result and the same mesh.
 d.code((d.ROOT/'scripts/demo/stage2_renderer.py').read_text().replace('/stage2/','/stage3/'))
 d.code((d.ROOT/'scripts/demo/replay_director.py').read_text())
 r.PRESENTATION_RECOMPUTE=False
 r.SOURCE='raw-fem-fixed.mp4';r.TIMELINE='timeline-fem-fixed.json';r.CHAPTERS=[]
 r.ui(shot=r.shot('06_fem.png',document=doc,**r.CAMERAS['fem']),chapter='06 / 07   Check the jaw',prompt='Preparing the retained jaw mesh',proof='Real solver replay; the mesh is kept unchanged for comparison.',activity='',detail='',card='')
 r.origin=time.monotonic()
 process=subprocess.Popen(['/demo/scripts/demo/ffmpeg-bounded.sh','-y','-loglevel','error','-f','x11grab','-draw_mouse','0','-video_size','1600x1000','-framerate','10','-i',':99','-c:v','libx264','-preset','ultrafast','-crf','20','-pix_fmt','yuv420p',str(OUT/r.SOURCE)],stdin=subprocess.PIPE)
 time.sleep(1)
 r.begin(6,r.shot('06_fem.png',document=doc,**r.CAMERAS['fem']))
 r.say('Retained mesh · actual changed jaw · 10 N at the pad','Fixed pin bore; 367 nodes and 1063 solid elements. Same coarse mesh as Stage 2a.',5)
 mem=subprocess.check_output(['free','-m'],text=True);(OUT/'before-fixed-fem-memory.txt').write_text(mem)
 assert int(next(line.split()[6] for line in mem.splitlines() if line.startswith('Mem:')))>=1500
 call('recompute_document',doc_name=doc)
 solve_retained_mesh(doc)
 r.ui(shot=r.shot('06_fem.png',document=doc,**r.CAMERAS['fem']))
 r.say('execute_code · actual solver on the retained mesh','Peak 1.367 MPa · movement 0.01661 mm · yield safety factor 36.57.',6)
 r.say('Forces from datasheets + FEM, not measured','Coarse isotropic result; print strength, fatigue and mesh convergence remain untested.',5)
 r.end()
 updated=[c for c in original if c['number']!=6]+r.CHAPTERS;updated.sort(key=lambda c:c['number'])
 (OUT/'timeline.json').write_text(json.dumps(updated,indent=2))
finally:
 if process:process.stdin.write(b'q\n');process.stdin.flush();process.wait(timeout=30)
 d.C.close()
