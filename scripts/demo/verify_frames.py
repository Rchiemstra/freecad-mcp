#!/usr/bin/env python3
"""Inspect every decoded GIF frame, with OCR cached only for identical pixels.

Requires Pillow, numpy, OpenCV, ffmpeg and tesseract. Also checks the MP4 at
native frame rate. Outputs frame-indexed failures and contact sheets for review.
No CAD or rendering processes are started. Exit nonzero on a delivery defect.
"""
import argparse, hashlib, io, json, re, subprocess, os, math
os.environ["OMP_THREAD_LIMIT"]="1"
from pathlib import Path
import cv2
cv2.setNumThreads(1)
import numpy as np
from PIL import Image, ImageDraw, ImageSequence
R=Path(__file__).resolve().parents[2];S=R/'demo-out/stage3'
BAD=re.compile(r'traceback|broken\s*pipe|auto.?save document|too many opened|non.intrusive|notifications are being|condensed preview|python exception|error occurred|failed to auto',re.I)
MENU=re.compile(r'File\s+Edit\s+View',re.I)
PEAK_MPA=json.loads((S/'replay-fem.json').read_text())['result']['stress_MPa']
OCR_ENGINE=subprocess.check_output(['tesseract','--version'],stderr=subprocess.STDOUT).splitlines()[0].decode()
CACHE_PATH=S/'frame-audit/tesseract-cache-v1.json'
OCR_CACHE=json.loads(CACHE_PATH.read_text()) if CACHE_PATH.exists() else {}

def ocr(im, psm=11):
 key=OCR_ENGINE+':'+str(im.size)+':'+str(psm)+':'+hashlib.sha256(im.tobytes()).hexdigest()
 if key not in OCR_CACHE:
  b=io.BytesIO();im.save(b,format='PNG')
  OCR_CACHE[key]=subprocess.check_output(['tesseract','stdin','stdout','--psm',str(psm)],input=b.getvalue(),stderr=subprocess.DEVNULL).decode()
 return OCR_CACHE[key]

