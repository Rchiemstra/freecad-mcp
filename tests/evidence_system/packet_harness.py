"""Reusable non-authoritative signed packets for production-entrypoint tests."""
from __future__ import annotations

import base64, hashlib, json, os, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tests.evidence_system.non_authoritative_signing import sign
from freecad_mcp.evidence_system.launcher import run_isolated
from freecad_mcp.evidence_system.launch_source import LaunchSourceError

ROOT = Path(__file__).parents[2]
SOURCE = ROOT / "src/freecad_mcp/evidence_system"
BOOT = SOURCE / "trusted_bootstrap.py"
PY = Path(sys.executable).resolve(); PYHASH = hashlib.sha256(PY.read_bytes()).hexdigest(); ENV = {key: os.environ[key] for key in ("SystemRoot","WINDIR","ComSpec","TEMP","TMP") if os.environ.get(key)}
HEX = "a" * 64
MOUNTS = lambda package, out: [
    {"Type":"bind","Source":str(package),"Destination":"/diagnostic","RW":False},
    {"Type":"bind","Source":str(BOOT),"Destination":"/trusted/bootstrap.py","RW":False},
    {"Type":"bind","Source":str(ROOT),"Destination":"/repo","RW":False},
    {"Type":"bind","Source":str(ROOT),"Destination":"/build","RW":False},
    {"Type":"bind","Source":str(out),"Destination":"/out","RW":True},
]


def run_packet(tmp_path: Path, mutation: dict[str, object] | None = None, *, host_interpreter: Path | None = None, approved_interpreter_sha256: str | None = None, pre_spawn_hook: object | None = None) -> tuple[dict[str, object], Path]:
    package = tmp_path / "diagnostic"; package.mkdir(parents=True); out = tmp_path / "out"; active_mutation = mutation or {}
    worker_root=tmp_path/"worker-root"; worker_root.mkdir(); worker=worker_root/"offline_worker.py"; worker.write_text(_WORKER.replace("__MUTATION_JSON__", repr(json.dumps(active_mutation))),encoding="utf-8")
    race_target = tmp_path / "worker-race-target"
    if active_mutation.get("kind") == "worker_race":
        race_target.mkdir(); (race_target / "offline_worker.mutation.json").write_text(json.dumps(active_mutation)); (race_target / "offline_worker.py").write_text("from pathlib import Path\nPath(r'%s').write_text('unapproved')\n" % (tmp_path / "unapproved-worker-side-effect"))
    replacement = tmp_path / "offline-worker-replacement.py"
    if active_mutation.get("kind") == "worker_swap": replacement.write_text("from pathlib import Path\nPath(r'%s').write_text('unapproved')\n" % (tmp_path / "unapproved-worker-side-effect"))
    interpreter = host_interpreter or PY
    try: interpreter_hash = hashlib.sha256(interpreter.read_bytes()).hexdigest()
    except OSError: interpreter_hash = "0" * 64
    signed_hash = str(active_mutation.get("signed_interpreter_sha256", interpreter_hash))
    public, _ = sign(b""); reviewer = hashlib.sha256(public).hexdigest(); mounts = MOUNTS(package, out)
    launch = [str(interpreter),"run","--network","none","--read-only","--tmpfs","/tmp:rw,nosuid,nodev,size=2g"] + [item for row in mounts for item in ("--mount",f"type=bind,src={row['Source']},dst={row['Destination']}"+("" if row["RW"] else ",readonly"))]+["sha256:"+"e"*64]
    outer = [str(interpreter),"-I","-S","-B",str(BOOT),str(package),"--reviewer-sha256",reviewer,"--interpreter-sha256",signed_hash,"--run-id","P3-WP27","--attempt-id","packet-harness","--sequence","44","--scope","tracked-evidence-scope/44","--","--packet"]
    executor_command=[str(interpreter),"-I","-S","-B",str(worker)]
    contract={"outer":outer,"executor":executor_command,"docker":launch}
    policy={"run_id":"P3-WP27","attempt_id":"packet-harness","sequence":44,"reviewer_key":reviewer,"scope":"tracked-evidence-scope/44","interpreter":str(interpreter),"outer_argv":outer,"executor_argv":contract["executor"],"docker_argv":launch,"environment":{},"container_environment":{},"mounts":mounts,"sources":{},"binaries":{"host_interpreter":signed_hash},"container_entrypoint":["/usr/bin/python3","-I","-S","-B","/trusted/bootstrap.py"],"container_cmd":[]}
    config=json.dumps({"runner":"runner.py","command_contract":contract,"runtime":{"policy":policy,"executor_command":executor_command,"executor_sha256":hashlib.sha256(worker.read_bytes()).hexdigest()}},sort_keys=True,separators=(",",":")).encode()
    governed={"runner.py":_runner_source(active_mutation,worker_root,race_target,replacement,tmp_path),"evidence-config.json":config,"freecad_mcp/__init__.py":b""}
    for source in SOURCE.glob("*.py"): governed[f"freecad_mcp/evidence_system/{source.name}"]=source.read_bytes()
    for name,data in governed.items(): target=package/name; target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    manifest=json.dumps({"schema_version":1,"files":{name:hashlib.sha256(data).hexdigest() for name,data in governed.items()},"directories":["freecad_mcp","freecad_mcp/evidence_system"]},sort_keys=True,separators=(",",":")).encode(); public,manifest_sig=sign(manifest); now=datetime.now(timezone.utc)
    auth={"schema_version":2,"status":"AUTHORIZED","run_id":"P3-WP27","attempt_id":"packet-harness","sequence":44,"nonce":HEX,"output_root":str(out),"configured_candidate":"b"*64,"raw_candidate":"c"*64,"repository":"d"*64,"image":"sha256:"+"e"*64,"package_manifest":hashlib.sha256(manifest).hexdigest(),"trusted_bootstrap":hashlib.sha256(BOOT.read_bytes()).hexdigest(),"commands":hashlib.sha256(json.dumps(contract,sort_keys=True,separators=(",",":")).encode()).hexdigest(),"scope":"tracked-evidence-scope/44","reviewer_key":hashlib.sha256(public).hexdigest(),"not_before_utc":(now-timedelta(seconds=1)).isoformat(),"issued_utc":now.isoformat(),"expires_utc":(now+timedelta(minutes=5)).isoformat()}
    raw=json.dumps(auth,sort_keys=True,separators=(",",":")).encode(); _,auth_sig=sign(raw); wire=b"\0\0\0\vssh-ed25519\0\0\0 "+public
    for name,data in {"package-manifest.json":manifest,"package-manifest.sig":base64.b64encode(manifest_sig),"review-authorization.json":raw,"review-authorization.sig":base64.b64encode(auth_sig),"reviewer.pub":b"ssh-ed25519 "+base64.b64encode(wire)}.items():(package/name).write_bytes(data)
    try:
        completed=run_isolated(BOOT,package,["--packet"],{**ENV,"FREECAD_MCP_EVIDENCE_PYTHON":str(interpreter),"TEMP":str(tmp_path),"TMP":str(tmp_path)},hashlib.sha256(BOOT.read_bytes()).hexdigest(),approved_interpreter_sha256 or interpreter_hash,reviewer,"P3-WP27","packet-harness",44,"tracked-evidence-scope/44",timeout=30,pre_spawn_hook=pre_spawn_hook if callable(pre_spawn_hook) else None)
        return json.loads(completed.stdout), out
    except LaunchSourceError as error:
        return {"passed":False,"issue":{"stage":error.issue.stage,"code":error.issue.code,"artifact":error.issue.artifact,"field":error.issue.field}}, out


