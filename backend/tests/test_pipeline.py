import array
from contextlib import closing
import http.client
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import wave

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import engine
import server

class EngineTests(unittest.TestCase):
    def test_link_validation(self):
        self.assertEqual(engine.validate_source('https://youtu.be/abcdefghijk?si=abc'),'https://www.youtube.com/watch?v=abcdefghijk')
        self.assertEqual(engine.validate_source('https://youtube.com/shorts/abcdefghijk'),'https://www.youtube.com/watch?v=abcdefghijk')
        self.assertTrue(engine.validate_source('https://www.tiktok.com/@someone/video/123456789').endswith('123456789'))
        for source in ['http://youtube.com/watch?v=abcdefghijk','https://youtube.com.evil.test/watch?v=abcdefghijk','https://youtube.com@127.0.0.1/video','https://127.0.0.1/a','https://youtube.com/playlist?list=123','https://youtu.be/abcdefghijk:123']:
            with self.subTest(source=source),self.assertRaises(engine.ProcessingError):engine.validate_source(source)

    def test_timestamp_validation_rejects_overlap_and_invalid_duration(self):
        good=[{'start':1,'end':2,'text':'Hello'},{'start':3,'end':4,'text':'Next scene'}]
        self.assertEqual(engine.validate_segments(good,5),good)
        for segments in [[{'start':0,'end':7,'text':'Wrong'}],[{'start':float('nan'),'end':1,'text':'Wrong'}],[{'start':0,'end':2,'text':'A'},{'start':1,'end':3,'text':'B'}]]:
            with self.assertRaises(engine.ProcessingError):engine.validate_segments(segments,5)

    def test_subtitles_and_font_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            opts=server.validate_options({'subtitle':{'font':'Arial','bold':True,'text_color':'#00aaff'}})
            cues=engine.subtitles([{'start':1.2,'end':3.4,'text':'Hello {bad} \\pos(1,2) world'}],opts['subtitle'],folder,640,360)
            self.assertIn('00:00:01,200 --> 00:00:03,400',(folder/'english.srt').read_text())
            ass=(folder/'english.ass').read_text()
            self.assertIn('Liberation Sans',ass)
            self.assertIn('&H00ffaa00',ass)
            self.assertNotIn('{bad}',ass)
            self.assertEqual(cues[0]['start'],1.2)
            self.assertEqual(engine.timestamp(59.9996),'00:01:00,000')

    def test_voice_placed_at_scene_times_full_length_wav(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            tone=folder/'tone.mp3'
            engine.run(['ffmpeg','-y','-v','error','-f','lavfi','-i','sine=frequency=440:duration=0.4','-c:a','libmp3lame',str(tone)])
            segments=[{'start':1,'end':2,'text':'First scene'},{'start':3,'end':4,'text':'Second scene'}]
            with patch('engine.speech',return_value=tone.read_bytes()):
                result=engine.voice_track(segments,5,'voice_identifier',1,folder,{},lambda *_:None)
            with wave.open(str(result),'rb') as f:
                self.assertEqual(f.getnframes(),120000)
                samples=array.array('h');samples.frombytes(f.readframes(f.getnframes()))
            self.assertEqual(max(map(abs,samples[:24000])),0)
            self.assertGreater(max(map(abs,samples[24000:35000])),100)
            self.assertEqual(max(map(abs,samples[48000:72000])),0)
            self.assertGreater(max(map(abs,samples[72000:83000])),100)
            self.assertEqual(max(map(abs,samples[100000:])),0)

    def test_long_voice_extends_scene_and_keeps_later_scenes(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);tone=folder/'tone.mp3'
            engine.run(['ffmpeg','-y','-v','error','-f','lavfi','-i','sine=frequency=440:duration=3','-c:a','libmp3lame',str(tone)])
            segments=[{'start':0,'end':1,'text':'All words from the first scene'},
                      {'start':2,'end':3,'text':'Every word from the second scene'}]
            with patch('engine.speech',return_value=tone.read_bytes()):
                result=engine.voice_track(segments,4,'voice_identifier',1,folder,{},lambda *_:None)
            timeline=json.loads((folder/'timeline.json').read_text())
            captions=json.loads((folder/'captions.json').read_text())
            self.assertEqual([c['text'] for c in captions],[c['text'] for c in segments])
            self.assertGreater(captions[0]['end'],2)
            self.assertAlmostEqual(captions[1]['start']-captions[0]['end'],1)
            self.assertEqual(timeline[-1]['source_end'],4)
            with wave.open(str(result)) as f:
                self.assertAlmostEqual(f.getnframes()/f.getframerate(),timeline[-1]['output_end'])
            self.assertAlmostEqual(engine.map_scene_time(4,timeline),timeline[-1]['output_end'])

class APITests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();root=Path(self.tmp.name)
        self.saved=(server.DATA,server.DATABASE,server.CONFIG_FILE,server.ADMIN)
        server.DATA=root;server.DATABASE=root/'jobs.sqlite3';server.CONFIG_FILE=root/'provider-settings.json';server.ADMIN='testing-owner-token-not-a-real-secret-12345'
        server.initialize()
        self.http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):
        self.http.shutdown();self.http.server_close();self.thread.join();server.DATA,server.DATABASE,server.CONFIG_FILE,server.ADMIN=self.saved;self.tmp.cleanup()
    def request(self,method,path,body=None,auth=True,headers=None):
        connection=http.client.HTTPConnection('127.0.0.1',self.http.server_port)
        h=headers or {}
        if auth:h['Authorization']='Bearer '+server.ADMIN
        if body is not None:h['Content-Type']='application/json'
        connection.request(method,path,body=json.dumps(body) if body is not None else None,headers=h)
        result=connection.getresponse();content=result.read();status=result.status;response_headers=dict(result.getheaders());connection.close()
        return status,content,response_headers
    def test_authorization_and_no_secret_exposure(self):
        self.assertEqual(self.request('GET','/v1/status',auth=False)[0],401)
        with patch.dict(os.environ,{'GEMINI_API_KEY':'','ELEVENLABS_API_KEY':'','GEMINI_MODEL':''}):
            status,_,_=self.request('POST','/v1/settings',{'gemini_key':'test-value'});self.assertEqual(status,200)
            self.assertEqual(server.CONFIG_FILE.stat().st_mode&0o777,0o600)
            status,data,_=self.request('GET','/v1/status');self.assertEqual(status,200)
            self.assertNotIn('test-value',data.decode())
            self.assertTrue(json.loads(data)['gemini_configured'])
    def test_job_idempotency_and_payload_conflict(self):
        body={'action':'analyze','url':'https://youtu.be/abcdefghijk'}
        with patch('server.require_ready'),patch.object(server.POOL,'submit') as submit:
            a=self.request('POST','/v1/jobs',body,headers={'X-Request-ID':'same-request-id-123'})
            b=self.request('POST','/v1/jobs',body,headers={'X-Request-ID':'same-request-id-123'})
            self.assertEqual(a[0],202);self.assertEqual(json.loads(a[1]),json.loads(b[1]));self.assertEqual(submit.call_count,1)
            body['url']='https://youtu.be/123456789ab'
            self.assertEqual(self.request('POST','/v1/jobs',body,headers={'X-Request-ID':'same-request-id-123'})[0],400)
    def test_signed_download_range_and_expiration(self):
        job='a'*32;folder=server.DATA/job;folder.mkdir();(folder/'english.wav').write_bytes(b'abcdefghij')
        with closing(sqlite3.connect(server.DATABASE)) as db:
            db.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?)',(job,'file-request-id','hash','{}','succeeded','complete',100,'Ready',0,0));db.commit()
        link=server.signed_url(job,'english.wav')
        status,data,headers=self.request('GET',link,auth=False,headers={'Range':'bytes=2-5'})
        self.assertEqual(status,206);self.assertEqual(data,b'cdef');self.assertEqual(headers['Content-Range'],'bytes 2-5/10')
        self.assertEqual(self.request('GET',link.replace('signature=','signature=bad'),auth=False)[0],401)
        self.assertEqual(self.request('GET',f'/v1/jobs/{job}/files/english.wav?expires=1&signature=bad',auth=False)[0],401)
    def test_invalid_options_rejected_before_job_creation(self):
        for opts in [{'original_volume':1.5},{'subtitle':{'font':'UninstalledFont'}},{'colors':{'person':{'brightness':float('inf')}}}]:
            with self.assertRaises(engine.ProcessingError):server.validate_options(opts)

if __name__=='__main__':unittest.main()
