"""Reframe Stage 2a native geometry and add measurement witnesses; no design edits."""
import json,time
from pathlib import Path
import stage2_job as j
from stage2_support import d,call,wait_ready,OUT
original=j.render
only_top='--only-top' in __import__('sys').argv
only_closeup='--only-closeup' in __import__('sys').argv
shots=json.loads((OUT/'shots.json').read_text()) if only_closeup or only_top else {}
def render(file,title,subtitle,parts=None,**kw):
 if file in ('03_top.png','07_narrow_fixed.png'):
  kw['view']=None;kw['orientation']=j.c.view_from([.3,1.5,.72]);kw['height']=190
  kw['center']=[0,-30,3]
 if file=='03_top.png':
  subtitle='Low view of the nose; translucent housing exposes the two drive linkages.'
  for label in kw['labels']:
   if 'clearance' in label['text']:label['point']=[3.5,2.5,6.2];label['textpos']=[620,540];label['leader_start']=[807,550];label['font_size']=15
   if label['text']=='stem':label['textpos']=[860,440];label['leader_start']=[860,440]
   if label['text']=='pad':label['point']=[2.5,4,2];label['textpos']=[680,640];label['leader_start']=[752,615]
   if label['text']=='blade':label['textpos']=[1040,520];label['leader_start']=[1040,520]
 if file=='02_closeup.png':
  kw['labels']=[x for x in kw['labels'] if 'clearance' not in x['text']]
  kw['dimensions']=[{'a':[-2,0,6.7],'b':[2.5,0,5.7],'x':1005,'text':'1.0 mm'}]
 if file=='04_parts.png':
  names=['servo','servo','blade','jaw pin','cut pin','bolt','screw','M2 screw','locknut','M2 screw']
  for i,txt in enumerate(names):
   x=-135+i*30
   kw['labels'].append({'text':txt,'point':[x,-135,0],'textpos':[800+x*1000/330-24,875 if i%2==0 else 900],'font_size':12})
 if kw.get('document')=='JawFEM':kw['document']='fem'
 kw['output_dir']='stills3'
 shots[file]={'file':file,'title':title,'subtitle':subtitle,'document':kw.get('document',d.DOC),'parts':parts if parts is not None else j.M['parts'],**kw}
 (OUT/'shots.json').write_text(json.dumps(shots,indent=2))
 return original(file,title,subtitle,parts,**kw)
j.render=render
j.snapshot=lambda: None
try:
 info={'document_name':'strawberry_head_v2'} if '--resume' in __import__('sys').argv else call('open_document',path='/demo/demo-out/strawberry-head-v2.FCStd')
 d.DOC=info['document_name'];j.c.DOC=d.DOC
 import stage2_support
 stage2_support.MODEL_DOC=d.DOC
 (OUT/'document-name.json').write_text(json.dumps({'document_name':d.DOC}))
 wait_ready()
 None if '--resume' in __import__('sys').argv or only_closeup or only_top else call('open_document',path='/demo/demo-out/stage2/fem.FCStd')
 call('recompute_document',doc_name=d.DOC)
 source=(d.ROOT/'scripts/demo/stage2_renderer.py').read_text().replace('/stage2/','/stage3/').replace("QFont('DejaVu Sans',17)","QFont('DejaVu Sans',label.get('font_size',17))")
 d.code(source)
 if only_top:
  j.top_detail()
 elif only_closeup:
  j.contact_detail_setup();j.contact_detail();j.c.pose('clamp')
 else:
  j.stills();j.parts_retake();j.baseline_retake();j.fem_still()
 # j.stills saves the assembly: write a separate checkpoint, never overwrite Stage 2a.
finally:d.C.close()
