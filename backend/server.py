"""Single-owner authenticated HTTP API for CPU/FFmpeg video jobs.

Run one replica/process with a persistent DATA_DIR. Provider credentials never go
to the frontend or the source repository. Background jobs are durably recorded;
interrupted jobs are marked failed rather than automatically charging again.
"""
import base64
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import logging
import math
import mimetypes
import os
from pathlib import Path
import re
import secrets
import shutil
import sqlite3
import threading
import time
from urllib.parse import parse_qs, urlsplit

from engine import (ProcessingError, FONTS, api, download_source, list_voices,
                    probe, render_video, speech, subtitles, transcribe,
                    validate_segments, validate_source, voice_track)

DATA = Path(os.environ.get('DATA_DIR', '/data')).resolve()
ADMIN = os.environ.get('ADMIN_TOKEN', '')
ORIGINS = set(x.strip() for x in os.environ.get('ALLOWED_ORIGINS', 'https://atk-english-studio.wint44954.chatgpt.site').split(',') if x.strip())
POOL = ThreadPoolExecutor(max_workers=1)
LOCK = threading.RLock()
CONFIG_FILE = DATA / 'provider-settings.json'
DATABASE = DATA / 'jobs.sqlite3'
DEFAULT_COLORS = {'brightness': 100, 'contrast': 100, 'saturation': 100, 'hue': 0}
MAX_BODY = 4 * 1024 * 1024

def initialize():
    DATA.mkdir(parents=True, exist_ok=True)
    os.chmod(DATA, 0o700)
    with closing(sqlite3.connect(DATABASE)) as db:
        db.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, request_id TEXT UNIQUE NOT NULL, request_hash TEXT NOT NULL, payload TEXT NOT NULL, status TEXT NOT NULL, stage TEXT NOT NULL, progress INTEGER NOT NULL, message TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL)')
        db.execute("UPDATE jobs SET status='failed', message='Server restarted while processing. Review partial outputs before starting a new job.', updated=? WHERE status IN ('queued','running')", (time.time(),))
        db.commit()
    os.chmod(DATABASE, 0o600)

def config():
    saved = json.loads(CONFIG_FILE.read_text()) if CONFIG_FILE.exists() else {}
    return {key: os.environ.get(env) or saved.get(key) or default for key, env, default in [
        ('gemini_key','GEMINI_API_KEY',''),('eleven_key','ELEVENLABS_API_KEY',''),
        ('gemini_model','GEMINI_MODEL','gemini-2.5-flash'),('eleven_model','ELEVENLABS_MODEL','eleven_multilingual_v2')]}

def save_config(data):
    allowed = {'gemini_key','eleven_key','gemini_model','eleven_model'}
    if set(data) - allowed: raise ProcessingError('Unknown settings field.')
    current = json.loads(CONFIG_FILE.read_text()) if CONFIG_FILE.exists() else {}
    for k, v in data.items():
        if not isinstance(v, str) or len(v) > 1024: raise ProcessingError('Invalid settings value.')
        if not v.strip(): continue
        if 'model' in k and not re.fullmatch(r'[a-zA-Z0-9._-]{1,100}',v): raise ProcessingError('Invalid model name.')
        env_name = {'gemini_key':'GEMINI_API_KEY','eleven_key':'ELEVENLABS_API_KEY','gemini_model':'GEMINI_MODEL','eleven_model':'ELEVENLABS_MODEL'}[k]
        if os.environ.get(env_name) and os.environ[env_name] != v:
            raise ProcessingError(f'{env_name} is managed by the server host. Update it in the hosting settings.')
        current[k] = v.strip()
    temp = DATA / ('settings-' + secrets.token_hex(6) + '.tmp')
    fd = os.open(temp,os.O_CREAT | os.O_EXCL | os.O_WRONLY,0o600)
    with os.fdopen(fd,'w') as f: json.dump(current,f)
    os.replace(temp,CONFIG_FILE)

def numeric(value, low, high, label):
    if isinstance(value, bool) or not isinstance(value, (int,float)) or not math.isfinite(value) or not low <= value <= high:
        raise ProcessingError(f'Invalid {label}.')
    return value

