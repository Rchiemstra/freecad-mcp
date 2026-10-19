import sys,time,json,os,statistics,traceback,subprocess,re,uuid,textwrap
from pathlib import Path
sys.path[:0]=['/demo/scripts/demo']
os.environ['FREECAD_MCP_TELEMETRY_DIR']='/demo/demo-out/stage2/telemetry'
import stdio_client
stdio_client.ROOT=Path('/mcpfix')
Base=stdio_client.Client
OUT=Path('/demo/demo-out')/os.environ.get('DEMO_STAGE','stage2');OUT.mkdir(exist_ok=True);RT=OUT/'runtime';RT.mkdir(exist_ok=True)
if not (RT/'profile').exists():(RT/'profile').symlink_to('/demo/demo-out/'+os.environ.get('DEMO_STAGE','stage2')+'-profile')
class Client(Base):
 def __init__(self,*a,**kw):super().__init__(RT,timeout=900)
stdio_client.Client=Client
import strawberry_driver as d
_doc_file=OUT/'document-name.json'
MODEL_DOC=json.loads(_doc_file.read_text())['document_name'] if _doc_file.exists() else 'strawberry_head_v2'
d.DOC=MODEL_DOC
d.OUT=OUT;d.CALLS=OUT/'calls.json';d.events=json.loads(d.CALLS.read_text()) if d.CALLS.exists() else []
PHASE='setup';original=d.call
CODE_RECEIPTS={}
def journal(event):
 event={**event,'phase':PHASE,'wall_end':time.time()}
 with (OUT/'calls.jsonl').open('a') as f:f.write(json.dumps(event)+'\n')
def raw(tool,**args):
 if tool=='execute_code' and 'BaselineYellow_' in args.get('code',''):
  args['allow_gui_geometry_loop']=True  # exactly three archival commons that create evidence objects
 original(tool,False,**args)
 event=d.events[-1];journal(event)
 return event['result']
def wait_ready():
 for tick in range(1800):
  r=raw('get_mutation_readiness')
  if r['ok'] and r['data'].get('ready'):return r['data']
  docs=(r.get('data') or {}).get('documents',[])
  # A completed commit can leave fresh recompute work. This is a new
  # idempotent recompute after all writes/notifications settled, never a
  # resend of the spreadsheet or geometry mutation that caused it.
  if tick%3==2 and docs and not (r.get('data') or {}).get('automation_pause',{}).get('active_write_count'):
   for doc in docs:
    if doc.get('must_execute') and not any(doc.get(k) for k in ['pending_transaction','recomputing','commit_barrier','notification_replay','active_write_count']):
     done=raw('recompute_document',doc_name=doc['document'])
     if not done['ok']:raise RuntimeError('Follow-up recompute did not confirm completion: '+str(done)[:1500])
  time.sleep(2)
 raise TimeoutError('Native readiness did not settle in one hour')
