import os, uuid, subprocess, asyncio, shutil
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, FileResponse, Response, JSONResponse
import secrets, base64
import edge_tts
app=FastAPI(title="ATK AI Documentary Studio")
ROOT=Path("/tmp/atk_jobs");ROOT.mkdir(exist_ok=True)
VOICE="my-MM-ThihaNeural"
@app.middleware("http")
async def auth(req:Request,next_call):
 if req.url.path=="/health":return await next_call(req)
 pw=os.getenv("ATK_PASSWORD","")
 if not pw:return JSONResponse({"detail":"Configure ATK_PASSWORD"},status_code=503)
 try:
  scheme,token=req.headers.get("authorization","").split(" ",1)
  user,got=base64.b64decode(token).decode().split(":",1)
 except Exception:scheme=user=got=""
 if scheme.lower()!="basic" or not secrets.compare_digest(user,"admin") or not secrets.compare_digest(got,pw):
  return Response(status_code=401,headers={"WWW-Authenticate":'Basic realm="ATK Documentary"'})
 return await next_call(req)
@app.get("/health")
def health():return {"status":"ok"}
HTML="""<!doctype html><html lang="my"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ATK AI Documentary Studio</title><style>body{font:16px system-ui;background:#0c1424;color:#edf4ff;margin:0}main{max-width:760px;margin:auto;padding:22px}section{background:#1b2a42;padding:20px;border-radius:14px;margin:18px 0}input,textarea,button{box-sizing:border-box;width:100%;margin:8px 0;padding:12px;border-radius:8px;border:1px solid #63738c;background:#101c30;color:white}button{background:#2669dd;cursor:pointer}a{color:#9bc7ff}small{color:#a9b9ce}</style><main><h1>ATK AI Documentary Studio</h1><small>Online browser MVP · Myanmar male voice · 1080p MP4</small><section><h3>1. ဇာတ်ညွှန်း / Voice</h3><textarea id="script" rows="7" placeholder="မြန်မာ ဇာတ်ညွှန်း (စာကြောင်းတစ်ကြောင်း = subtitle တစ်ခု)"></textarea><button onclick="preview()">မြန်မာ အမျိုးသားအသံ Preview</button><audio id="audio" controls style="width:100%"></audio><label>ကိုယ်ပိုင် Voice ဖိုင် (optional)</label><input id="voice" type="file" accept="audio/*"></section><section><h3>2. Scene Video / BGM</h3><input id="videos" type="file" multiple accept="video/*"><label>BGM (optional)</label><input id="music" type="file" accept="audio/*"><small>အချိန်ညှိ Scene Editing ဖြစ်ပြီး AI semantic scene selection မဟုတ်သေးပါ။</small></section><section><h3>3. 1080p Export</h3><button onclick="render()">Render MP4 + SRT</button><p id="status">Ready</p><div id="links"></div></section></main><script>
async function preview(){let f=new FormData();f.append('script',document.querySelector('#script').value.slice(0,400));document.querySelector('#status').textContent='Voice generating...';try{let r=await fetch('/tts',{method:'POST',body:f});if(!r.ok)throw Error((await r.json()).detail);document.querySelector('#audio').src=URL.createObjectURL(await r.blob());document.querySelector('#status').textContent='Preview ready'}catch(e){document.querySelector('#status').textContent=e.message}}
async function render(){let f=new FormData();let videos=document.querySelector('#videos').files;if(!videos.length)return alert('Video ထည့်ပါ');for(let v of videos)f.append('videos',v);let voice=document.querySelector('#voice').files[0],music=document.querySelector('#music').files[0];if(voice)f.append('voice',voice);if(music)f.append('music',music);f.append('script',document.querySelector('#script').value);document.querySelector('#status').textContent='Rendering...';try{let r=await fetch('/render',{method:'POST',body:f});let d=await r.json();if(!r.ok)throw Error(d.detail);document.querySelector('#links').innerHTML='<a href="'+d.mp4+'">MP4 Download</a> | <a href="'+d.srt+'">SRT Download</a>';document.querySelector('#status').textContent='Done'}catch(e){document.querySelector('#status').textContent='Error: '+e.message}}
</script></html>"""
@app.get("/",response_class=HTMLResponse)
def home():return HTML
def run(cmd):
 p=subprocess.run(cmd,capture_output=True,text=True,timeout=300)
 if p.returncode:raise HTTPException(500,"FFmpeg error: "+p.stderr[-400:])
