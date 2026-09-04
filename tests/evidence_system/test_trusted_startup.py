from __future__ import annotations
import base64,hashlib,json,os,shutil,subprocess,sys
from datetime import datetime,timedelta,timezone
from pathlib import Path
from freecad_mcp.evidence_system import docker_contract
from freecad_mcp.evidence_system.launcher import run_isolated
from freecad_mcp.evidence_system.launch_source import LaunchSourceError
from freecad_mcp.evidence_system.host import select_host_interpreter
from freecad_mcp.evidence_system.validation import ValidationIssue as Issue
from tests.evidence_system.non_authoritative_signing import sign
from tests.evidence_system.packet_harness import run_packet
PY=Path(sys.executable).resolve();PYHASH=hashlib.sha256(PY.read_bytes()).hexdigest();BOOT=Path(__file__).parents[2]/"src/freecad_mcp/evidence_system/trusted_bootstrap.py";ENV={key:os.environ[key] for key in ("SystemRoot","WINDIR","ComSpec","TEMP","TMP") if os.environ.get(key)}
def make(tmp,command=["--ok"],runner="def main(request):\n from lib.support import VALUE\n return {'passed': VALUE == 1 and request.get('argv') == ['--ok'] and isinstance(request.get('package'), str)}\n",bootstrap=BOOT):
 p=tmp/"diagnostic";p.mkdir();(p/"runner.py").write_text(runner);prekey,_=sign(b"");fingerprint=hashlib.sha256(prekey).hexdigest();identity=["--run-id","P3-WP27","--attempt-id","tracked-bootstrap-test","--sequence","44","--scope","tracked-evidence-scope/44"];contract={"outer":[str(PY),"-I","-S","-B",str(bootstrap),str(p),"--reviewer-sha256",fingerprint,"--interpreter-sha256",PYHASH,*identity,"--",*command],"executor":[str(PY),"-I","-S","-B","/trusted/bootstrap.py"],"docker":[str(PY),"run"]};config=json.dumps({"runner":"runner.py","command_contract":contract},sort_keys=True,separators=(",",":")).encode();(p/"evidence-config.json").write_bytes(config);(p/"lib").mkdir();package=b"";(p/"lib"/"__init__.py").write_bytes(package);support=b"VALUE = 1\n";(p/"lib"/"support.py").write_bytes(support)
 m={"schema_version":1,"files":{"runner.py":hashlib.sha256((p/"runner.py").read_bytes()).hexdigest(),"evidence-config.json":hashlib.sha256(config).hexdigest(),"lib/__init__.py":hashlib.sha256(package).hexdigest(),"lib/support.py":hashlib.sha256(support).hexdigest()},"directories":["lib"]};raw=json.dumps(m,sort_keys=True,separators=(",",":")).encode();key,ms=sign(raw);now=datetime.now(timezone.utc);commands=hashlib.sha256(json.dumps(contract,sort_keys=True,separators=(",",":")).encode()).hexdigest()
 document={"schema_version":2,"status":"AUTHORIZED","run_id":"P3-WP27","attempt_id":"tracked-bootstrap-test","sequence":44,"nonce":"a"*64,"output_root":str(tmp/"out"),"configured_candidate":"b"*64,"raw_candidate":"c"*64,"repository":"d"*64,"image":"sha256:"+"e"*64,"package_manifest":hashlib.sha256(raw).hexdigest(),"trusted_bootstrap":hashlib.sha256(bootstrap.read_bytes()).hexdigest(),"commands":commands,"scope":"tracked-evidence-scope/44","reviewer_key":fingerprint,"not_before_utc":(now-timedelta(seconds=1)).isoformat(),"issued_utc":now.isoformat(),"expires_utc":(now+timedelta(minutes=5)).isoformat()};auth=json.dumps(document,sort_keys=True,separators=(",",":")).encode();_,au=sign(auth);wire=b"\0\0\0\vssh-ed25519\0\0\0 "+key
 for n,b in (("package-manifest.json",raw),("package-manifest.sig",base64.b64encode(ms)),("review-authorization.json",auth),("review-authorization.sig",base64.b64encode(au))):(p/n).write_bytes(b)
 (p/"reviewer.pub").write_text("ssh-ed25519 "+base64.b64encode(wire).decode());return p
def go(p,args=["--ok"],flags=["-I","-S","-B"],env=None,reviewer=None):
 wire=base64.b64decode((p/"reviewer.pub").read_text().split()[1]);reviewer=reviewer or hashlib.sha256(wire[-32:]).hexdigest()
 if flags==["-I","-S","-B"]:
  r=run_isolated(BOOT,p,args,env or ENV,hashlib.sha256(BOOT.read_bytes()).hexdigest(),PYHASH,reviewer,"P3-WP27","tracked-bootstrap-test",44,"tracked-evidence-scope/44")
 else:r=subprocess.run([str(PY),*flags,str(BOOT),str(p),"--reviewer-sha256",reviewer,"--interpreter-sha256",PYHASH,"--run-id","P3-WP27","--attempt-id","tracked-bootstrap-test","--sequence","44","--scope","tracked-evidence-scope/44","--",*args],capture_output=True,text=True,env=env or ENV)
 return r.returncode,json.loads(r.stdout)