def _runner_source(mutation: dict[str, object], worker_root: Path, race_target: Path, replacement: Path, root: Path) -> bytes:
    if mutation.get("kind") not in {"worker_race","worker_swap"}:
        return b"from freecad_mcp.evidence_system.runner import bootstrap_entrypoint\ndef main(request): return bootstrap_entrypoint(request)\n"
    # This is a signed packet-only deterministic hook.  It replaces the
    # worker's checked ancestor *after* the gate's first walk and before its
    # CreateFileW call.  A failed setup raises, so the test cannot silently
    # omit the race; no production runner supplies this hook.
    if mutation.get("kind") == "worker_race": return ("""from freecad_mcp.evidence_system.runner import bootstrap_entrypoint
def main(request):
 def before_open():
  import os, subprocess
  from pathlib import Path
  live=Path(%r); parked=Path(%r); target=Path(%r); marker=Path(%r)
  os.replace(live,parked)
  if os.name == 'nt':
   command='"{}" /d /c mklink /J "{}" "{}"'.format(os.environ['ComSpec'],live,target)
   completed=subprocess.run(command,shell=False,capture_output=True,text=True,check=False)
   if completed.returncode != 0: raise RuntimeError('junction setup failed')
  else: os.symlink(target,live,target_is_directory=True)
  marker.write_text('hook-ran')
 return bootstrap_entrypoint(request,executor_pre_open_hook=before_open)
""" % (str(worker_root), str(worker_root.with_name("worker-root-original")), str(race_target), str(root / "worker-race-hook"))).encode()
    return ("""from freecad_mcp.evidence_system.runner import bootstrap_entrypoint
def main(request):
 def before_spawn():
  import os
  from pathlib import Path
  worker=Path(%r); replacement=Path(%r); marker=Path(%r)
  try: os.replace(replacement,worker); marker.write_text('swap-succeeded')
  except OSError: marker.write_text('swap-denied')
 return bootstrap_entrypoint(request,executor_pre_spawn_hook=before_spawn)
""" % (str(worker_root / "offline_worker.py"), str(replacement), str(root / "worker-swap-hook"))).encode()