def inspect(name, frames, size, out, frame_count, sample_count=8):
 out=out.resolve()
 sample_prefix=Path(name).stem+'-'+Path(name).suffix.lstrip('.')
 failures=[];samples=[];count=0;elapsed=0;previous=None;previous_ch=None;max_jump=0;seen=set();legend_frames=0;chapters=set();previous_footer=""
 chosen=sorted(set(round(i*(frame_count-1)/(sample_count-1)) for i in range(sample_count)))
 for index, (im,dt) in enumerate(frames):
  im=im.convert('RGB');w,h=im.size;arr=np.asarray(im);gray=cv2.cvtColor(arr,cv2.COLOR_RGB2GRAY)
  # Coordinates are relative to the cropped 1600 x 932 presentation.
  scene=im.crop((0,round(h*190/932),w,round(h*764/932)))
  a=np.asarray(scene);mask=np.max(np.abs(a.astype(np.int16)-np.array([240,242,243])),axis=2)>42
  if gray.mean()<45 or np.mean(gray>80)<.12:failures.append([index,'black/dark frame'])
  if mask[:,:round(w*1030/1600)].mean()<.002:failures.append([index,'blank CAD viewport'])
  top=im.crop((0,0,w,round(h*190/932)));footer=im.crop((0,round(h*764/932),w,h))
  toptext=ocr(top,6);foottext=ocr(footer,6)
  scene_text=ocr(scene.resize((scene.width*2,scene.height*2)))
  text=toptext+'\n'+foottext+'\n'+scene_text
  if re.search(r'FreeCAD|exception|error',scene_text,re.I) and re.search(r'\b(OK|Cancel|Abort|Retry)\b',scene_text,re.I):failures.append([index,'dialog in CAD viewport'])
  for bad in BAD.finditer(text):failures.append([index,'popup/stamp text: '+bad[0]])
  # Menu glyphs are tiny neutral black; chapter headings are larger teal.
  menu_band=arr[:10,:min(500,w)].astype(np.int16)
  neutral_dark=(menu_band.max(2)-menu_band.min(2)<35)&(menu_band.max(2)<160)
  if MENU.search(toptext) or neutral_dark.sum()>45:failures.append([index,'main-window menu chrome'])
  match=re.search(r'0?([1-7])\s*/\s*0?7',toptext)
  ch=int(match[1]) if match else previous_ch
  chapters.add(ch)
  if ch==3:
   # The two stationary neighbours remain visible throughout the pick. A native
   # commit replay can briefly replace/hide scene geometry before it settles.
   red=((a[:,:,0]>95)&(a[:,:,0]>a[:,:,1]*1.8)&(a[:,:,0]>a[:,:,2]*1.4)).astype(np.uint8)
   _,_,stats,_=cv2.connectedComponentsWithStats(red)
   if sum(s[cv2.CC_STAT_AREA]>70 for s in stats[1:])<2:failures.append([index,'missing neighbouring fruit / unsettled scene'])
  if not match:failures.append([index,'missing/cut-off chapter label'])
  if 'You:' not in toptext and 'You;' not in toptext:failures.append([index,'missing/cut-off prompt'])
  if 'proves' not in toptext.lower():failures.append([index,'missing/cut-off proof label'])
  if not all(x in foottext.lower() for x in ['scripted','replay','captions','estimated','measured']):failures.append([index,'missing/cut-off disclosure'])
  # Text must retain an outside margin; cropped glyphs reaching an image edge fail.
  for label,region in [('top',np.asarray(top)),('footer',np.asarray(footer))]:
   ink=np.max(np.abs(region.astype(np.int16)-[240,242,243]),axis=2)>80
   if ink[:,:5].any() or ink[:,-5:].any() or (label=='footer' and ink[-1].any()):failures.append([index,'cut-off '+label+' at side edge'])
  if ch==6:
   legend_frames+=1
   leg=im.crop((round(w*1300/1600),round(h*204/932),w,round(h*754/932)))
   lt=ocr(leg,6)
   la=np.asarray(leg).astype(np.int16)
   red=(la[:,:,0]>160)&(la[:,:,1]<150)&(la[:,:,2]<150)
   blue=(la[:,:,2]>160)&(la[:,:,0]<150)&(la[:,:,1]<150)
   if not ('MPa' in lt and ('%.3f'%PEAK_MPA) in lt and re.search(r'0[.,]000',lt) and red.sum()>35 and blue.sum()>35):failures.append([index,'missing stress legend, endpoints or MPa units'])
  current=cv2.cvtColor(np.asarray(scene),cv2.COLOR_RGB2GRAY)
  # A deliberate shot cut introduces the explicitly labelled tray preview.
  tray_cut=(ch==3 and 'tray transfer' in foottext.lower() and 'tray transfer' not in previous_footer.lower())
  if previous is not None and ch==previous_ch and not tray_cut:
   diff=np.mean(np.abs(current.astype(float)-previous.astype(float))>30)
   features=cv2.goodFeaturesToTrack(previous,200,.04,8)
   jump=0
   if features is not None and len(features)>=12:
    points,status,_=cv2.calcOpticalFlowPyrLK(previous,current,features,None)
    good=status.ravel()==1
    if good.sum()<len(features)*.35 and diff>.12:failures.append([index,'abrupt viewport change: lost tracking'])
    if good.sum()>=12:
     matrix,inliers=cv2.estimateAffinePartial2D(features[good],points[good],method=cv2.RANSAC,ransacReprojThreshold=2)
     if matrix is not None and inliers.sum()>=12:
      center=np.array([current.shape[1]/2,current.shape[0]/2])
      shift=np.linalg.norm(matrix[:,:2]@center+matrix[:,2]-center)
      scale=np.linalg.norm(matrix[0,:2]);angle=abs(math.degrees(math.atan2(matrix[1,0],matrix[0,0])));jump=float(shift)
      if shift>24 or abs(scale-1)>.09 or angle>8:failures.append([index,'camera jump (center shift %.1f px, scale %.3f, angle %.1f)'%(shift,scale,angle)])
   max_jump=max(max_jump,jump)
   if diff>.32:failures.append([index,'abrupt viewport change %.3f'%diff])
  previous=current;previous_ch=ch;previous_footer=foottext
  digest=hashlib.sha256(im.tobytes()).hexdigest();seen.add(digest)
  # Store evenly spaced frames later; lightweight thumbnails suffice for review.
  if index in chosen:samples.append((index,elapsed,im.copy()))
  count+=1;elapsed+=dt
  if index%100==0:print(name,index,'frames checked',flush=True)
 # Eight actual output frames, including frame zero and the final frame.
 assert count==frame_count,(name,count,frame_count)
 sheet=Image.new('RGB',(960*2,(560+32)*4),'white');draw=ImageDraw.Draw(sheet)
 paths=[]
 for j,(idx,t,im) in enumerate(samples):
  p=out/(sample_prefix+'-frame-%04d.png'%idx);im.save(p);paths.append(str(p.relative_to(R)))
  thumb=im.resize((960,560));x=(j%2)*960;y=(j//2)*592
  sheet.paste(thumb,(x,y));draw.text((x+12,y+566),'frame %d | %.2f s'%(idx,t),fill='black')
 sheet.save(out/(sample_prefix+'-contact.png'))
 report={'name':name,'frames_checked':count,'presentation_frames_10fps':round(elapsed*10),'unique_frames':len(seen),'duration_seconds':round(elapsed,3),'bytes':size,'chapters':sorted(c for c in chapters if c is not None),'legend_frames':legend_frames,'max_affine_shift_px':round(max_jump,3),'sample_frames':chosen,'sample_paths':paths,'failures':failures,'sha256':hashlib.sha256((R/name).read_bytes()).hexdigest()}
 return report

def gif_frames(path):
 with Image.open(path) as gif:
  for frame in ImageSequence.Iterator(gif):
   # GIF may coalesce identical samples into one duration: inspect every decoded
   # stored frame and report the full 10 fps presentation count separately.
   yield frame.copy(),frame.info.get('duration',100)/1000

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--video',action='store_true');ap.add_argument('--only',nargs='*');args=ap.parse_args()
 out=S/'frame-audit';out.mkdir(exist_ok=True)
 names=args.only or [str(p.relative_to(R)) for p in sorted((R/'assets').glob('strawberry-picker*.gif'))]
 reports=[]
 for name in names:
  p=R/name
  with Image.open(p) as im:
   assert im.width==960,(name,im.size)
   frame_count=im.n_frames
  assert p.stat().st_size<=2_500_000,(name,p.stat().st_size)
  reports.append(inspect(name,gif_frames(p),p.stat().st_size,out,frame_count))
  CACHE_PATH.write_text(json.dumps(OCR_CACHE))
  (out/'report.json').write_text(json.dumps({'result':'FAIL' if any(r['failures'] for r in reports) else 'PASS','files':reports},indent=2))
 if args.video:
  name='demo-out/strawberry-picker.mp4';p=R/name
  frame_count=int(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=nb_frames','-of','csv=p=0',str(p)]))
  proc=subprocess.Popen([str(R/'scripts/demo/ffmpeg-bounded.sh'),'-v','error','-i',str(p),'-vf','scale=960:560','-f','rawvideo','-pix_fmt','rgb24','-'],stdout=subprocess.PIPE)
  def frames():
   while True:
    b=proc.stdout.read(960*560*3)
    if not b:break
    assert len(b)==960*560*3
    yield Image.frombytes('RGB',(960,560),b),.1
  reports.append(inspect(name,frames(),p.stat().st_size,out,frame_count));assert proc.wait()==0
 CACHE_PATH.write_text(json.dumps(OCR_CACHE))
 result={'result':'FAIL' if any(r['failures'] for r in reports) else 'PASS','files':reports}
 (out/'report.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({**result,'files':[{k:v for k,v in r.items() if k!='sample_paths'} for r in reports]},indent=2))
 return 1 if result['result']=='FAIL' else 0
if __name__=='__main__':raise SystemExit(main())
