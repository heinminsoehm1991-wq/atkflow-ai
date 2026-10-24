"""Account-private, leased native FFmpeg renderer for ATK Recap."""
import concurrent.futures, hashlib, json, math, os, re, signal, subprocess, tarfile, tempfile, threading, time, urllib.request, urllib.error, wave
from pathlib import Path

try:RENDER_CONCURRENCY=max(1,min(8,int(os.environ.get('RENDER_CONCURRENCY','1'))))
except ValueError:RENDER_CONCURRENCY=1
SLOT=threading.BoundedSemaphore(RENDER_CONCURRENCY)
LOCK=threading.Lock()
ACTIVE={}
STOP=threading.Event()
ALLOWED={'www.atkmoverecap.app','atkmoverecap.app'}

class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*args): return None
OPENER=urllib.request.build_opener(NoRedirect())

def request(base,token,path,body=None,method=None):
 from urllib.parse import urlsplit
 headers={'Authorization':'Bearer '+token,'Content-Type':'application/json' if body is None or body.startswith(b'{') else 'application/octet-stream'}
 service_token=os.environ.get('ATK_SITE_SERVICE_TOKEN','')
 if service_token and urlsplit(base).scheme=='https' and urlsplit(base).hostname in ALLOWED:headers['OAI-Sites-Authorization']='Bearer '+service_token
 req=urllib.request.Request(base+'/'+path,data=body,method=method or ('POST' if body is not None else 'GET'),headers=headers)
 return OPENER.open(req,timeout=60)
def api(base,token,path,data=None):
 with request(base,token,path,None if data is None else json.dumps(data).encode()) as r:return json.load(r)
def download(base,token,path,target):
 for attempt in range(3):
  try:
   with request(base,token,path) as r,open(target,'wb') as out:
    while block:=r.read(1024*1024):out.write(block)
   return
  except Exception:
   if attempt==2:raise
   time.sleep(1)
def probe(path):return json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)],timeout=30))
def number(value,default,low,high):
 try:n=float(value)
 except (ValueError,TypeError):n=default
 if not math.isfinite(n):n=default
 return max(low,min(high,n))
