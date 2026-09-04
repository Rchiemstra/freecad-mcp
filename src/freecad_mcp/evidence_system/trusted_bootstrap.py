"""Direct Python-3.11 stdlib bootstrap; it imports no governed code first."""
from __future__ import annotations
import base64, hashlib, importlib.abc, importlib.util, json, os, stat, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

Q=2**255-19;D=(-121665*pow(121666,Q-2,Q))%Q;I=pow(2,(Q-1)//4,Q);L=2**252+27742317777372353535851937790883648493
B=(15112221349535400772501151409588531511454012693041857206046113283949847762202,46316835694926478169428394003475163141307993866256225615783033603165251855960)
def _issue(code,artifact,field="/",stage="startup"): return {"passed":False,"issue":{"stage":stage,"code":code,"artifact":artifact,"field":field}}
def _json(raw):
 def hook(rows):
  out={}
  for k,v in rows:
   if k in out: raise ValueError("duplicate")
   out[k]=v
  return out
 return json.loads(raw.decode(),object_pairs_hook=hook)
def _add(a,b):
 x,y=a;u,v=b;c=(x*v+y*u)%Q;d=(y*v+x*u)%Q
 return c*pow(1+D*x*u*y*v,Q-2,Q)%Q,d*pow(1-D*x*u*y*v,Q-2,Q)%Q
def _mul(p,n):
 r=(0,1)
 while n:
  if n&1:r=_add(r,p)
  p=_add(p,p);n>>=1
 return r
def _dec(x):
 if len(x)!=32:raise ValueError()
 y=int.from_bytes(x,"little")&((1<<255)-1);z=(y*y-1)*pow(D*y*y+1,Q-2,Q)%Q;a=pow(z,(Q+3)//8,Q)
 if a*a%Q!=z:a=a*I%Q
 if a*a%Q!=z:raise ValueError()
 return (Q-a if (a&1)!=(x[31]>>7) else a),y
def _verify(key,msg,sig):
 try:
  if len(key)!=32 or len(sig)!=64:return False
  r,s=sig[:32],int.from_bytes(sig[32:],"little")
  return s<L and _mul(B,s)==_add(_dec(r),_mul(_dec(key),int.from_bytes(hashlib.sha512(r+key+msg).digest(),"little")%L))
 except (ValueError,OverflowError):return False
def _reparse(path):
 try:return path.is_symlink() or bool(os.lstat(path).st_file_attributes&stat.FILE_ATTRIBUTE_REPARSE_POINT)
 except AttributeError:return path.is_symlink()
def _open_nofollow(path):
 if os.name!="nt":return os.open(path,os.O_RDONLY|getattr(os,"O_NOFOLLOW",0))
 import ctypes,msvcrt
 kernel=ctypes.WinDLL("kernel32",use_last_error=True);kernel.CreateFileW.restype=ctypes.c_void_p;kernel.CreateFileW.argtypes=[ctypes.c_wchar_p,ctypes.c_ulong,ctypes.c_ulong,ctypes.c_void_p,ctypes.c_ulong,ctypes.c_ulong,ctypes.c_void_p]
 handle=kernel.CreateFileW(str(path),0x80000000,7,None,3,0x00200000,None)
 if handle in (None,ctypes.c_void_p(-1).value):raise OSError(ctypes.get_last_error(),"CreateFileW")
 class Tag(ctypes.Structure):_fields_=[("attributes",ctypes.c_ulong),("tag",ctypes.c_ulong)]
 tag=Tag()
 if not kernel.GetFileInformationByHandleEx(ctypes.c_void_p(handle),9,ctypes.byref(tag),ctypes.sizeof(tag)) or tag.attributes&stat.FILE_ATTRIBUTE_REPARSE_POINT:
  kernel.CloseHandle(ctypes.c_void_p(handle));raise OSError("reparse point")
 return msvcrt.open_osfhandle(handle,os.O_RDONLY|os.O_BINARY)
def _read_regular(path):
 descriptor=_open_nofollow(path)
 try:
  before=os.fstat(descriptor)
  if not stat.S_ISREG(before.st_mode):raise OSError("not regular")
  chunks=[]
  while True:
   chunk=os.read(descriptor,1024*1024)
   if not chunk:break
   chunks.append(chunk)
  after=os.fstat(descriptor)
  identity=lambda value:(value.st_dev,value.st_ino,value.st_size,getattr(value,"st_mtime_ns",None))
  if identity(before)!=identity(after):raise OSError("file changed")
  return b"".join(chunks)
 finally:os.close(descriptor)
def _capture(root):
 if not root.is_absolute() or any(_reparse(ancestor) for ancestor in (root,*root.parents)):return None,_issue("PACKAGE_REPARSE","diagnostic")
 out={};inventory=set()
 for base,dirs,files in os.walk(root,followlinks=False):
  if _reparse(Path(base)) or "__pycache__" in dirs:return None,_issue("PACKAGE_REPARSE" if _reparse(Path(base)) else "UNDECLARED_BYTECODE",Path(base).name)
  for name in dirs:
   directory=Path(base,name);rel=directory.relative_to(root).as_posix()
   if _reparse(directory):return None,_issue("PACKAGE_REPARSE",rel)
   inventory.add(rel)
  for name in files:
   p=Path(base,name);rel=p.relative_to(root).as_posix()
   if _reparse(p):return None,_issue("PACKAGE_REPARSE",rel)
   if name.endswith((".pyc",".pyo",".pth")):return None,_issue("UNDECLARED_BYTECODE",rel)
   try:out[rel]=_read_regular(p)
   except OSError:return None,_issue("PACKAGE_CAPTURE_CHANGED",rel)
 return (out,frozenset(inventory)),None
def _hex(value):return isinstance(value,str) and len(value)==64 and all(c in "0123456789abcdef" for c in value)
def _invoked_interpreter():
 if os.name=="nt":return sys.executable
 value=(getattr(sys,"orig_argv",()) or (sys.executable,))[0]
 return value if isinstance(value,str) and Path(value).is_absolute() else sys.executable
def _time(value):
 try:
  parsed=datetime.fromisoformat(value.replace("Z","+00:00"));return parsed if parsed.tzinfo else None
 except (AttributeError,ValueError):return None
class _L(importlib.abc.Loader):
 def __init__(self,b,name,package=False):self.b=b;self.name=name;self.package=package
 def create_module(self,s):return None
 def exec_module(self,m):exec(compile(self.b,"<captured:"+self.name+">","exec"),m.__dict__)
class _F(importlib.abc.MetaPathFinder):
 def __init__(self,files):
  self.modules={}
  for name,data in files.items():
   if not name.endswith(".py") or name=="runner.py":continue
   parts=name.split("/");package=parts[-1]=="__init__.py";module=".".join(parts[:-1]) if package else ".".join(parts)[:-3]
   self.modules[module]=(data,name,package)
 def find_spec(self,fullname,path=None,target=None):
  if fullname not in self.modules:return None
  data,name,package=self.modules[fullname];return importlib.util.spec_from_loader(fullname,_L(data,name,package),is_package=package)
def run(root,argv,reviewer_anchor,interpreter_anchor,identity):
 if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):return _issue("ISOLATED_STARTUP","bootstrap","/flags")
 captured,error=_capture(root)
 if error:return error
 files,directories=captured
 envelope={"package-manifest.json","package-manifest.sig","review-authorization.json","review-authorization.sig","reviewer.pub"}
 if not envelope<=set(files):return _issue("PACKAGE_INVENTORY","package-manifest.json")
 try:
  wire=base64.b64decode(files["reviewer.pub"].decode().split()[1],validate=True);key=wire[-32:];ms=base64.b64decode(files["package-manifest.sig"],validate=True);au=base64.b64decode(files["review-authorization.sig"],validate=True)
 except Exception:return _issue("PACKAGE_SCHEMA","package-manifest.json")
 if len(wire)!=51 or wire[:19]!=b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20":return _issue("PACKAGE_SCHEMA","reviewer.pub")
 if not _hex(reviewer_anchor) or hashlib.sha256(key).hexdigest()!=reviewer_anchor:return _issue("REVIEWER_KEY_UNTRUSTED","reviewer.pub","/","authorization")
 if not _verify(key,files["package-manifest.json"],ms):return _issue("PACKAGE_SIGNATURE","package-manifest.sig")
 try:manifest=_json(files["package-manifest.json"])
 except Exception:return _issue("PACKAGE_SCHEMA","package-manifest.json")
 if not isinstance(manifest,dict) or set(manifest)!={"schema_version","files","directories"} or manifest["schema_version"]!=1 or not isinstance(manifest["files"],dict) or not isinstance(manifest["directories"],list):return _issue("PACKAGE_INVENTORY","package-manifest.json")
 governed=manifest["files"]
 if not {"runner.py","evidence-config.json"}<=set(governed) or any(not isinstance(name,str) or not isinstance(digest,str) or not _hex(digest) or name.startswith(("/","\\")) or ".." in Path(name).parts or name in envelope for name,digest in governed.items()):return _issue("PACKAGE_INVENTORY","package-manifest.json")
 if set(files)!=envelope|set(governed) or any(hashlib.sha256(files[name]).hexdigest()!=digest for name,digest in governed.items()):return _issue("PACKAGE_INVENTORY","package-manifest.json")
 declared_directories=manifest["directories"]
 if len(declared_directories)!=len(set(declared_directories)) or set(declared_directories)!=set(directories):return _issue("PACKAGE_INVENTORY","package-manifest.json","/directories")
 try:config=_json(files["evidence-config.json"]);auth=_json(files["review-authorization.json"])
 except Exception:return _issue("PACKAGE_SCHEMA","evidence-config.json")
 if not _verify(key,files["review-authorization.json"],au):return _issue("AUTHORIZATION_SIGNATURE","review-authorization.sig","/","authorization")
 if not isinstance(config,dict) or set(config) not in ({"runner","command_contract"},{"runner","command_contract","runtime"}) or config["runner"]!="runner.py":return _issue("PACKAGE_SCHEMA","evidence-config.json")
 contract=config["command_contract"]
 if not isinstance(contract,dict) or set(contract)!={"outer","executor","docker"} or not all(isinstance(contract[name],list) and contract[name] and all(isinstance(item,str) for item in contract[name]) for name in contract):return _issue("PACKAGE_SCHEMA","evidence-config.json","/command_contract")
 binding={"run_id","attempt_id","sequence","nonce","output_root","configured_candidate","raw_candidate","repository","image","package_manifest","trusted_bootstrap","commands","scope","reviewer_key"}
 required={"schema_version","status","not_before_utc","issued_utc","expires_utc"}|binding
 if not isinstance(auth,dict) or set(auth)!=required or auth["schema_version"]!=2 or auth["status"]!="AUTHORIZED":return _issue("AUTHORIZATION_SCHEMA","review-authorization.json","/","authorization")
 command_hash=hashlib.sha256(json.dumps(contract,sort_keys=True,separators=(",",":")).encode()).hexdigest()
 hashes=("nonce","configured_candidate","raw_candidate","repository","package_manifest","trusted_bootstrap","commands","reviewer_key")
 if any(not _hex(auth[name]) for name in hashes) or not isinstance(auth["sequence"],int) or isinstance(auth["sequence"],bool) or not auth["output_root"] or not auth["scope"] or not str(auth["image"]).startswith("sha256:"):return _issue("AUTHORIZATION_SCHEMA","review-authorization.json","/","authorization")
 expected={"package_manifest":hashlib.sha256(files["package-manifest.json"]).hexdigest(),"trusted_bootstrap":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),"commands":command_hash,"reviewer_key":hashlib.sha256(key).hexdigest()}
 if any(auth[name]!=value for name,value in expected.items()):return _issue("AUTHORIZATION_BINDING","review-authorization.json","/"+next(name for name,value in expected.items() if auth[name]!=value),"authorization")
 if any(auth[name]!=value for name,value in identity.items()):return _issue("AUTHORIZATION_SCOPE","review-authorization.json","/"+next(name for name,value in identity.items() if auth[name]!=value),"authorization")
 if not _hex(interpreter_anchor):return _issue("INTERPRETER_APPROVAL","bootstrap","/interpreter-sha256","interpreter")
 invoked=_invoked_interpreter()
 actual_outer=[invoked,"-I","-S","-B",str(Path(__file__).resolve()),str(root),"--reviewer-sha256",reviewer_anchor,"--interpreter-sha256",interpreter_anchor,"--run-id",identity["run_id"],"--attempt-id",identity["attempt_id"],"--sequence",str(identity["sequence"]),"--scope",identity["scope"],"--",*argv]
 if contract["outer"]!=actual_outer:return _issue("AUTHORIZATION_BINDING","review-authorization.json","/commands","authorization")
 runtime=config.get("runtime")
 if isinstance(runtime,dict) and isinstance(runtime.get("policy"),dict):
  policy=runtime["policy"];binaries=policy.get("binaries")
  if (not isinstance(binaries,dict) or binaries.get("host_interpreter")!=interpreter_anchor or policy.get("interpreter")!=invoked or policy.get("outer_argv")!=actual_outer or policy.get("executor_argv",[None])[0]!=invoked):return _issue("HOST_INTERPRETER_BINDING","evidence-config.json","/runtime/policy/interpreter","interpreter")
 now=datetime.now(timezone.utc);not_before=_time(auth["not_before_utc"]);issued=_time(auth["issued_utc"]);expires=_time(auth["expires_utc"])
 if None in (not_before,issued,expires) or not_before>issued or issued>expires or now<not_before or issued>now+timedelta(seconds=5) or expires<now or expires-issued>timedelta(minutes=15):return _issue("AUTHORIZATION_EXPIRED","review-authorization.json","/expires_utc","authorization")
 try:
  finder=_F({name:files[name] for name in governed});sys.meta_path.insert(0,finder);spec=importlib.util.spec_from_loader("_captured",_L(files["runner.py"],"runner.py"));mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);entry=getattr(mod,"main",None)
  if not callable(entry):raise RuntimeError("missing main")
  outcome=entry({"argv":list(argv),"package":str(root),"trusted_bootstrap":str(Path(__file__).resolve()),"interpreter":invoked,"interpreter_sha256":interpreter_anchor,"runtime":config.get("runtime"),"initial":{"document":files["review-authorization.json"],"signature":au,"reviewer_key":key}})
  if not isinstance(outcome,dict) or not isinstance(outcome.get("passed"),bool):raise RuntimeError("runner rejected")
  if outcome["passed"] is not True:
   if set(outcome)!={"passed","issue"} or not isinstance(outcome["issue"],dict) or set(outcome["issue"])!={"stage","code","artifact","field"} or not all(isinstance(outcome["issue"][name],str) and outcome["issue"][name] for name in ("stage","code","artifact","field")):raise RuntimeError("runner rejected")
   return outcome
  if outcome.get("issue") is not None:raise RuntimeError("runner rejected")
 except Exception:return _issue("RUNNER_FAILURE","runner.py","/","runner")
 finally:
  if 'finder' in locals() and finder in sys.meta_path:sys.meta_path.remove(finder)
 return {"passed":True,"issue":None}
def main(argv=None):
 values=list(sys.argv[1:] if argv is None else argv)
 if len(values)<14 or values[1]!="--reviewer-sha256" or values[3]!="--interpreter-sha256" or values[5]!="--run-id" or values[7]!="--attempt-id" or values[9]!="--sequence" or values[11]!="--scope" or values[13]!="--":result=_issue("BOOTSTRAP_ARGUMENTS","bootstrap")
 else:
  try:identity={"run_id":values[6],"attempt_id":values[8],"sequence":int(values[10]),"scope":values[12]};result=run(Path(values[0]),values[14:],values[2],values[4],identity)
  except ValueError:result=_issue("BOOTSTRAP_ARGUMENTS","bootstrap")
 print(json.dumps(result,sort_keys=True));return 0 if result["passed"] else 1
if __name__=="__main__":raise SystemExit(main())