def validate_options(raw):
    if not isinstance(raw,dict): raise ProcessingError('Invalid rendering options.')
    sub = raw.get('subtitle',{})
    if not isinstance(sub,dict): raise ProcessingError('Invalid subtitle options.')
    font = sub.get('font','Noto Sans')
    if font not in FONTS: raise ProcessingError('Select a supported subtitle font.')
    result = {'subtitle': {'font':font, 'size':numeric(sub.get('size',26),14,54,'font size'),
                          'position':numeric(sub.get('position',9),3,85,'subtitle position'),
                          'bold':sub.get('bold',False), 'text_color':sub.get('text_color','#ffffff'),
                          'background_color':sub.get('background_color','#000000')},
              'original_volume':numeric(raw.get('original_volume',0),0,1,'original volume'),
              'burn_subtitles':raw.get('burn_subtitles',True),'colors':{}}
    if not isinstance(result['subtitle']['bold'],bool) or not isinstance(result['burn_subtitles'],bool): raise ProcessingError('Invalid boolean option.')
    for k in ('text_color','background_color'):
        if not isinstance(result['subtitle'][k],str) or not re.fullmatch(r'#[a-fA-F0-9]{6}',result['subtitle'][k]): raise ProcessingError('Invalid subtitle color.')
    colors = raw.get('colors',{})
    if not isinstance(colors,dict): raise ProcessingError('Invalid color settings.')
    for region in ('all','person','background','left','right'):
        c = colors.get(region,{})
        if not isinstance(c,dict): raise ProcessingError('Invalid color region.')
        result['colors'][region] = {k:numeric(c.get(k,default),*bounds,k) for k,default,bounds in [
            ('brightness',100,(40,180)),('contrast',100,(40,180)),('saturation',100,(0,200)),('hue',0,(-45,45))]}
    frame = raw.get('frame', {})
    blur = raw.get('blur', {})
    if not isinstance(frame, dict) or not isinstance(blur, dict):
        raise ProcessingError('Invalid frame or blur options.')
    aspect = frame.get('aspect', 'original')
    if aspect not in ('original', '9:16', '1:1', '4:5', '16:9', '3:4'):
        raise ProcessingError('Invalid aspect ratio.')
    mirror = frame.get('mirror', False)
    enabled = blur.get('enabled', False)
    if not isinstance(mirror, bool) or not isinstance(enabled, bool):
        raise ProcessingError('Invalid frame or blur switch.')
    result['frame'] = {'aspect': aspect, 'mirror': mirror, 'zoom': numeric(frame.get('zoom', 1), 1, 1.5, 'zoom')}
    result['blur'] = {'enabled': enabled, 'y': numeric(blur.get('y', 78), 0, 90, 'blur position'),
                      'height': numeric(blur.get('height', 12), 2, 35, 'blur height'),
                      'strength': numeric(blur.get('strength', 22), 1, 40, 'blur strength')}
    quality = raw.get('quality', 'normal')
    if quality not in ('draft', 'normal', 'high'): raise ProcessingError('Invalid output quality.')
    result['quality'] = quality
    logo = raw.get('logo')
    if logo is not None and (not isinstance(logo, str) or len(logo) > 2800000 or not re.fullmatch(r'data:image/(?:png|jpeg|webp);base64,[A-Za-z0-9+/=]+', logo)):
        raise ProcessingError('Choose a PNG, JPEG or WebP logo smaller than 2 MB.')
    result['logo'] = logo
    result['logo_size'] = numeric(raw.get('logo_size', 15), 5, 35, 'logo size')
    return result

def record(job_id):
    with closing(sqlite3.connect(DATABASE)) as db:
        db.row_factory = sqlite3.Row
        row = db.execute('SELECT * FROM jobs WHERE id=?',(job_id,)).fetchone()
    if not row: raise ProcessingError('Job not found.')
    return dict(row)

def update(job_id, stage, progress, message, status='running'):
    with closing(sqlite3.connect(DATABASE, timeout=30)) as db:
        db.execute('UPDATE jobs SET stage=?,progress=?,message=?,status=?,updated=? WHERE id=?',(stage,progress,message,status,time.time(),job_id)); db.commit()

def require_ready(action,cfg,options):
    if action in ('analyze','full') and not cfg['gemini_key']: raise ProcessingError('Configure GEMINI_API_KEY before analysis.')
    if action in ('render','full') and not cfg['eleven_key']: raise ProcessingError('Configure ELEVENLABS_API_KEY before voice generation.')
    for tool in ('ffmpeg','ffprobe'):
        if not shutil.which(tool): raise ProcessingError(f'Server dependency {tool} is missing.')
    if action in ('analyze','full') and not importlib.util.find_spec('yt_dlp'): raise ProcessingError('Server video download dependency is missing.')
    if action in ('render','full'):
        for package in ('cv2','numpy'):
            if not importlib.util.find_spec(package): raise ProcessingError(f'Server dependency {package} is missing.')
        if any(options['colors'][r] != DEFAULT_COLORS for r in ('person','background')) and not importlib.util.find_spec('mediapipe'):
            raise ProcessingError('Person/background segmentation dependency is missing.')