def video_filters(meta,settings,source):
 w,h=meta['width'],meta['height'];sw,sh=source['width'],source['height'];c=settings.get('cropRect') or {'x':0,'y':0,'w':100,'h':100}
 x=int(sw*number(c.get('x'),0,0,99)/100);y=int(sh*number(c.get('y'),0,0,99)/100);cw=max(2,min(sw-x,int(sw*number(c.get('w'),100,.1,100)/100)));ch=max(2,min(sh-y,int(sh*number(c.get('h'),100,.1,100)/100)))
 pad=settings.get('fit')=='Pad (blur bg)';scale=(min(w/cw,h/ch) if pad else max(w/cw,h/ch))*number(settings.get('zoom'),100,10,300)/100
 if pad and settings.get('ratio')!='Original':scale*=number(settings.get('pictureSize'),1,.1,3)
 dw=max(2,round(cw*scale/2)*2);dh=max(2,round(ch*scale/2)*2)
 dx=(w-dw)/2+number(settings.get('panX'),0,-100,100)*w/100;dy=(h-dh)/2+number(settings.get('panY'),0,-100,100)*h/100
 if pad and settings.get('ratio')!='Original':dx+=(w-dw)/2*number(settings.get('pictureX'),0,-100,100)/100;dy+=(h-dh)/2*number(settings.get('pictureY'),0,-100,100)/100
 mirror=',hflip' if settings.get('mirror') else ''
 bright=number(settings.get('videoBrightness'),100,0,200)/100;contrast=number(settings.get('videoContrast'),100,0,200)/100;sat=number(settings.get('videoColour'),100,0,200)/100
 colour=f",format=rgb24,lutrgb=r='clip((val*{bright}-127.5)*{contrast}+127.5,0,255)':g='clip((val*{bright}-127.5)*{contrast}+127.5,0,255)':b='clip((val*{bright}-127.5)*{contrast}+127.5,0,255)'"
 if abs(sat-1)>.0001:
  weights=[.213,.715,.072];matrix={}
  for i,a in enumerate('rgb'):
   for j,b in enumerate('rgb'):matrix[a+b]=(1-sat)*weights[j]+(sat if i==j else 0)
  colour+=',colorchannelmixer='+':'.join(f'{k}={v}' for k,v in matrix.items())
 if bright==contrast==sat==1:colour=''
 d=meta['seconds'];filters=[f'[0:v]fps=30,tpad=stop_mode=clone:stop_duration=1{mirror}{colour},split=2[original][back]']
 filters.append(f'[original]crop={cw}:{ch}:{x}:{y},scale={dw}:{dh}[foreground]')
 if pad:
  bw=math.ceil(max(w/sw,h/sh)*sw*1.12/2)*2;bh=math.ceil(max(w/sw,h/sh)*sh*1.12/2)*2
  filters.append(f'[back]scale={bw}:{bh},crop={w}:{h},boxblur={max(1,round(w/1080*18.75))}:1[background]')
 else:filters.append('[back]nullsink');filters.append(f'color=c=0x12131b:s={w}x{h}:r=30:d={d+1}[background]')
 filters.append(f'[background][foreground]overlay=x={dx}:y={dy}:shortest=1[composite0]')
 blurs=list(meta.get('blurs') or [])
 if settings.get('fullband'):blurs.append({'x':0,'y':100-number(settings.get('bandBottom'),0,0,100)-number(settings.get('bandHeight'),14,1,100),'w':100,'h':number(settings.get('bandHeight'),14,1,100),'strength':22})
 current='composite0'
 for i,b in enumerate(blurs):
  bx=max(0,min(w-2,int(number(b.get('x'),0,0,100)*w/100)));by=max(0,min(h-2,int(number(b.get('y'),0,0,100)*h/100)));bw=max(2,min(w-bx,int(number(b.get('w'),1,.1,100)*w/100)));bh=max(2,min(h-by,int(number(b.get('h'),1,.1,100)*h/100)))
  radius=max(0,min(int(number(b.get('strength'),22,1,40)*w/1080),min(bw,bh)//2-1))
  filters.extend([f'[{current}]split=2[blurbase{i}][blurcrop{i}]',f'[blurcrop{i}]crop={bw}:{bh}:{bx}:{by},boxblur={radius}:1[blurred{i}]',f'[blurbase{i}][blurred{i}]overlay={bx}:{by}[composite{i+1}]']);current=f'composite{i+1}'
 filters.append(f'[{current}][2:v]overlay=0:0:eof_action=repeat:format=auto,format=yuv420p[output]')
 return ';'.join(filters)
def pcm(path):
 with wave.open(str(path),'rb') as wav:
  if wav.getnchannels()!=1 or wav.getsampwidth()!=2:raise ValueError('Unsupported retained voice format')
  import array
  samples=array.array('h',wav.readframes(wav.getnframes()));return samples,wav.getframerate()
def rms(samples,rate,start,end):
 a=max(0,int(start*rate));b=min(len(samples),math.ceil(end*rate));return math.sqrt(sum(x*x for x in samples[a:b])/(b-a))/32768 if b>a else 0

def verify_audio(folder,voice,target,seconds,cues):
 # Decode the complete exported AAC and compare speech-energy windows to retained PCM.
 decoded=folder/'checked.wav';subprocess.run(['ffmpeg','-v','error','-xerror','-i',str(target),'-vn','-ac','1','-ar','8000','-c:a','pcm_s16le','-y',str(decoded)],check=True,timeout=max(120,min(900,seconds)))
 reference=folder/'reference-8k.wav';subprocess.run(['ffmpeg','-v','error','-i',str(voice),'-vn','-ac','1','-ar','8000','-c:a','pcm_s16le','-y',str(reference)],check=True,timeout=max(120,min(900,seconds)))
 ref,rr=pcm(reference);audio,ar=pcm(decoded);active=0
 for n in range(math.ceil(seconds/.2)):
  t=n*.2;end=min(seconds,t+.2);energy=rms(ref,rr,t,end)
  if energy<.005:continue
  active+=1
  if rms(audio,ar,max(0,t-.04),min(seconds,end+.04))<energy*.025:raise ValueError('Export audio contains missing speech')
 if not active:raise ValueError('Voice contains no audible speech')
 for cue in cues:
  if rms(ref,rr,cue['start'],cue['end'])>.0001 and rms(audio,ar,cue['start'],cue['end'])<.0001:raise ValueError('A voice line is missing')

def render_file(folder,manifest):
 job=manifest['job'];render=manifest['render'];settings=manifest['settings'];source=folder/'source.mp4';voice=folder/'voice.wav'
 digest=hashlib.sha256()
 with source.open('rb') as stream:
  while block:=stream.read(1024*1024):digest.update(block)
 if digest.hexdigest()!=job['fingerprint']:raise ValueError('Original video fingerprint does not match')
 info=probe(source);picture=next(s for s in info['streams'] if s['codec_type']=='video');seconds=float(info['format']['duration'])
 if abs(seconds-job['duration'])>.1:raise ValueError('Original video duration does not match the reservation')
 if settings.get('moving') and settings.get('water'):raise ValueError('Moving watermark requires browser rendering')
 expected=render['frames'];names={str(i)+'.png' for i in range(len(expected))}
 with tarfile.open(folder/'overlays.tar') as archive:
  members=archive.getmembers()
  if len(members)!=len(names) or {m.name for m in members}!=names or any(not m.isfile() or m.size>16*1024*1024 for m in members):raise ValueError('Invalid caption overlay package')
  for member in members:
   data=archive.extractfile(member).read()
   if data[:8]!=b'\x89PNG\r\n\x1a\n':raise ValueError('Invalid caption image')
   (folder/member.name).write_bytes(data)
 concat=folder/'overlays.txt';concat.write_text('ffconcat version 1.0\n'+''.join(f"file '{i}.png'\noption framerate 1000\nduration {frame['end']-frame['start']:.6f}\n" for i,frame in enumerate(expected))+f"file '{len(expected)-1}.png'\noption framerate 1000\n")
 render={**render,'seconds':seconds,'blurs':manifest.get('blurs',[])};filters=video_filters(render,settings,picture);target=folder/'final.mp4';frames=math.ceil(seconds*30)
 command=['ffmpeg','-v','error','-nostdin','-threads','1','-i',str(source),'-i',str(voice),'-f','concat','-safe','0','-i',str(concat),'-filter_complex_threads','1','-filter_complex',filters,'-map','[output]','-map','1:a:0','-af',f'apad,atrim=duration={seconds}','-c:v','libx264','-preset','veryfast','-crf','20','-threads','1','-r','30','-frames:v',str(frames),'-t',str(frames/30),'-c:a','aac','-movflags','+faststart','-y',str(target)]
 with open(folder/'ffmpeg.log','wb') as log:
  proc=subprocess.Popen(command,stdout=subprocess.DEVNULL,stderr=log);started=time.time()
  while proc.poll() is None:
   if STOP.wait(.5) or time.time()-started>max(1800,min(14400,seconds*2+600)):proc.terminate();proc.wait(timeout=15);raise RuntimeError('Renderer interrupted; saved inputs can resume')
  if proc.returncode:raise RuntimeError('Video encoding failed: '+(folder/'ffmpeg.log').read_text()[-300:])
 out=probe(target);v=next(s for s in out['streams'] if s['codec_type']=='video');a=next(s for s in out['streams'] if s['codec_type']=='audio')
 if int(v.get('nb_frames',0))!=frames or abs(float(v['duration'])-frames/30)>.05 or abs(float(a['duration'])-seconds)>.12:raise ValueError('Incomplete output duration')
 verify_audio(folder,voice,target,seconds,manifest['cues'])
 return target,{'lines':len(manifest['cues']),'duration':seconds,'frames':frames}

def run(payload, *, release_slot=True, raise_errors=False):
 base=payload['origin']+'/render-worker/'+payload['id'];token=payload['token'];done=threading.Event()
 def heartbeat():
  while not done.wait(30):
   try:api(base,token,'heartbeat',{})
   except Exception:pass
 thread=threading.Thread(target=heartbeat,daemon=True);thread.start()
 try:
  print('ATK_RENDER '+payload['id']+' phase=manifest',flush=True)
  manifest=api(base,token,'manifest')
  print('ATK_RENDER '+payload['id']+' phase=inputs',flush=True)
  with tempfile.TemporaryDirectory(prefix='atk-render-') as name:
   folder=Path(name)
   for kind,key,target in [('source','sourceParts','source.mp4'),('overlay','overlayParts','overlays.tar')]:
    with open(folder/target,'wb') as combined:
     for i in range(manifest['job'][key]):
      print('ATK_RENDER '+payload['id']+' downloading='+kind+'/'+str(i),flush=True)
      part=folder/'part.tmp';download(base,token,kind+'/'+str(i),part)
      print('ATK_RENDER '+payload['id']+' received='+str(part.stat().st_size),flush=True)
      with open(part,'rb') as f:
       while block:=f.read(1024*1024):combined.write(block)
      part.unlink()
   print('ATK_RENDER '+payload['id']+' downloading=voice',flush=True)
   download(base,token,'voice',folder/'voice.wav')
   print('ATK_RENDER '+payload['id']+' phase=encoding',flush=True)
   target,quality=render_file(folder,manifest)
   print('ATK_RENDER '+payload['id']+' phase=upload_result',flush=True)
   meta=api(base,token,'result/start',{'size':target.stat().st_size,'duration':quality['duration'],'name':'ATK-Recap-'+payload['id'][:8]+'.mp4'})
   with open(target,'rb') as f:
    for i in range(meta['parts']):
     data=f.read(meta['chunkSize'])
     for attempt in range(3):
      try:
       with request(base,token,'result/chunks/'+str(i),data,method='PUT') as response:response.read()
       break
      except Exception:
       if attempt==2:raise
       time.sleep(1)
   api(base,token,'result/commit',{})
   return quality
 except Exception as error:
  print('ATK_RENDER '+payload['id']+' failed='+type(error).__name__+' '+str(error)[:220],flush=True)
  if not STOP.is_set():
   try:api(base,token,'failed',{'error':str(error)[:220]})
   except Exception:pass
  if raise_errors:raise
 finally:
  done.set()
  with LOCK:ACTIVE.pop(payload['id'],None)
  if release_slot:SLOT.release()

def validate_payload(payload):
 from urllib.parse import urlsplit
 if not isinstance(payload,dict) or not re.fullmatch('[a-f0-9-]{36}',str(payload.get('id',''))) or not re.fullmatch('[a-f0-9]{64}',str(payload.get('token',''))):raise ValueError('Invalid render job')
 u=urlsplit(str(payload.get('origin','')))
 if u.scheme!='https' or u.hostname not in ALLOWED or u.path or u.query or u.fragment or u.username or u.port not in (None,443):raise ValueError('Invalid callback origin')

def accept(payload):
 from urllib.parse import urlsplit
 if not isinstance(payload,dict) or not re.fullmatch('[a-f0-9-]{36}',str(payload.get('id',''))) or not re.fullmatch('[a-f0-9]{64}',str(payload.get('token',''))):return 400,'Invalid render job'
 u=urlsplit(str(payload.get('origin','')))
 if u.scheme!='https' or u.hostname not in ALLOWED or u.path or u.query or u.fragment or u.username or u.port not in (None,443):return 400,'Invalid callback origin'
 with LOCK:
  if payload['id'] in ACTIVE:return 202,'Already rendering'
  if STOP.is_set() or not SLOT.acquire(False):return 503,'Renderer busy; queued job retained'
  ACTIVE[payload['id']]=True
 threading.Thread(target=run,args=(payload,),daemon=True).start();return 202,'Accepted'

def poll_loop():
 origin='https://www.atkmoverecap.app'
 reported=set()
 while not STOP.wait(8):
  with LOCK:busy=len(ACTIVE)>=RENDER_CONCURRENCY
  if busy:continue
  for token in [os.environ.get('ATK_RECAP_IMPORT_TOKEN',''),os.environ.get('ATK_IMPORT_TOKEN','')]:
   if not token:continue
   try:
    with request(origin+'/render-worker',token,'poll',b'{}') as response:response.read()
    if 'ready' not in reported:print('ATK_RENDER poll=ready',flush=True);reported.add('ready')
    break
   except urllib.error.HTTPError as error:
    code='http_'+str(error.code)
    if code not in reported:print('ATK_RENDER poll='+code+' server='+error.headers.get('server','')+' challenge='+error.headers.get('cf-mitigated','none')+' type='+error.headers.get('content-type',''),flush=True);reported.add(code)
    if error.code==403:
     print('ATK_RENDER poll=paused_forbidden; authorized site access requires review',flush=True)
     return
    if error.code!=401:break
   except Exception as error:
    code=type(error).__name__
    if code not in reported:print('ATK_RENDER poll='+code,flush=True);reported.add(code)
    break

def start():threading.Thread(target=poll_loop,daemon=True).start()
