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
def health():return {"status":"ok","gemini_configured":bool(os.getenv("GEMINI_API_KEY","").strip()),"voice":VOICE,"export":"ffmpeg"}
HTML="""<!doctype html><html lang="my"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ATK AI Documentary Studio</title><style>body{font:16px system-ui;background:#0c1424;color:#edf4ff;margin:0}main{max-width:760px;margin:auto;padding:22px}section{background:#1b2a42;padding:20px;border-radius:14px;margin:18px 0}input,textarea,button{box-sizing:border-box;width:100%;margin:8px 0;padding:12px;border-radius:8px;border:1px solid #63738c;background:#101c30;color:white}button{background:#2669dd;cursor:pointer}a{color:#9bc7ff}small{color:#a9b9ce}</style><main><h1>ATK AI Documentary Studio</h1><small>Online browser MVP · Myanmar male voice · 1080p MP4 · Long exports may exceed free hosting limits</small><section><h3>0. YouTube Reference</h3><small>မူရင်း YouTube Video ကို Download မလုပ်ပါ။ ခေါင်းစဉ်နဲ့ Channel အချက်အလက်ကိုသာ ဖတ်ပြီး ကိုယ်ပိုင် Documentary စီစဉ်ရန် အသုံးပြုပါ။</small><input id="youtube" type="url" placeholder="https://www.youtube.com/watch?v=..."><button onclick="reference()">YouTube Link စစ်ဆေးရန်</button><p id="refstatus"></p><label>ကိုယ်ပိုင် မှတ်စု / အသုံးပြုခွင့်ရှိသော Transcript</label><textarea id="notes" rows="4" placeholder="လေ့လာထားတဲ့ အချက်အလက်တွေကို ဒီမှာရေးပါ"></textarea><button onclick="outline()">Gemini AI ဖြင့် မြန်မာ Documentary Script ထုတ်ရန်</button><p id="scriptstatus" role="status"></p><small>Gemini API ဖြင့် Link သို့မဟုတ် မှတ်စုကို လေ့လာပြီး မူရင်း မြန်မာဇာတ်ညွှန်း ဖန်တီးပါမည်။ AI အချက်အလက်များကို ပြန်လည်စစ်ဆေးပါ။</small></section><section><h3>1. ဇာတ်ညွှန်း / Voice</h3><textarea id="script" rows="7" placeholder="မြန်မာ ဇာတ်ညွှန်း (စာကြောင်းတစ်ကြောင်း = subtitle တစ်ခု)"></textarea><button id="previewbtn" onclick="preview()">မြန်မာ အမျိုးသားအသံ Preview</button><p id="voicestatus" role="status"></p><audio id="audio" controls style="width:100%"></audio><label>ကိုယ်ပိုင် Voice ဖိုင် (optional)</label><input id="voice" type="file" accept="audio/*"></section><section><h3>2. Scene Video / BGM</h3><input id="videos" type="file" multiple accept="video/*"><label>BGM (optional)</label><input id="music" type="file" accept="audio/*"><small>အချိန်ညှိ Scene Editing ဖြစ်ပြီး AI semantic scene selection မဟုတ်သေးပါ။</small></section><section><h3>3. 1080p Export</h3><button onclick="render()">Render MP4 + SRT</button><p id="status">Ready</p><div id="links"></div></section></main><script>
async function reference(){const el=document.querySelector('#refstatus');el.textContent='Checking public metadata...';try{const r=await fetch('/youtube-reference',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:document.querySelector('#youtube').value})});const d=await r.json();if(!r.ok)throw Error(d.detail);el.textContent='Title: '+d.title+' | Channel: '+d.author+' | Video footage မယူထားပါ';}catch(e){el.textContent='Error: '+e.message;}}
async function outline(){const notes=document.querySelector('#notes').value.trim(),url=document.querySelector('#youtube').value.trim(),el=document.querySelector('#scriptstatus'),btn=document.querySelector('button[onclick="outline()"]');if(!notes&&!url){alert('YouTube Link သို့မဟုတ် မှတ်စု ထည့်ပါ');return}btn.disabled=true;el.textContent='Gemini AI က မြန်မာဇာတ်ညွှန်း ရေးနေပါသည်...';try{const r=await fetch('/generate-script',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url,notes})});const d=await r.json();if(!r.ok)throw Error(d.detail||'Generation failed');document.querySelector('#script').value=d.script;el.textContent=d.warning||'Gemini Script ready — အချက်အလက်နှင့် မူပိုင်ခွင့်ကို စစ်ဆေးပါ';document.querySelector('#script').scrollIntoView({behavior:'smooth',block:'center'})}catch(e){el.textContent='Error: '+e.message}finally{btn.disabled=false}}
async function preview(){const script=document.querySelector('#script').value.trim(),el=document.querySelector('#voicestatus'),btn=document.querySelector('#previewbtn');if(!script){el.textContent='မြန်မာ ဇာတ်ညွှန်း အရင်ထည့်ပါ';return}let f=new FormData();f.append('script',script.slice(0,400));btn.disabled=true;el.textContent='မြန်မာအသံ ထုတ်နေပါသည်...';try{let r=await fetch('/tts',{method:'POST',body:f});if(!r.ok){let d=await r.json().catch(()=>({}));throw Error(d.detail||'Voice generation failed')}let player=document.querySelector('#audio');if(player.dataset.objecturl)URL.revokeObjectURL(player.dataset.objecturl);player.dataset.objecturl=URL.createObjectURL(await r.blob());player.src=player.dataset.objecturl;el.textContent='အသံ Preview အဆင်သင့်ပါပြီ';await player.play().catch(()=>{})}catch(e){el.textContent='Voice Error: '+e.message}finally{btn.disabled=false}}
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
def split_tts_text(text,limit=2500):
 lines=[line.strip() for line in text.splitlines() if line.strip()]
 chunks=[];current=""
 for line in lines:
  while len(line)>limit:
   if current:chunks.append(current);current=""
   split=line.rfind(" ",0,limit)
   if split<limit//2:split=limit
   chunks.append(line[:split].strip());line=line[split:].strip()
  if len(current)+len(line)+1>limit and current:chunks.append(current);current=""
  current=(current+"\n"+line).strip()
 if current:chunks.append(current)
 return chunks

async def tts(text,path):
 if not text.strip():raise HTTPException(400,"Myanmar script required")
 if len(text)>120000:raise HTTPException(413,"Script exceeds 120000 characters")
 chunks=split_tts_text(text)
 if len(chunks)>60:raise HTTPException(413,"Too many voice chunks")
 pieces=[]
 try:
  for i,chunk in enumerate(chunks):
   piece=path.parent/f"tts_part_{i:03d}.mp3"
   await edge_tts.Communicate(chunk,VOICE).save(str(piece))
   pieces.append(piece)
  if len(pieces)==1:shutil.move(str(pieces[0]),str(path))
  else:
   concat=path.parent/"tts_concat.txt"
   concat.write_text("".join("file '"+p.name+"'\\n" for p in pieces),encoding="utf-8")
   run(["ffmpeg","-y","-f","concat","-safe","0","-i",str(concat),"-c:a","libmp3lame","-q:a","4",str(path)])
 except HTTPException:raise
 except Exception as e:raise HTTPException(502,"TTS unavailable: "+str(e)[:120])
 finally:
  for piece in pieces:piece.unlink(missing_ok=True)
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
 if not videos:raise HTTPException(400,"At least one video required")
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
 if voice:audio=await save(voice,folder/"voice"+(Path(voice.filename or ".mp3").suffix.lower() if Path(voice.filename or ".mp3").suffix.lower() in (".mp3",".wav",".m4a",".aac") else ".mp3"))
 else:
  audio=folder/"voice.mp3";await tts(script,audio)
 total=duration(audio)
 if total>3600:raise HTTPException(413,"Export currently limited to 60 minutes; use shorter narration or split the project")
 if total<0.5:raise HTTPException(400,"Audio too short")
 if not clips:raise HTTPException(400,"At least one video required")
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

def youtube_video_id(url):
 u=urlparse(url)
 host=(u.hostname or "").lower()
 if u.scheme!="https" or host not in ("youtube.com","www.youtube.com","m.youtube.com","youtu.be"):
  raise HTTPException(400,"HTTPS YouTube link only")
 vid=u.path.strip("/").split("/")[0] if host=="youtu.be" else (parse_qs(u.query).get("v",[""])[0] if u.path=="/watch" else (u.path.split("/")[2] if u.path.startswith(("/shorts/","/live/","/embed/")) and len(u.path.split("/"))>2 else ""))
 if not re.fullmatch(r"[A-Za-z0-9_-]{11}",vid):raise HTTPException(400,"Invalid YouTube video ID")
 return vid

def video_metadata(vid):
 safe="https://www.youtube.com/watch?v="+vid
 try:
  req=URLRequest("https://www.youtube.com/oembed?url="+safe+"&format=json",headers={"User-Agent":"ATKDocumentaryStudio/1.0"})
  with urlopen(req,timeout=8) as resp:
   data=json.loads(resp.read(12000))
  return {"title":str(data.get("title",""))[:300],"channel":str(data.get("author_name",""))[:200]}
 except Exception:
  return {"title":"","channel":""}

def gemini_call(key,model,parts):
 payload={"contents":[{"role":"user","parts":parts}],"generationConfig":{"temperature":0.45,"maxOutputTokens":4096}}
 req=URLRequest("https://generativelanguage.googleapis.com/v1beta/models/"+model+":generateContent",data=json.dumps(payload).encode(),headers={"Content-Type":"application/json","x-goog-api-key":key},method="POST")
 with urlopen(req,timeout=120) as response:data=json.loads(response.read(500000))
 output="\n".join(p.get("text","") for c in data.get("candidates",[]) for p in c.get("content",{}).get("parts",[]) if p.get("text"))
 if not output.strip():raise HTTPException(502,"Gemini returned no script. Try adding notes.")
 return output.strip()

@app.post("/generate-script")
def generate_script(item:ScriptRequest):
 key=os.getenv("GEMINI_API_KEY","").strip()
 if not key:raise HTTPException(503,"GEMINI_API_KEY ကို Render Environment မှာ ထည့်ပါ")
 if len(item.notes)>25000 or len(item.url)>500:raise HTTPException(400,"Input too long")
 url=item.url.strip()
 notes=item.notes.strip()
 if not url and not notes:raise HTTPException(400,"YouTube Link သို့မဟုတ် မှတ်စု လိုအပ်ပါသည်")
 vid=youtube_video_id(url) if url else ""
 model=os.getenv("GEMINI_MODEL","gemini-2.5-flash")
 prompt=("Write an ORIGINAL Burmese-language documentary narration script. Do not copy copyrighted narration. "
 "Do not invent facts, locations, events or footage details. Use natural Myanmar male documentary narrator style. "
 "Output ONLY Burmese narration, one short subtitle-friendly sentence per line. "
 "If there is insufficient evidence for a detailed documentary, make a short introduction and clearly state what additional research is needed. "
 "User notes:\n"+notes)
 if vid:
  video_part={"file_data":{"file_uri":"https://www.youtube.com/watch?v="+vid,"mime_type":"video/mp4"}}
  try:
   script=gemini_call(key,model,[video_part,{"text":prompt+"\nAnalyze the supplied YouTube video only if it is accessible."}])
   return {"script":script,"source":"video"}
  except HTTPException as exc:
   if exc.status_code not in (400,403,404,422,502):raise
  except Exception as exc:
   from urllib.error import HTTPError
   if not isinstance(exc,HTTPError) or exc.code not in (400,403,404,422):
    if isinstance(exc,HTTPError):
     raise HTTPException(429 if exc.code==429 else 502,"Gemini API request failed (HTTP "+str(exc.code)+"). Check API key and quota.")
    raise HTTPException(502,"Gemini service unavailable. Try again later.")
  metadata=video_metadata(vid)
  if not metadata["title"] and not notes:
   raise HTTPException(422,"Gemini က Video ကို မဖတ်နိုင်ပါ။ YouTube metadata လည်း မရပါ။ မှတ်စု/Transcript ထည့်ပြီး ပြန်စမ်းပါ")
  context=("YouTube title: "+metadata["title"]+"\nChannel: "+metadata["channel"]+"\n" if metadata["title"] else "")
  fallback_prompt=(prompt+"\n"+context+
   "\nIMPORTANT: The YouTube VIDEO CONTENT WAS NOT ACCESSIBLE. The title/channel are only metadata, NOT evidence of specific scenes or facts. "
   "Do not claim to have watched the video. Produce only an original introductory script grounded in supplied notes and broadly established facts; avoid specific unsupported claims.")
  try:
   script=gemini_call(key,model,[{"text":fallback_prompt}])
   return {"script":script,"source":"metadata_and_notes","warning":"YouTube Video ကို တိုက်ရိုက် မဖတ်နိုင်ခဲ့ပါ။ ခေါင်းစဉ်နှင့် မှတ်စုကိုသာ အခြေခံထားသောကြောင့် အချက်အလက်များ ပြန်စစ်ပါ။"}
  except HTTPException:raise
  except Exception as exc:
   from urllib.error import HTTPError
   if isinstance(exc,HTTPError):
    raise HTTPException(429 if exc.code==429 else 502,"Gemini API request failed (HTTP "+str(exc.code)+"). Check API key, model and quota.")
   raise HTTPException(502,"Gemini service unavailable. Try again later.")
 try:
  return {"script":gemini_call(key,model,[{"text":prompt}]),"source":"notes"}
 except HTTPException:raise
 except Exception as exc:
  from urllib.error import HTTPError
  if isinstance(exc,HTTPError):raise HTTPException(429 if exc.code==429 else 502,"Gemini API request failed (HTTP "+str(exc.code)+"). Check API key and quota.")
  raise HTTPException(502,"Gemini service unavailable. Try again later.")