def create_job(body,request_id):
    if not re.fullmatch(r'[a-zA-Z0-9_-]{12,100}',request_id): raise ProcessingError('A unique request ID is required.')
    if not isinstance(body,dict): raise ProcessingError('Invalid job request.')
    action = body.get('action','full')
    if action not in ('full','analyze','render'): raise ProcessingError('Invalid job action.')
    payload = {'action':action,'options':validate_options(body.get('options',{}))}
    if action == 'render':
        parent = body.get('analysis_id','')
        if not re.fullmatch(r'[a-f0-9]{32}',parent): raise ProcessingError('Select a completed analysis.')
        info = record(parent)
        folder = DATA / parent
        if info['status'] != 'succeeded' or not (folder/'transcript.json').exists(): raise ProcessingError('Analysis is not ready.')
        meta = json.loads((folder/'metadata.json').read_text())
        payload['analysis_id'] = parent
        payload['segments'] = validate_segments(body.get('segments',json.loads((folder/'transcript.json').read_text())),meta['duration'])
    else: payload['url'] = validate_source(body.get('url'))
    if action != 'analyze':
        payload['voice_id'] = body.get('voice_id','')
        if not isinstance(payload['voice_id'],str) or not re.fullmatch(r'[\w-]{8,100}',payload['voice_id']): raise ProcessingError('Select a cloud English voice.')
        payload['speed'] = numeric(body.get('speed',1),.7,1.2,'voice speed')
    cfg = config()
    require_ready(action,cfg,payload['options'])
    encoded = json.dumps(payload,sort_keys=True)
    digest = hashlib.sha256(encoded.encode()).hexdigest()
    with LOCK,closing(sqlite3.connect(DATABASE)) as db:
        existing = db.execute('SELECT id,request_hash FROM jobs WHERE request_id=?',(request_id,)).fetchone()
        if existing:
            if existing[1] != digest: raise ProcessingError('Request ID was already used for different settings.')
            return existing[0]
        active = db.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0]
        if active >= 2: raise ProcessingError('Another video is processing. Wait for it to finish.')
        job_id = secrets.token_hex(16)
        db.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?)',(job_id,request_id,digest,encoded,'queued','queued',0,'Waiting to process',time.time(),time.time())); db.commit()
        POOL.submit(process_job,job_id,payload,cfg)
    return job_id

def process_job(job_id,payload,cfg):
    folder = DATA / job_id
    folder.mkdir(mode=0o700)
    report = lambda stage,percent,message: update(job_id,stage,percent,message)
    try:
        if payload['action']=='render':
            parent = DATA / payload['analysis_id']
            meta = json.loads((parent/'metadata.json').read_text())
            source = Path(meta['source'])
            if not source.is_file(): raise ProcessingError('Source video expired. Analyze the link again.')
            segments = payload['segments']
        else:
            source = download_source(payload['url'],folder,report)
            info,video,duration = probe(source)
            if not video or duration <= 0 or duration > int(os.environ.get('MAX_VIDEO_SECONDS','1800')):
                raise ProcessingError('Source has no video or exceeds the configured duration limit.')
            if not any(s['codec_type']=='audio' for s in info['streams']): raise ProcessingError('This video has no audio to translate.')
            meta = {'source':str(source),'duration':duration,'width':video['width'],'height':video['height']}
            segments = transcribe(source,folder,cfg,duration,report)
        (folder/'metadata.json').write_text(json.dumps(meta))
        (folder/'transcript.json').write_text(json.dumps(segments,ensure_ascii=False),encoding='utf-8')
        subtitles(segments,payload['options']['subtitle'],folder,meta['width'],meta['height'])
        if payload['action']!='analyze':
            voice = voice_track(segments,meta['duration'],payload['voice_id'],payload['speed'],folder,cfg,report)
            render_video(source,voice,folder,payload['options'],report)
        update(job_id,'complete',100,'Analysis ready for review' if payload['action']=='analyze' else 'English WAV, subtitles and final MP4 ready',status='succeeded')
    except ProcessingError as exc:
        update(job_id,'failed',record(job_id)['progress'],str(exc),status='failed')
    except Exception as exc:
        logging.error('Job %s failed: %s',job_id,type(exc).__name__)
        update(job_id,'failed',record(job_id)['progress'],'Processing failed. Check server dependencies and configuration. No final success was reported.',status='failed')