def iss(x):return Issue(**x["issue"])
def assert_startup_issue(root,x,expected):
 assert not x["passed"] and iss(x)==expected and not (root/"out"/"final-verdict.json").exists()
def make_reparse(live,target,parked):
 os.replace(live,parked)
 if os.name=="nt":
  command='"{}" /d /c mklink /J "{}" "{}"'.format(os.environ["ComSpec"],live,target)
  created=subprocess.run(command,shell=False,capture_output=True,text=True,check=False)
  if created.returncode!=0:raise AssertionError("junction setup failed: "+created.stderr)
 else:os.symlink(target,live,target_is_directory=True)
def test_hostile_pythonpath(tmp_path):
 rc,x=go(make(tmp_path),env={**ENV,"PYTHONPATH":str(tmp_path)});assert rc==0 and x["passed"]
 assert select_host_interpreter({"FREECAD_MCP_EVIDENCE_PYTHON":str(PY)})==PY
 try:select_host_interpreter({"FREECAD_MCP_EVIDENCE_PYTHON":"relative-python"})
 except LaunchSourceError as error:assert error.issue==Issue("interpreter","HOST_INTERPRETER_RELATIVE","host-interpreter","/path")
 else:raise AssertionError("relative interpreter accepted")
 try:select_host_interpreter({"FREECAD_MCP_EVIDENCE_PYTHON":str(tmp_path/"missing-python")})
 except LaunchSourceError as error:assert error.issue==Issue("interpreter","HOST_INTERPRETER_MISSING","host-interpreter","/path")
 else:raise AssertionError("missing interpreter accepted")
 alternate=tmp_path/"alternate-checkout";alternate.mkdir();alternate_boot=alternate/"bootstrap.py";alternate_boot.write_bytes(BOOT.read_bytes());packet_root=tmp_path/"alternate-packet";packet_root.mkdir();packet=make(packet_root,bootstrap=alternate_boot);wire=base64.b64decode((packet/"reviewer.pub").read_text().split()[1]);reviewer=hashlib.sha256(wire[-32:]).hexdigest();completed=run_isolated(alternate_boot,packet,["--ok"],ENV,hashlib.sha256(alternate_boot.read_bytes()).hexdigest(),PYHASH,reviewer,"P3-WP27","tracked-bootstrap-test",44,"tracked-evidence-scope/44");assert completed.returncode==0 and json.loads(completed.stdout)["passed"]
 # Fresh signed packets exercise the root approval boundary too.  The
 # selector is rejected before package import when either its leaf or an
 # ancestor is a reparse point, and no packet can publish a verdict.
 target=tmp_path/"interpreter-target";target.mkdir();copy=target/PY.name;copy.write_bytes(PY.read_bytes());live=tmp_path/"interpreter-live";live.mkdir();make_reparse(live,target,tmp_path/"interpreter-parked")
 reparse_result,reparse_out=run_packet(tmp_path/"interpreter-reparse",host_interpreter=live/PY.name)
 assert reparse_result["issue"]=={"stage":"interpreter","code":"HOST_INTERPRETER_REPARSE","artifact":"host-interpreter","field":"/path"} and not (reparse_out/"final-verdict.json").exists()
 leaf_target=tmp_path/"interpreter-leaf-target";leaf_target.mkdir();leaf=tmp_path/"interpreter-leaf";leaf.mkdir();make_reparse(leaf,leaf_target,tmp_path/"interpreter-leaf-parked")
 leaf_result,leaf_out=run_packet(tmp_path/"interpreter-leaf-reparse",host_interpreter=leaf)
 assert leaf_result["issue"]=={"stage":"interpreter","code":"HOST_INTERPRETER_REPARSE","artifact":"host-interpreter","field":"/path"} and not (leaf_out/"final-verdict.json").exists()
 wrong_result,wrong_out=run_packet(tmp_path/"wrong-root-digest",approved_interpreter_sha256="f"*64)
 assert wrong_result["issue"]=={"stage":"interpreter","code":"HOST_INTERPRETER_HASH","artifact":PY.name,"field":"/sha256"} and not (wrong_out/"final-verdict.json").exists()
 mismatch_result,mismatch_out=run_packet(tmp_path/"signed-root-mismatch",{"signed_interpreter_sha256":"f"*64})
 assert mismatch_result["issue"]=={"stage":"authorization","code":"AUTHORIZATION_BINDING","artifact":"review-authorization.json","field":"/commands"} and not (mismatch_out/"final-verdict.json").exists()
 explicit_result,explicit_out=run_packet(tmp_path/"explicit-current-interpreter",{"kind":"docker","case":"missing"},host_interpreter=Path(sys.executable).resolve())
 assert explicit_result["issue"]=={"stage":"mount","code":"MOUNT_SET_CONTRACT","artifact":"inspect","field":"/Mounts"} and not (explicit_out/"final-verdict.json").exists()
 mcp_root=Path(__file__).resolve().parents[2]; repository=next((candidate for candidate in (mcp_root,*mcp_root.parents) if (candidate/"tools/mcp/freecad-mcp").is_dir()),mcp_root); mcp_checkout=repository/"tools/mcp/freecad-mcp" if repository!=mcp_root else mcp_root; tokens=("R"+"chie","C:/"+"Users","C:\\"+"Users","FreeCAD"+"Modeling","App"+"Data"+"/Local")
 sensitive_sources=[*mcp_checkout.joinpath("src/freecad_mcp/evidence_system").glob("*.py"),*mcp_checkout.joinpath("tests/evidence_system").glob("*.py")]; integration=repository/"tests/gui/part3/test_evidence_system_integration.py"; sensitive_sources.extend([integration] if integration.is_file() else [])
 assert not any(token in path.read_text(encoding="utf-8") for path in sensitive_sources for token in tokens)
 launch_source=(mcp_checkout/"src/freecad_mcp/evidence_system/launch_source.py").read_text(encoding="utf-8")
 assert 'kwargs["executable"] = interpreter.launch_path' in launch_source and 'argv[script_index] = self.launch_path' in launch_source