def call(tool,required=True,**args):
 global PHASE
 if tool in {'spreadsheet_create','spreadsheet_set_cells','spreadsheet_get_cells'} and args.get('sheet_name')=='Mass':args['sheet_name']='V2Mass'
 if tool=='spreadsheet_create' and args.get('sheet_name')=='V2Mass':
  existing=raw('spreadsheet_get_cells',sheet_name='V2Mass',addresses=['A1','B15'])
  if existing['ok']:return {'sheet':'V2Mass','reused_existing':True,'readback':existing['data']}
 if tool=='save_document_as' and args.get('destination')=='/demo/demo-out/strawberry-head.FCStd':args['destination']='/demo/demo-out/strawberry-head-v2.FCStd'
 result=raw(tool,**args)
 if result['ok']:return result['data']
 message=result['text'];data=result.get('data') or {}
 # Structured replies: completion_uncertain, outcome=uncertain or a *_UNCERTAIN code.
 uncertain=('outcome is uncertain' in message.lower() or bool(data.get('completion_uncertain'))
  or data.get('outcome')=='uncertain' or str(data.get('error_code') or '').endswith('_UNCERTAIN'))
 if uncertain and tool in {'execute_code','spreadsheet_set_cells'}:
  workload_phase=PHASE;PHASE='settle_inline_'+workload_phase
  request_id=result['data'].get('request_id')
  if request_id:raw('get_request_status',request_id=request_id)
  ready=wait_ready()
  status=raw('get_request_status',request_id=request_id) if request_id else None
  recovery={'tool':tool,'phase':workload_phase,'request_id':request_id,'readiness':ready,'status':status,'verified':False}
  if tool=='execute_code':
   receipt=CODE_RECEIPTS.get(args['code'])
   if receipt and receipt.exists():
    saved=json.loads(receipt.read_text())
    doc=next((z for z in ready.get('documents',[]) if z.get('document')==args.get('document',d.DOC)),{})
    committed=saved.get('body_returned') and doc.get('undo_count',0)>saved.get('undo_before',10**9)
    added=set(saved.get('object_names_after',[]))-set(saved.get('object_names_before',[]))
    if saved.get('body_returned') and not committed and added:
     names_reply=raw('execute_code',code="import FreeCAD as App,json\nprint(json.dumps([o.Name for o in App.getDocument("+repr(args.get('document',d.DOC))+").Objects]))",document=args.get('document',d.DOC),recompute='none',execution_mode='gui')
     live_names=d.output_json(names_reply['data']) if names_reply['ok'] else []
     committed=bool(live_names) and added.issubset(set(live_names))
     recovery['created_object_readback']={'names':sorted(added),'verified':committed}
    if committed:
     recovered={'stdout':saved['stdout'],'recovered_committed_body':True,'request_id':request_id}
     recovery.update(verified=True,receipt=str(receipt),undo_after=doc['undo_count'])
  else:
   check=raw('spreadsheet_get_cells',sheet_name=args['sheet_name'],addresses=[c['address'] for c in args['cells']])
   actual={c.get('address'):c for c in check['data'].get('cells',[])}
   mismatches=[]
   for c in args['cells']:
    got=actual.get(c['address'],{})
    value=str(got.get('contents',got.get('value',''))).removeprefix("'")
    expected=str(c['value']).removeprefix("'")
    same=re.sub(r'\s+','',value)==re.sub(r'\s+','',expected) if expected.startswith('=') else value==expected
    if not same and not expected.startswith('='):
     try:same=__import__('math').isclose(float(got.get('value')),float(expected),rel_tol=1e-12,abs_tol=1e-12)
     except (ValueError,TypeError):pass
    if not same or ('alias' in c and got.get('alias')!=c['alias']):mismatches.append({'expected':c,'actual':got})
   if check['ok'] and not mismatches:
    recovered={'recovered_committed_cells':True,'request_id':request_id}
    recovery['verified']=True
   recovery['cell_readback']=check;recovery['mismatches']=mismatches
  with (OUT/'recoveries.jsonl').open('a') as f:f.write(json.dumps(recovery)+'\n')
  PHASE=workload_phase
  if recovery['verified']:return recovered
  if required:raise RuntimeError('Uncertain call settled but commit readback was not verified: '+str(recovery)[:1500])
 elif uncertain and tool in {'common_volume_along_path','measure_distance','measure_volume','center_of_mass','validate_geometry'}:
  wait_ready()
  result=raw(tool,**args)
  if result['ok']:return result['data']
 elif not uncertain and ('new GUI work is rejected' in message or (data.get('error_code')=='MUTATION_NOT_READY' and 'Mutation refused' in message) or (data.get('error_code')=='DOCUMENT_NOT_READY' and data.get('committed') is False and data.get('retry_safe') is True)):
  # The dispatcher explicitly refused this new request before execution.
  workload_phase=PHASE;PHASE='settle_rejected_'+workload_phase;wait_ready();PHASE=workload_phase
  result=raw(tool,**args)
  if result['ok']:return result['data']
 elif not uncertain and (data.get('outcome')=='rejected' and data.get('committed') is False and data.get('retry_safe') is True and data.get('native_status')=='Conflict'):
  # An explicit admission conflict guarantees apply did not execute. This is
  # distinct from an uncertain completion and may be retried after settling.
  for attempt in range(3):
   settled=False
   for tick in range(100):
    ready=raw('get_mutation_readiness',**({'doc_name':args['doc_name']} if args.get('doc_name') else {}))
    state=ready.get('data') or {};docs=state.get('documents',[])
    if ready.get('ok') and docs and not state.get('automation_pause',{}).get('active_write_count') and all(not v.get('pending_transaction') and not v.get('commit_barrier') and not v.get('notification_replay') and not v.get('active_write_count') for v in docs):
     settled=True;break
    time.sleep(.2)
   if not settled:break
   time.sleep(.5)
   retried=raw(tool,**args)
   with (OUT/'recoveries.jsonl').open('a') as f:f.write(json.dumps({'tool':tool,'reason':'confirmed_not_committed_admission_conflict','attempt':attempt+1,'result':retried})+'\n')
   if retried['ok']:return retried['data']
   result=retried;data=result.get('data') or {}
   re_uncertain=bool(data.get('completion_uncertain')) or data.get('outcome')=='uncertain' or str(data.get('error_code') or '').endswith('_UNCERTAIN') or 'outcome is uncertain' in result.get('text','').lower()
   if re_uncertain:break
   if not (data.get('outcome')=='rejected' and data.get('committed') is False and data.get('retry_safe') is True and data.get('native_status')=='Conflict'):break
 if required:raise RuntimeError(str(result)[:2000])
 return result['data']