def signed_url(job_id,name):
    expires = int(time.time()) + 900
    path = f'/v1/jobs/{job_id}/files/{name}'
    signature = hmac.new(ADMIN.encode(),f'{path}:{expires}'.encode(),hashlib.sha256).hexdigest()
    return f'{path}?expires={expires}&signature={signature}'

def job_info(job_id):
    row = record(job_id)
    folder = DATA / job_id
    result = {k:row[k] for k in ('id','status','stage','progress','message','created','updated')}
    files = {key:signed_url(job_id,name) for key,name in [('wav','english.wav'),('srt','english.srt'),('ass','english.ass'),('mp4','final.mp4')] if (folder/name).exists() and (key != 'mp4' or row['status']=='succeeded')}
    result['files'] = files
    if (folder/'transcript.json').exists(): result['segments'] = json.loads((folder/'transcript.json').read_text())
    if (folder/'metadata.json').exists():
        meta = json.loads((folder/'metadata.json').read_text()); result['duration']=meta['duration']; result['source_preview']=signed_url(job_id,'source')
    return result

class Handler(BaseHTTPRequestHandler):
    server_version = 'ATKStudio'
    def log_message(self, *_): pass  # Query strings include expiring download signatures.
    def cors(self):
        origin = self.headers.get('Origin','')
        if origin in ORIGINS:
            self.send_header('Access-Control-Allow-Origin',origin)
            self.send_header('Vary','Origin')
            self.send_header('Access-Control-Allow-Headers','Authorization, Content-Type, X-Request-ID')
            self.send_header('Access-Control-Allow-Methods','GET, POST, OPTIONS')
            self.send_header('Access-Control-Expose-Headers','Content-Disposition, Content-Range')
    def respond(self,code,data):
        content = json.dumps(data,ensure_ascii=False).encode()
        self.send_response(code); self.cors(); self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(content)));self.end_headers();self.wfile.write(content)
    def authorized(self):
        supplied = self.headers.get('Authorization','')
        return bool(ADMIN) and hmac.compare_digest(supplied,'Bearer '+ADMIN)
    def signed(self):
        u = urlsplit(self.path); q = parse_qs(u.query)
        try:
            exp = int(q.get('expires',['0'])[0])
            if not time.time() <= exp <= time.time()+901: return False
            sig = q.get('signature',[''])[0]
            expected = hmac.new(ADMIN.encode(),f'{u.path}:{exp}'.encode(),hashlib.sha256).hexdigest()
            return bool(ADMIN) and hmac.compare_digest(sig,expected)
        except (ValueError,TypeError): return False
    def do_OPTIONS(self):
        if self.headers.get('Origin') not in ORIGINS: return self.respond(403,{'error':'Origin not allowed.'})
        self.send_response(204);self.cors();self.send_header('Content-Length','0');self.end_headers()
    def do_GET(self):
        path = urlsplit(self.path).path
        if path=='/health': return self.respond(200,{'ok':True,'service':'ATK English processor'})
        file_match = re.fullmatch(r'/v1/jobs/([a-f0-9]{32})/files/(source|english\.wav|english\.srt|english\.ass|final\.mp4)',path)
        if not self.authorized() and not (file_match and self.signed()): return self.respond(401,{'error':'Enter the server access token in Settings.'})
        try:
            if file_match: return self.send_file(*file_match.groups())
            if path=='/v1/status':
                cfg=config();return self.respond(200,{'connected':True,'gemini_configured':bool(cfg['gemini_key']),'elevenlabs_configured':bool(cfg['eleven_key']),
                    'models':{'gemini':cfg['gemini_model'],'elevenlabs':cfg['eleven_model']},'fonts':sorted(set(FONTS.values())),
                    'dependencies':{name:bool(importlib.util.find_spec(name)) for name in ('numpy','cv2','mediapipe','yt_dlp')},
                    'ffmpeg':bool(shutil.which('ffmpeg')),'max_video_seconds':int(os.environ.get('MAX_VIDEO_SECONDS','1800'))})
            if path=='/v1/voices':
                cfg=config()
                if not cfg['eleven_key']: raise ProcessingError('Configure ELEVENLABS_API_KEY in Settings.')
                return self.respond(200,{'voices':list_voices(cfg)})
            job = re.fullmatch(r'/v1/jobs/([a-f0-9]{32})',path)
            if job: return self.respond(200,job_info(job[1]))
            return self.respond(404,{'error':'Route not found.'})
        except ProcessingError as exc: self.respond(400,{'error':str(exc)})
        except Exception: self.respond(500,{'error':'Server request failed. Check server configuration.'})
    def do_POST(self):
        if not self.authorized(): return self.respond(401,{'error':'Enter the server access token in Settings.'})
        origin=self.headers.get('Origin')
        if origin and origin not in ORIGINS: return self.respond(403,{'error':'Origin not allowed.'})
        try:
            size=int(self.headers.get('Content-Length','0'))
            if size<=0 or size>MAX_BODY: return self.respond(413,{'error':'Request body too large or empty.'})
            data=json.loads(self.rfile.read(size))
            if not isinstance(data,dict): raise ProcessingError('Request must be a JSON object.')
            path=urlsplit(self.path).path
            if path=='/v1/settings':
                with LOCK: save_config(data)
                return self.respond(200,{'saved':True})
            if path=='/v1/jobs': return self.respond(202,{'id':create_job(data,self.headers.get('X-Request-ID',''))})
            if path=='/v1/voice-preview':
                cfg=config()
                if not cfg['eleven_key']: raise ProcessingError('Configure ELEVENLABS_API_KEY.')
                text=data.get('text','Hello. This is your English voice preview.')
                if not isinstance(text,str) or not 1<=len(text)<=250: raise ProcessingError('Preview text must be 1–250 characters.')
                content=speech(text,data.get('voice_id',''),numeric(data.get('speed',1),.7,1.2,'voice speed'),cfg)
                self.send_response(200);self.cors();self.send_header('Content-Type','audio/mpeg');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(content)));self.end_headers();self.wfile.write(content);return
            return self.respond(404,{'error':'Route not found.'})
        except (ValueError,json.JSONDecodeError): self.respond(400,{'error':'Invalid JSON request.'})
        except ProcessingError as exc: self.respond(400,{'error':str(exc)})
        except Exception: self.respond(500,{'error':'Server request failed. Check server configuration.'})
    def send_file(self,job_id,name):
        folder=DATA/job_id
        record(job_id)
        if name=='source':
            metadata=json.loads((folder/'metadata.json').read_text())
            path=Path(metadata['source']).resolve()
            if DATA not in path.parents: raise ProcessingError('Invalid source path.')
        else: path=folder/name
        if not path.is_file(): return self.respond(404,{'error':'Output is not ready.'})
        if name=='final.mp4' and record(job_id)['status']!='succeeded': return self.respond(409,{'error':'Final output is not ready.'})
        size=path.stat().st_size; start,end=0,size-1
        header=self.headers.get('Range'); partial=False
        if header:
            m=re.fullmatch(r'bytes=(\d+)-(\d*)',header)
            if not m: return self.respond(416,{'error':'Unsupported byte range.'})
            start=int(m[1]);end=min(int(m[2]),end) if m[2] else end;partial=True
            if start>end or start>=size: return self.respond(416,{'error':'Invalid byte range.'})
        self.send_response(206 if partial else 200);self.cors();self.send_header('Content-Type',mimetypes.guess_type(path.name)[0] or 'application/octet-stream');self.send_header('Content-Length',str(end-start+1));self.send_header('Accept-Ranges','bytes');self.send_header('Cache-Control','private, no-store');self.send_header('Referrer-Policy','no-referrer')
        if partial:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
        if name!='source':self.send_header('Content-Disposition',f'attachment; filename="{name}"')
        self.end_headers()
        try:
            with path.open('rb') as f:
                f.seek(start);remaining=end-start+1
                while remaining:
                    chunk=f.read(min(1024*1024,remaining))
                    if not chunk:break
                    self.wfile.write(chunk);remaining-=len(chunk)
        except (BrokenPipeError,ConnectionResetError):pass

def main():
    if len(ADMIN)<32:
        raise SystemExit('Set ADMIN_TOKEN to a random string of at least 32 characters before starting the server.')
    if not ORIGINS or '*' in ORIGINS:
        raise SystemExit('ALLOWED_ORIGINS must contain explicit frontend HTTPS origins.')
    initialize()
    server=ThreadingHTTPServer(('0.0.0.0',int(os.environ.get('PORT','8080'))),Handler)
    server.daemon_threads=True
    server.serve_forever()

if __name__=='__main__':main()