def test_cwd_shadow(tmp_path,monkeypatch):
 p=make(tmp_path);(tmp_path/"json.py").write_text("raise RuntimeError()");monkeypatch.chdir(tmp_path);rc,x=go(p);assert rc==0 and x["passed"]
def test_invalid_signature_before_import(tmp_path):
 marker=tmp_path/"marker";p=make(tmp_path,runner="def main(request): open(r'%s','w').write('x'); return {'passed': True}\n"%marker);(p/"package-manifest.sig").write_bytes(base64.b64encode(b"\0"*64));rc,x=go(p);assert rc==1 and not marker.exists();assert_startup_issue(tmp_path,x,Issue("startup","PACKAGE_SIGNATURE","package-manifest.sig","/"))
 anchored=tmp_path/"anchored";anchored.mkdir();p=make(anchored);wire=base64.b64decode((p/"reviewer.pub").read_text().split()[1]);approved=hashlib.sha256(wire[-32:]).hexdigest();other,_=sign(b"",bytes(reversed(range(32))));ssh=b"\0\0\0\vssh-ed25519\0\0\0 "+other;(p/"reviewer.pub").write_text("ssh-ed25519 "+base64.b64encode(ssh).decode());rc,x=go(p,reviewer=approved);assert rc==1;assert_startup_issue(anchored,x,Issue("authorization","REVIEWER_KEY_UNTRUSTED","reviewer.pub","/"))