d.call=call
origcode=d.code
def code(body,required=True):
 body=body.replace('StrawberryHead',MODEL_DOC)
 # Validation proxies have identity parent placement and embed their source's
 # full world placement in a one-child compound. Zero path samples are then
 # truly the current pose for rotating members as well as the whole head.
 body=body.replace('target.Shape=shape;cache[target.Name]=sig','target.Shape=Part.makeCompound([shape]);cache[target.Name]=sig+"_world_baked"')
 body=body.replace('cache.get(target.Name)==sig:continue','cache.get(target.Name)==sig+"_world_baked":continue')
 if body==(d.ROOT/'scripts/demo/design_presentation.py').read_text():return {'skipped':'cadence workaround excluded'}
 body=body.replace('/demo/demo-out/design-ui-ack.json',str(OUT/'design-ui-ack.json'))
 receipt=OUT/'native-output'/str(uuid.uuid4());receipt.parent.mkdir(exist_ok=True)
 prefix="""import io as _ab_io,sys as _ab_sys,json as _ab_json
from pathlib import Path as _ab_Path
_ab_doc=__import__('FreeCAD').getDocument(%r)
_ab_before=_ab_doc.UndoCount
_ab_names_before=[o.Name for o in _ab_doc.Objects]
_ab_stdout_original=_ab_sys.stdout
_ab_stdout_buffer=_ab_io.StringIO()
class _AbStdoutTee:
 def write(self,s):
  _ab_stdout_buffer.write(s)
  return _ab_stdout_original.write(s)
 def flush(self):return _ab_stdout_original.flush()
_ab_sys.stdout=_AbStdoutTee()
_ab_body_returned=False
try:
"""%d.DOC
 suffix="""\n _ab_body_returned=True
finally:
 _ab_sys.stdout=_ab_stdout_original
 _ab_Path(%r).write_text(_ab_json.dumps({'body_returned':_ab_body_returned,'undo_before':_ab_before,'stdout':_ab_stdout_buffer.getvalue(),'object_names_before':_ab_names_before,'object_names_after':[o.Name for o in _ab_doc.Objects]}))
"""%str(receipt)
 wrapped=prefix+textwrap.indent(body,' ')+suffix
 CODE_RECEIPTS[wrapped]=receipt
 return origcode(wrapped,required)
d.code=code;d.capture=lambda *a,**kw:None

def counts():
 p=OUT/'freecad.log';raw=p.read_bytes() if p.exists() else b''
 return {'bytes':len(raw),'view_update':raw.count(b'ViewProvider update time'),'shape_mesh':raw.count(b'Shape mesh info'),'show_plane':len(re.findall(rb'\.ViewObject\.ShowPlane changed',raw))}
phases=json.loads((OUT/'phases.json').read_text()) if (OUT/'phases.json').exists() else []
def phase(name,fn):
 global PHASE
 PHASE=name;t=time.perf_counter();before=counts();n=len(d.events);error=None
 print('PHASE START',name,flush=True)
 try:fn()
 except Exception:error=traceback.format_exc();print(error,flush=True)
 after=counts();ev=d.events[n:];lat=[x['seconds'] for x in ev];work=[x['seconds'] for x in ev if x['tool'] not in {'get_mutation_readiness','get_request_status'}]
 entry={'phase':name,'wall_seconds':time.perf_counter()-t,'log_delta':{k:after[k]-before[k] for k in before},'log_before':before,'log_after':after,'rpc_count':len(ev),'rpc_p50':statistics.median(lat) if lat else None,'rpc_max':max(lat) if lat else None,'work_rpc_count':len(work),'work_rpc_p50':statistics.median(work) if work else None,'work_rpc_max':max(work) if work else None,'uncertain_outcomes':sum('outcome is uncertain' in x['result']['text'] for x in ev),'rpc_minus32000':sum('RPC error -32000' in x['result']['text'] for x in ev),'error':error}
 phases.append(entry);(OUT/'phases.json').write_text(json.dumps(phases,indent=2));print('PHASE END',json.dumps(entry),flush=True)
 return error is None

def live(name):subprocess.run(['import','-window','root',str(OUT/name)],check=True,env={**os.environ,'DISPLAY':':99'})

def frame():
 body="""import FreeCAD as App,FreeCADGui as Gui
from PySide import QtCore,QtWidgets
from pathlib import Path
class _ABFrame(QtCore.QObject):
 @QtCore.Slot()
 def start(self):QtCore.QTimer.singleShot(500,self.apply)
 @QtCore.Slot()
 def apply(self):
  d=App.getDocument('StrawberryHead')
  if not d.getMutationReadiness().get('ready'):QtCore.QTimer.singleShot(100,self.apply);return
  v=Gui.activeDocument().activeView();v.viewAxonometric();v.fitAll();v.redraw()
  Path('/demo/demo-out/stage2/frame-ready').write_text('ready')
_ab_frame=_ABFrame();_ab_frame.moveToThread(QtWidgets.QApplication.instance().thread())
QtCore.QMetaObject.invokeMethod(_ab_frame,'start',QtCore.Qt.QueuedConnection)
print('Queued camera framing without image rendering or timer cadence changes')
"""
 p=OUT/'frame-ready'
 if p.exists():p.unlink()
 d.code(body)
 for _ in range(600):
  if p.exists():return
  time.sleep(.1)
 raise TimeoutError('camera frame')
