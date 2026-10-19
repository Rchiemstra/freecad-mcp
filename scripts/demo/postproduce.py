#!/usr/bin/env python3
"""Trim idle capture time, soften chapter boundaries, encode bounded GIFs.
All 3-D pixels come from the continuously recorded real GUI.
"""
import argparse,hashlib,json,subprocess
from pathlib import Path
from replay_cameras import CAMERAS
from caption_panels import sequence
ROOT=Path(__file__).resolve().parents[2];O=ROOT/'demo-out/stage3';A=ROOT/'assets'
FF=ROOT/'scripts/demo/ffmpeg-bounded.sh'
ENC=['-c:v','libx264','-preset','fast','-crf','20','-pix_fmt','yuv420p']
def run(args):subprocess.run([str(FF),'-y','-hide_banner','-loglevel','error',*map(str,args)],check=True)
def duration(p):return float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',str(p)]))
def gif(source,target,seconds,budget):
 vf=f'setpts=(PTS-STARTPTS)*{seconds/duration(source)},fps=10,scale=960:-1:flags=lanczos'
 vf+=",drawbox=x=0:y=574:w=960:h=26:color=0xf0f2f3:t=fill,drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:text='Condensed preview':x=24:y=578:fontsize=16:fontcolor=0x263d46"
 palette=O/(target.stem+'-palette.png')
 for colors in [96,64,48,32]:
  run(['-i',source,'-vf',vf+f',palettegen=max_colors={colors}:stats_mode=diff','-frames:v','1',palette])
  run(['-i',source,'-i',palette,'-filter_complex_threads','1','-lavfi',f'[0:v]{vf}[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle','-loop','0',target])
  if target.stat().st_size<=budget:return
 raise RuntimeError(f'{target} exceeds {budget} bytes')
