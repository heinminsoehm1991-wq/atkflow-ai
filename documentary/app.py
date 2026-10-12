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
HTML="""<!doctype html><html lang="my"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ATK AI Documentary Studio</title><style>body{font:16px system-ui;background:#0c1424;color:#edf4ff;margin:0}main{max-width:760px;margin:auto;padding:22px}section{background:#1b2a42;padding:20px;border-radius:14px;margin:18px 0}input,textarea,button{box-sizing:border-box;width:100%;margin:8px 0;padding:12px;border-radius:8px;border:1px solid #63738c;background:#101c30;color:white}button{background:#2669dd;cursor:pointer}a{color:#9bc7ff}small{color:#a9b9ce}</style><main><h1>ATK AI Documentary Studio</h1><small>Online browser MVP · Myanmar male voice · 1080p MP4</small><section><h3>0. YouTube Reference</h3><small>မူရင်း YouTube Video ကို Download မလုပ်ပါ။ ခေါင်းစဉ်နဲ့ Channel အချက်အလက်ကိုသာ ဖတ်ပြီး ကိုယ်ပိုင် Documentary စီစဉ်ရန် အသုံးပြုပါ။</small><input id="youtube" type="url" placeholder="https://www.youtube.com/watch?v=..."><button onclick="reference()">YouTube Link စစ်ဆေးရန်</button><p id="refstatus"></p><label>ကိုယ်ပိုင် မှတ်စု / အသုံးပြုခွင့်ရှိသော Transcript</label><textarea id="notes" rows="4" placeholder="လေ့လာထားတဲ့ အချက်အလက်တွေကို ဒီမှာရေးပါ"></textarea><button onclick="outline()">Gemini AI ဖြင့် မြန်မာ Documentary Script ထုတ်ရန်</button><small>Gemini API ဖြင့် Link သို့မဟုတ် မှတ်စုကို လေ့လာပြီး မူရင်း မြန်မာဇာတ်ညွှန်း ဖန်တီးပါမည်။ AI အချက်အလက်များကို ပြန်လည်စစ်ဆေးပါ။</small></section><section><h3>1. ဇာတ်ညွှန်း / Voice</h3><textarea id="script" rows="7" placeholder="မြန်မာ ဇာတ်ညွှန်း (စာကြောင်းတစ်ကြောင်း = subtitle တစ်ခု)"></textarea><button onclick="preview()">မြန်မာ အမျိုးသားအသံ Preview</button><audio id="audio" controls style="width:100%"></audio><label>ကိုယ်ပိုင် Voice ဖိုင် (optional)</label><input id="voice" type="file" accept="audio/*"></section><section><h3>2. Scene Video / BGM</h3><input id="videos" type="file" multiple accept="video/*"><label>BGM (optional)</label><input id="music" type="file" accept="audio/*"><small>အချိန်ညှိ Scene Editing ဖြစ်ပြီး AI semantic scene selection မဟုတ်သေးပါ။</small></section><section><h3>3. 1080p Export</h3><button onclick="render()">Render MP4 + SRT</button><p id="status">Ready</p><div id="links"></div></section></main><script>
async function reference(){const el=document.querySelector('#refstatus');el.textContent='Checking public metadata...';try{const r=await fetch('/youtube-reference',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:document.querySelector('#youtube').value})});const d=await r.json();if(!r.ok)throw Error(d.detail);el.textContent='Title: '+d.title+' | Channel: '+d.author+' | Video footage မယူထားပါ';}catch(e){el.textContent='Error: '+e.message;}}
async function outline(){const notes=document.querySelector('#notes').value.trim(),url=document.querySelector('#youtube').value.trim(),el=document.querySelector('#status'),btn=document.querySelector('button[onclick="outline()"]');if(!notes&&!url){alert('YouTube Link သို့မဟုတ် မှတ်စု ထည့်ပါ');return}btn.disabled=true;el.textContent='Gemini AI က မြန်မာဇာတ်ညွှန်း ရေးနေပါသည်...';try{const r=await fetch('/generate-script',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url,notes})});const d=await r.json();if(!r.ok)throw Error(d.detail||'Generation failed');document.querySelector('#script').value=d.script;el.textContent='Gemini Script ready — အချက်အလက်နှင့် မူပိုင်ခွင့်ကို စစ်ဆေးပါ';document.querySelector('#script').scrollIntoView({behavior:'smooth',block:'center'})}catch(e){el.textContent='Error: '+e.message}finally{btn.disabled=false}}
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

# Public YouTube metadata only; no video download or transcript scraping.
from pydantic import BaseModel
from urllib.parse import urlparse,parse_qs
from urllib.request import Request as URLRequest, urlopen
import json,re
class YouTubeReference(BaseModel):
 url:str
@app.post("/youtube-reference")
def youtube_reference(item:YouTubeReference):
 if len(item.url)>500:raise HTTPException(400,"URL too long")
 u=urlparse(item.url.strip())
 host=(u.hostname or "").lower()
 if u.scheme!="https" or host not in ("youtube.com","www.youtube.com","m.youtube.com","youtu.be"):
  raise HTTPException(400,"HTTPS YouTube link only")
 if host=="youtu.be":vid=u.path.strip("/").split("/")[0]
 elif u.path=="/watch":vid=parse_qs(u.query).get("v",[""])[0]
 elif u.path.startswith(("/shorts/","/live/","/embed/")):vid=u.path.split("/")[2]
 else:raise HTTPException(400,"Unsupported YouTube URL format")
 if not re.fullmatch(r"[A-Za-z0-9_-]{11}",vid):raise HTTPException(400,"Invalid video ID")
 safe="https://www.youtube.com/watch?v="+vid
 try:
  req=URLRequest("https://www.youtube.com/oembed?url="+safe+"&format=json",headers={"User-Agent":"ATKDocumentaryStudio/1.0"})
  with urlopen(req,timeout=8) as resp:data=json.loads(resp.read(12000))
 except Exception:raise HTTPException(502,"YouTube metadata unavailable. Paste notes manually.")
 return {"video_url":safe,"title":str(data.get("title",""))[:300],"author":str(data.get("author_name",""))[:200],"downloaded":False}

class ScriptRequest(BaseModel):
 url:str=""
 notes:str=""
@app.post("/generate-script")
def generate_script(item:ScriptRequest):
 key=os.getenv("GEMINI_API_KEY","").strip()
 if not key:raise HTTPException(503,"GEMINI_API_KEY ကို Render Environment မှာ ထည့်ပါ")
 if len(item.notes)>25000 or len(item.url)>500:raise HTTPException(400,"Input too long")
 url=item.url.strip()
 if not url and not item.notes.strip():raise HTTPException(400,"YouTube Link သို့မဟုတ် မှတ်စု လိုအပ်ပါသည်")
 parts=[]
 if url:
  u=urlparse(url)
  host=(u.hostname or "").lower()
  if u.scheme!="https" or host not in ("youtube.com","www.youtube.com","m.youtube.com","youtu.be"):
   raise HTTPException(400,"HTTPS YouTube link only")
  vid=u.path.strip("/").split("/")[0] if host=="youtu.be" else (parse_qs(u.query).get("v",[""])[0] if u.path=="/watch" else (u.path.split("/")[2] if u.path.startswith(("/shorts/","/live/","/embed/")) and len(u.path.split("/"))>2 else ""))
  if not re.fullmatch(r"[A-Za-z0-9_-]{11}",vid):raise HTTPException(400,"Invalid YouTube video ID")
  parts.append({"file_data":{"file_uri":"https://www.youtube.com/watch?v="+vid,"mime_type":"video/mp4"}})
 prompt=("Write an ORIGINAL Burmese-language documentary narration script using only verifiable information from the provided video and/or user's notes. "
 "Do not copy or closely paraphrase copyrighted narration. Do not pretend to have watched the video if it cannot be accessed. "
 "If insufficient information, say what is missing instead of fabricating facts. "
 "Use natural Myanmar male narrator style, compelling introduction, logical scene progression and conclusion. "
 "Output ONLY Burmese narration, one short subtitle-friendly sentence per line. "
 "Avoid unverified claims and indicate uncertainty when needed. "
 "User notes:\n"+item.notes.strip())
 parts.append({"text":prompt})
 model=os.getenv("GEMINI_MODEL","gemini-2.5-flash")
 payload={"contents":[{"role":"user","parts":parts}],"generationConfig":{"temperature":0.45,"maxOutputTokens":4096}}
 try:
  req=URLRequest("https://generativelanguage.googleapis.com/v1beta/models/"+model+":generateContent",data=json.dumps(payload).encode(),headers={"Content-Type":"application/json","x-goog-api-key":key},method="POST")
  with urlopen(req,timeout=120) as response:data=json.loads(response.read(500000))
  output="\n".join(p.get("text","") for c in data.get("candidates",[]) for p in c.get("content",{}).get("parts",[]) if p.get("text"))
  if not output.strip():raise HTTPException(502,"Gemini returned no script. Try adding notes.")
  return {"script":output.strip()}
 except HTTPException:raise
 except Exception as exc:
  from urllib.error import HTTPError
  if isinstance(exc,HTTPError):
   code=exc.code
   if url and not item.notes.strip() and code in (400,403,404,422):
    raise HTTPException(422,"Gemini က ဒီ YouTube Video ကို ဖတ်မရပါ။ ကိုယ်ပိုင် မှတ်စု/Transcript ထည့်ပြီး ပြန်စမ်းပါ")
   raise HTTPException(502,"Gemini API request failed (HTTP "+str(code)+"). Check API key, quota and video access.")
  raise HTTPException(502,"Gemini service unavailable. Try again later.")