def test_undeclared_bytecode(tmp_path):
 p=make(tmp_path);(p/"x.pyc").write_bytes(b"x");rc,x=go(p);assert rc==1;assert_startup_issue(tmp_path,x,Issue("startup","UNDECLARED_BYTECODE","x.pyc","/"))
 # The root launcher checks again after a mandatory actual reparse race,
 # placed precisely after its ancestor walk and before CreateFileW.
 live_root=tmp_path/"bootstrap-live";live_root.mkdir();stable=live_root/BOOT.name;stable.write_bytes(BOOT.read_bytes());target=tmp_path/"bootstrap-target";target.mkdir();marker=tmp_path/"root-race-hook";unapproved=tmp_path/"unapproved-root-side-effect";(target/BOOT.name).write_text("from pathlib import Path\nPath(r'%s').write_text('bad')\n"%unapproved);packet_root=tmp_path/"root-race";packet_root.mkdir();safe=make(packet_root,bootstrap=stable);wire=base64.b64decode((safe/"reviewer.pub").read_text().split()[1]);reviewer=hashlib.sha256(wire[-32:]).hexdigest()
 def race_before_open():make_reparse(live_root,target,tmp_path/"bootstrap-original");marker.write_text("hook-ran")
 try:run_isolated(stable,safe,["--ok"],ENV,hashlib.sha256(BOOT.read_bytes()).hexdigest(),PYHASH,reviewer,"P3-WP27","tracked-bootstrap-test",44,"tracked-evidence-scope/44",pre_open_hook=race_before_open)
 except LaunchSourceError as error:assert error.issue==Issue("startup","LAUNCH_SOURCE_REPARSE",BOOT.name,"/ancestors")
 else:raise AssertionError("reparse bootstrap was accepted")
 assert marker.read_text()=="hook-ran" and not unapproved.exists() and not (packet_root/"out"/"final-verdict.json").exists()
 # The approved root interpreter remains held across the explicit pre-spawn
 # hook.  On Windows the attempted replacement must be denied; the executed
 # packet is deliberately a non-PASS Docker mutation either way.
 if os.name=="nt":
  runtime=tmp_path/"portable-runtime";runtime.mkdir();portable=runtime/PY.name;shutil.copy2(PY,portable)
  for library in PY.parent.glob("python*.dll"):shutil.copy2(library,runtime/library.name)
  replacement=tmp_path/"replacement-interpreter";replacement.write_bytes(b"unapproved-interpreter-bytes");hook_marker=tmp_path/"interpreter-spawn-hook";malicious=tmp_path/"unapproved-interpreter-side-effect"
  def replace_interpreter():
   hook_marker.write_text("attempted")
   try:os.replace(replacement,portable)
   except PermissionError:hook_marker.write_text("denied")
   else:hook_marker.write_text("replaced")
  race_result,race_out=run_packet(tmp_path/"interpreter-spawn-race",{"kind":"docker","case":"missing"},host_interpreter=portable,pre_spawn_hook=replace_interpreter)
  assert hook_marker.read_text()=="denied" and not malicious.exists() and race_result["issue"]=={"stage":"authorization","code":"AUTHORIZATION_BINDING","artifact":"review-authorization.json","field":"/commands"} and not (race_out/"final-verdict.json").exists()
def test_old_authorization_new_argv(tmp_path):
 rc,x=go(make(tmp_path),["--new"]);assert rc==1;assert_startup_issue(tmp_path,x,Issue("authorization","AUTHORIZATION_BINDING","review-authorization.json","/commands"))
def test_missing_isolated_flag(tmp_path):
 rc,x=go(make(tmp_path),flags=["-S","-B"]);assert rc==1;assert_startup_issue(tmp_path,x,Issue("startup","ISOLATED_STARTUP","bootstrap","/flags"))
 missing_root=tmp_path/"missing-digest";missing_root.mkdir();duplicate_root=tmp_path/"duplicate-digest";duplicate_root.mkdir();p=make(missing_root);wire=base64.b64decode((p/"reviewer.pub").read_text().split()[1]);reviewer=hashlib.sha256(wire[-32:]).hexdigest();base=[str(PY),"-I","-S","-B",str(BOOT),str(p),"--reviewer-sha256",reviewer]
 for root,args in ((missing_root,base+["--run-id","P3-WP27","--attempt-id","tracked-bootstrap-test","--sequence","44","--scope","tracked-evidence-scope/44","--","--ok"]),(duplicate_root,base+["--interpreter-sha256",PYHASH,"--interpreter-sha256",PYHASH,"--run-id","P3-WP27","--attempt-id","tracked-bootstrap-test","--sequence","44","--scope","tracked-evidence-scope/44","--","--ok"])):
  if root.name=="duplicate-digest":p=make(root);wire=base64.b64decode((p/"reviewer.pub").read_text().split()[1]);reviewer=hashlib.sha256(wire[-32:]).hexdigest();args=[str(PY),"-I","-S","-B",str(BOOT),str(p),"--reviewer-sha256",reviewer,*args[8:]]
  completed=subprocess.run(args,capture_output=True,text=True,env=ENV);value=json.loads(completed.stdout);assert completed.returncode==1;assert_startup_issue(root,value,Issue("startup","BOOTSTRAP_ARGUMENTS","bootstrap","/"))
def test_startup_diagnostic_mount_writable(tmp_path):
 result,out=run_packet(tmp_path,{"kind":"docker","case":"writable"});assert result["issue"]=={"stage":"mount","code":"MOUNT_SET_CONTRACT","artifact":"inspect","field":"/Mounts"} and not (out/"final-verdict.json").exists()
def test_startup_diagnostic_mount_missing(tmp_path):
 result,out=run_packet(tmp_path,{"kind":"docker","case":"missing"});assert result["issue"]=={"stage":"mount","code":"MOUNT_SET_CONTRACT","artifact":"inspect","field":"/Mounts"} and not (out/"final-verdict.json").exists()
def test_startup_diagnostic_mount_changed(tmp_path):
 result,out=run_packet(tmp_path,{"kind":"docker","case":"changed"});assert result["issue"]=={"stage":"mount","code":"MOUNT_SET_CONTRACT","artifact":"inspect","field":"/Mounts"} and not (out/"final-verdict.json").exists()