def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--chapters',nargs='+',type=int,help='Re-encode only these chapters; retain verified existing chapter clips.')
 options=parser.parse_args()
 previous={c['number']:c for c in json.loads((O/'media-report.json').read_text())['chapters']} if options.chapters else {}
 review=json.loads((O/'frame-review.json').read_text()) if (O/'frame-review.json').exists() else {}
 chapters=json.loads((O/'timeline.json').read_text());assert len(chapters)==7
 clips=[];report=[];cursor=0
 for ch in chapters:
  n=ch['number'];dest=O/f'chapter-{n:02d}.mp4'
  if options.chapters and n not in options.chapters:
   entry=previous[n].copy();assert dest.exists()
   entry['start_seconds']=round(cursor,3)
   assert abs(duration(dest)-entry['duration_seconds'])<.01
   clips.append(dest);report.append(entry);cursor+=entry['duration_seconds']
   continue
  # A 0.12 s capture-start allowance keeps samples inside settled GUI intervals.
  sources=ch.get('prior_takes',[])+[{'source':ch.get('source','raw.mp4'),'intervals':[(a,min(b,ch['end'])) for a,b in ch['intervals'] if a<ch['end']]}]
  signature=hashlib.sha256(json.dumps(sources,sort_keys=True).encode()).hexdigest()
  parts=[];source_intervals=[]
  pauses=json.loads((O/'capture-pauses.json').read_text()) if (O/'capture-pauses.json').exists() else []
  for index,source in enumerate(sources):
   selected=source['intervals']
   for pause in pauses:
    if pause['source']!=source['source']:continue
    pieces=[]
    for a,b in selected:
     if b<=pause['start'] or a>=pause['end']:pieces.append((a,b));continue
     if a<pause['start']:pieces.append((a,pause['start']))
     if b>pause['end']:pieces.append((pause['end'],b))
    selected=pieces
   intervals=[[max(0,a-.12),max(.01,b-.12)] for a,b in selected if b>a]
   source_intervals.append({'source':source['source'],'intervals':intervals})
   # Read only this chapter's source window. Long native tool waits can make
   # a raw take much longer than the edited story; later chapters must not
   # decode the entire preceding motion take again.
   seek=max(0,(__import__('math').floor(min(a for a,b in intervals)*10)-2)/10)
   window=max(b for a,b in intervals)-seek+.2
   expression='+'.join(f'between(t,{a-seek:.4f},{b-seek:.4f})' for a,b in intervals)
   script=O/f'select-{n:02d}-{index:02d}.txt';script.write_text(f"select='{expression}',setpts=N/(10*TB),fps=10")
   part=O/f'rough-{n:02d}-{index:02d}.mp4'
   run(['-ss',seek,'-t',window,'-i',O/source['source'],'-an','-filter_script:v',script,*ENC,part]);parts.append(part)
  rough=O/f'rough-{n:02d}.mp4'
  join=O/f'join-{n:02d}.txt';join.write_text(''.join("file '%s'\n"%p for p in parts))
  run(['-f','concat','-safe','0','-i',join,'-c','copy',rough])
  reviewed=review.get(str(n))
  if reviewed:
   assert reviewed['source_signature']==signature,'Frame review belongs to another capture'
   expression='+'.join(f'between(n,{a},{b})' for a,b in reviewed['drop_ranges'])
   clean=O/f'reviewed-{n:02d}.mp4'
   run(['-i',rough,'-vf',f"select='not({expression})',setpts=N/(10*TB)",*ENC,clean]);rough=clean
  d=duration(rough)
  panel_source=sequence(ch,round(d*10));panel_video=O/f'caption-{n:02d}.mov'
  run(['-f','concat','-safe','0','-i',panel_source,'-vf','fps=10','-frames:v',round(d*10),'-c:v','png','-pix_fmt','rgba',panel_video])
  clean=O/f'captioned-{n:02d}.mp4'
  run(['-i',rough,'-i',panel_video,'-filter_complex_threads','1','-filter_complex','[0:v][1:v]overlay=0:0:shortest=1','-an',*ENC,clean]);rough=clean
  run(['-i',rough,'-vf',f'fade=t=in:st=0:d=0.6,fade=t=out:st={d-.6}:d=0.6',*ENC,dest])
  clips.append(dest)
  report.append({'number':n,'title':ch['title'],'start_seconds':round(cursor,3),'duration_seconds':duration(dest),'prompt':ch['prompt'],'proof':ch['proof'],'start_hold_seconds':4.4,'end_hold_seconds':4.4,'fade_seconds':.6,'camera':'one fixed camera per chapter','source_intervals':source_intervals})
  selected_intervals=[z for src in ch.get('prior_takes',[]) for z in src['intervals']]+ch['intervals']
  selected_frames=[round((b-a)*10) for a,b in selected_intervals]
  report[-1]['start_hold_seconds']=selected_frames[0]/10
  report[-1]['end_hold_seconds']=(selected_frames[-1]+round(d*10)-sum(selected_frames))/10
  report[-1]['camera_parameters']=CAMERAS[{1:'build',2:'force',3:'scene',4:'nose',5:'nose',6:'fem',7:'parts'}[n]]
  if reviewed:
   report[-1].update(frame_review=reviewed,start_hold_seconds=reviewed['start_hold_seconds'],end_hold_seconds=reviewed['end_hold_seconds'])
  cursor+=duration(dest)
  print(n,ch['title'],duration(dest),flush=True)
 manifest=O/'concat.txt';manifest.write_text(''.join("file '%s'\n"%p for p in clips))
 metadata=O/'chapters.ffmeta'
 metadata.write_text(';FFMETADATA1\n'+''.join('[CHAPTER]\nTIMEBASE=1/1000\nSTART=%d\nEND=%d\ntitle=%s\n'%(round(c['start_seconds']*1000),round((c['start_seconds']+c['duration_seconds'])*1000),c['title']) for c in report))
 final=ROOT/'demo-out/strawberry-picker.mp4'
 run(['-f','concat','-safe','0','-i',manifest,'-i',metadata,'-map_metadata','1','-map_chapters','1','-c','copy','-movflags','+faststart',final])
 d=duration(final);assert 180<=d<=300,d
 A.mkdir(exist_ok=True)
 gif(final,A/'strawberry-picker.gif',42,5_000_000)
 for n,slug,secs in [(3,'motion',20),(5,'clearance',16),(6,'fem',14)]:gif(clips[n-1],A/f'strawberry-picker-{n:02d}-{slug}.gif',secs,3_000_000)
 # Stay inside the readable holds, beyond the boundary fades; inspect four
 # evenly spaced chapter moments as well as the earlier middle sample.
 q=O/'qc';q.mkdir(exist_ok=True)
 for c in report:
  for label,t in [('start',1.5),('one-third',c['duration_seconds']/3),('two-thirds',2*c['duration_seconds']/3),('middle',c['duration_seconds']/2),('end',c['duration_seconds']-1.5)]:
   run(['-ss',c['start_seconds']+t,'-i',final,'-frames:v','1',q/f'{c["number"]:02d}-{label}.png'])
 for p in sorted(A.glob('strawberry-picker*.gif')):
  gd=duration(p)
  for i,t in enumerate([1,gd/2,gd-1]):
   run(['-ss',t,'-i',p,'-frames:v','1',q/f'{p.stem}-{i}.png'])
 gifs={p.name:p.stat().st_size for p in sorted(A.glob('strawberry-picker*.gif'))}
 data={'duration_seconds':d,'video_bytes':final.stat().st_size,'resolution':[1600,1000],'fps':10,'chapters':report,'gifs_bytes':gifs,'disclosure':'Scripted replay; real MCP tools on the companion FreeCAD fork; no language model during replay; waiting trimmed; saved parametric checkpoint regenerated; caption/readback panels restored in post, CAD pixels unchanged.'}
 (O/'media-report.json').write_text(json.dumps(data,indent=2)+'\n');print(json.dumps({'duration':d,'gifs':gifs}),flush=True)
if __name__=='__main__':main()