def duration(p):
 q=subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(p)],capture_output=True,text=True)
 if q.returncode:raise HTTPException(400,"Invalid media")
 return float(q.stdout.strip())
async def tts(text,path):
 if not text.strip():raise HTTPException(400,"Myanmar script required")
 if len(text)>10000:raise HTTPException(400,"Script too long for trial")
 try:await edge_tts.Communicate(text,VOICE).save(str(path))
 except Exception as e:raise HTTPException(502,"TTS unavailable: "+str(e)[:120])
@app.post("/tts")
async def voice_preview(script:str=Form(...)):
 folder=ROOT/uuid.uuid4().hex;folder.mkdir()
 p=folder/"voice.mp3";await tts(script[:400],p)
 return FileResponse(p,media_type="audio/mpeg")
def stamp(t):
 ms=round(t*1000);h,ms=divmod(ms,3600000);m,ms=divmod(ms,60000);s,ms=divmod(ms,1000)
 return f"{h:02}:{m:02}:{s:02},{ms:03}"
@app.post("/render")
async def render(videos:list[UploadFile]=File(...),script:str=Form(""),voice:UploadFile|None=File(None),music:UploadFile|None=File(None)):
 if len(videos)>12:raise HTTPException(400,"Trial supports 12 scenes max")
 folder=ROOT/uuid.uuid4().hex;folder.mkdir()
 async def save(upload,path):
  size=0
  with path.open("wb") as dest:
   while data:=await upload.read(1024*1024):
    size+=len(data)
    if size>70*1024*1024:raise HTTPException(413,"Each file max 70MB")
    dest.write(data)
  return path
 clips=[await save(v,folder/f"clip{i}{Path(v.filename or '.mp4').suffix}") for i,v in enumerate(videos)]
 if voice:audio=await save(voice,folder/"voice.mp3")
 else:
  audio=folder/"voice.mp3";await tts(script,audio)
 total=min(duration(audio),120)
 if total<0.5:raise HTTPException(400,"Audio too short")
 each=total/len(clips)
 rendered=[]
 for i,clip in enumerate(clips):
  out=folder/f"scene{i}.mp4"
  run(["ffmpeg","-y","-stream_loop","-1","-i",str(clip),"-t",str(each),"-vf","scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1","-r","24","-an","-c:v","libx264","-preset","ultrafast","-crf","28",str(out)])
  rendered.append(out)
 listing=folder/"concat.txt";listing.write_text("".join("file '"+p.name+"'\n" for p in rendered))
 silent=folder/"silent.mp4"
 run(["ffmpeg","-y","-f","concat","-safe","0","-i",str(listing),"-c","copy",str(silent)])
 srt=folder/"captions.srt";lines=[x.strip() for x in script.splitlines() if x.strip()]
 if not lines:lines=[" "]
 step=total/len(lines)
 srt.write_text("".join(f"{i+1}\n{stamp(i*step)} --> {stamp(min(total,(i+1)*step))}\n{line}\n\n" for i,line in enumerate(lines)),encoding="utf-8")
 final=folder/"documentary.mp4"
 if music:
  bg=await save(music,folder/"bg.mp3")
  run(["ffmpeg","-y","-i",str(silent),"-i",str(audio),"-stream_loop","-1","-i",str(bg),"-filter_complex","[1:a]volume=1[a];[2:a]volume=0.08[b];[a][b]amix=inputs=2:duration=first[m]","-map","0:v","-map","[m]","-t",str(total),"-c:v","copy","-c:a","aac",str(final)])
 else:run(["ffmpeg","-y","-i",str(silent),"-i",str(audio),"-t",str(total),"-c:v","copy","-c:a","aac",str(final)])
 key=folder.name
 return {"mp4":f"/download/{key}/documentary.mp4","srt":f"/download/{key}/captions.srt"}
@app.get("/download/{job}/{filename}")
def download(job:str,filename:str):
 if not (len(job)==32 and all(c in "0123456789abcdef" for c in job)) or filename not in ("documentary.mp4","captions.srt"):raise HTTPException(404)
 p=ROOT/job/filename
 if not p.exists():raise HTTPException(404)
 return FileResponse(p,filename=filename)