_WORKER = '''from datetime import datetime,timezone
from pathlib import Path
import hashlib,json,sys
mutation=json.loads(__MUTATION_JSON__); request=json.loads(Path(sys.argv[3]).read_text()); binding=request["binding"]; policy=request["policy"]; kind=mutation.get("kind")
if kind=="worker_swap":Path(__file__).parents[1].joinpath("approved-worker-ran").write_text("ran")
if sys.argv[1]=="--cleanup-request":print(json.dumps({"passed":True,"errors":[]}));raise SystemExit()
checks=("package","authorization","configured_candidate","raw_candidate","repository","sources","binaries","image","output_freshness","conflicting_processes","port","cache","resolved_outer_command","resolved_executor_command","resolved_docker_command","environment","mounts","timestamp_freshness")
if sys.argv[1]=="--preflight-request":
 if kind=="worker_swap": print("{");raise SystemExit()
 values={"package":binding["package_manifest"],"authorization":{"authorization_sha256":binding["authorization_sha256"],"signature_sha256":binding["signature_sha256"]},"configured_candidate":binding["configured_candidate"],"raw_candidate":binding["raw_candidate"],"repository":binding["repository"],"sources":policy["sources"],"binaries":policy["binaries"],"image":binding["image"],"output_freshness":True,"conflicting_processes":[],"port":{"available":True},"cache":{"clean":True},"resolved_outer_command":policy["outer_argv"],"resolved_executor_command":policy["executor_argv"],"resolved_docker_command":policy["docker_argv"],"environment":policy["environment"],"mounts":policy["mounts"],"timestamp_freshness":True}; rows=[{"id":name,"status":"PASS","binding":binding,"value":values[name]} for name in checks]
 observed=datetime.now(timezone.utc).isoformat()
 if kind=="preflight":
  if mutation["check"]=="timestamp_freshness": observed="2000-01-01T00:00:00+00:00"
  else:
   row=next(row for row in rows if row["id"]==mutation["check"]); row["value"]="invalid"; row["status"]="FAIL"
 print(json.dumps({"schema_version":44,"binding":binding,"observed_utc":observed,"passed":True,"checks":rows,"commands":{"outer":policy["outer_argv"],"executor":policy["executor_argv"],"docker":policy["docker_argv"]},"output_fresh":True},sort_keys=True));raise SystemExit()
out=Path(request["output"]); ident="b"*64; inspect={"Id":ident,"Config":{"Image":binding["image"],"Entrypoint":["/usr/bin/python3","-I","-S","-B","/trusted/bootstrap.py"],"Cmd":[],"Env":[]},"HostConfig":{"NetworkMode":"none","ReadonlyRootfs":True,"Tmpfs":{"/tmp":"rw,nosuid,nodev,size=2g"}},"Mounts":policy["mounts"]}
if kind=="docker" and mutation.get("case")=="writable":inspect["Mounts"][0]["RW"]=True
if kind=="docker" and mutation.get("case")=="missing":inspect["Mounts"]=inspect["Mounts"][1:]
if kind=="docker" and mutation.get("case")=="changed":inspect["Mounts"][0]["Source"]="C:/other"
launch=list(policy["docker_argv"]); kernel="rw,nosuid,nodev,size=2g"
if kind=="docker" and mutation.get("case")=="tmpfs_launch":launch.remove("--tmpfs")
if kind=="docker" and mutation.get("case")=="tmpfs_inspect":inspect["HostConfig"]["Tmpfs"]={"/tmp":"rw,nodev,nosuid,size=2g"}
if kind=="docker" and mutation.get("case")=="tmpfs_kernel":kernel="rw,nosuid,nodev,size=1g"
raw=json.dumps(inspect,sort_keys=True,separators=(",",":")); container={"execution":binding,"container_id":ident,"raw_inspect_sha256":hashlib.sha256(raw.encode()).hexdigest()}
def write(name,phase,status="SUCCEEDED",record=container,extra=False):
 value={"schema_version":44,"binding":record,"phase":phase,"status":status}; value.update({"extra":True} if extra else {}); (out/name).open("x").write(json.dumps(value))
if kind=="child" and mutation.get("case")=="unknown": (out/"foreign-result.json").open("x").write("{}")
else:
 case=mutation.get("case") if kind=="child" else ""
 if case=="malformed":(out/"gdb-resolution.json").open("x").write("{")
 elif case!="missing_gdb":write("gdb-resolution.json","gdb_resolution","FAILED" if case=="contradiction" else "SUCCEEDED",record={**container,"execution":{**binding,"nonce":"d"*64}} if case=="foreign" else ({**container,"container_id":"d"*64} if case=="foreign_container" else container),extra=case=="added")
 if case!="missing_localization":write("localization-result.json","localization","UNKNOWN" if case=="status" else "SUCCEEDED")
 if case not in ("missing_terminal","failure","parent"):write("child-terminal-result.json","terminal")
 if case in ("multiple","failure","parent"):write("child-failure-result.json","terminal","FAILED")
exit_code=0
if kind=="child" and mutation.get("case")=="failure":exit_code=1
inspect["_raw_bytes"]=raw;print(json.dumps({"execution":{"status":"SUCCEEDED","docker":{"launch":launch,"inspect":inspect,"kernel_tmpfs":kernel}},"parent_exit":exit_code,"container_id":ident,"raw_inspect_sha256":container["raw_inspect_sha256"]}))
'''
