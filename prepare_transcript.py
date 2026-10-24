"""Stream a retained original to disk; extract speech without browser/WASM memory."""
import hashlib,json,threading,time,subprocess,tempfile,urllib.request
from pathlib import Path
import render_jobs
_LOCK=threading.Lock();_ACTIVE=set();_SLOT=threading.BoundedSemaphore(1)
def accept(payload):
 try:
  render_jobs.validate_payload(payload)
  if not isinstance(payload.get('key'),str) or not 8<=len(payload['key'])<=250:return 400,'Missing transcription connection'
 except Exception:return 400,'Invalid preparation job'
 with _LOCK:
  if payload['id'] in _ACTIVE:return 202,'Already preparing'
  if not _SLOT.acquire(blocking=False):return 503,'Preparation slots are busy'
  _ACTIVE.add(payload['id'])
 threading.Thread(target=run,args=(payload,),daemon=True).start();return 202,'Accepted'
def upstream(path,key,data=None,content_type='application/json'):
 req=urllib.request.Request('https://api.assemblyai.com/v2/'+path,data=data,headers={'authorization':key,'content-type':content_type})
 with urllib.request.urlopen(req,timeout=120) as response:return json.load(response)
def run(payload):
 base=payload['origin']+'/prepare-worker/'+payload['id'];token=payload['token']
 try:
  meta=render_jobs.api(base,token,'manifest')
  if not 0<float(meta['duration'])<=5400.05:raise ValueError('Video exceeds 90 minutes')
  with tempfile.TemporaryDirectory(prefix='atk-transcript-') as name:
   folder=Path(name);source=folder/'source.mp4';digest=hashlib.sha256()
   with source.open('wb') as combined:
    for i in range(meta['parts']):
     part=folder/'part';render_jobs.download(base,token,'source/'+str(i),part)
     with part.open('rb') as stream:
      while block:=stream.read(1024*1024):digest.update(block);combined.write(block)
     part.unlink()
   if digest.hexdigest()!=meta['fingerprint']:raise ValueError('Original fingerprint mismatch')
   actual=float(render_jobs.probe(source)['format']['duration'])
   if abs(actual-float(meta['duration']))>.2:raise ValueError('Original duration mismatch')
   audio=folder/'speech.mp3'
   subprocess.run(['ffmpeg','-v','error','-nostdin','-i',str(source),'-vn','-ac','1','-ar','16000','-c:a','libmp3lame','-b:a','32k','-y',str(audio)],check=True,timeout=7200)
   if audio.stat().st_size>24*1024*1024:raise ValueError('Prepared speech exceeds limit')
   # At most 22 MB for 90 minutes; original video is never buffered in memory.
   uploaded=upstream('upload',payload['key'],audio.read_bytes(),'application/octet-stream')
   job=upstream('transcript',payload['key'],json.dumps({'audio_url':uploaded['upload_url'],'language_detection':True,'speaker_labels':True,'speech_models':['universal-3-5-pro','universal-2']}).encode())
   started=time.monotonic()
   while True:
    result=upstream('transcript/'+job['id'],payload['key'])
    if result['status']=='error':raise ValueError('Transcription provider could not complete the job')
    if result['status']=='completed':
     words=[{**w,'speaker':u['speaker']} for u in result.get('utterances',[]) for w in u.get('words',[])] or result.get('words',[])
     data={'status':'completed','words':words,'language':result.get('language_code','zh'),'model':result.get('speech_model_used','')};break
    if time.monotonic()-started>7200:raise TimeoutError('Transcription remains pending')
    time.sleep(5)
   with render_jobs.request(base,token,'result',json.dumps(data).encode(),method='PUT') as response:response.read()
 except Exception as error:
  # Never include provider keys, URLs or upstream exception text in user-visible errors.
  try:
   with render_jobs.request(base,token,'result',json.dumps({'status':'error','error':'Server speech preparation failed ('+type(error).__name__+'). Uploaded source is retained.'}).encode(),method='PUT') as response:response.read()
  except Exception:pass
 finally:
  payload.pop('key',None)
  with _LOCK:_ACTIVE.discard(payload['id'])
  _SLOT.release()
