"""Native FFmpeg + CPU segmentation smoke test; no cloud keys or paid calls."""
import importlib.util
import base64
import json
from pathlib import Path
import sys
import tempfile
import unittest
import wave

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import engine
import server

@unittest.skipUnless(all(importlib.util.find_spec(p) for p in ('cv2','numpy','mediapipe')),'Native vision dependencies not installed')
class NativeRenderTests(unittest.TestCase):
    def test_portrait_mirror_blur_logo_and_final_caption(self):
        import cv2
        import numpy as np
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            image = np.zeros((180,320,3),dtype=np.uint8)
            image[:,:160] = (255,0,0)
            image[:,160:] = (0,0,255)
            for x in range(320): image[130:160,x] = (255,255,255) if x%4<2 else (0,0,0)
            cv2.imwrite(str(folder/'source.png'),image)
            source = folder/'source.mp4'
            engine.run(['ffmpeg','-y','-v','error','-loop','1','-i',str(folder/'source.png'),'-t','1','-r','10','-c:v','libx264','-pix_fmt','yuv420p',str(source)])
            voice = folder/'english.wav'
            with wave.open(str(voice),'wb') as f:
                f.setnchannels(1);f.setsampwidth(2);f.setframerate(24000);f.writeframes(b'\0\0'*24000)
            (folder/'transcript.json').write_text(json.dumps([{'start':0,'end':1,'text':'English portrait'}]))
            logo = np.zeros((20,40,4),dtype=np.uint8);logo[:] = (0,255,0,255)
            _,encoded = cv2.imencode('.png',logo)
            options = server.validate_options({'frame':{'aspect':'9:16','mirror':True,'zoom':1.1},
                'blur':{'enabled':True,'y':70,'height':20,'strength':15},
                'logo':'data:image/png;base64,'+base64.b64encode(encoded).decode()})
            # Pixel checks independently verify the effects before lossy encoding.
            rendered = engine.frame_effects(image.copy(),options,320,180,logo)
            self.assertGreater(int(rendered[30,30,2]),200)
            self.assertGreater(int(rendered[15,285,1]),200)
            self.assertLess(float(rendered[135:150,30:100].std()),float(image[135:150,30:100].std()))
            final = engine.render_video(source,voice,folder,options,lambda *a:None)
            _,stream,duration = engine.probe(final)
            self.assertEqual((stream['width'],stream['height']),(404,720))
            self.assertAlmostEqual(duration,1,delta=.1)
            self.assertIn('PlayResX: 404',(folder/'english.ass').read_text())

    def test_extended_scene_preserves_video_audio_and_caption(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp); source=folder/'source.mp4'; tone=folder/'tone.mp3'
            engine.run(['ffmpeg','-y','-v','error','-f','lavfi','-i','testsrc2=size=160x120:rate=10:duration=3','-f','lavfi','-i','sine=frequency=220:duration=3','-c:v','libx264','-c:a','aac',str(source)])
            engine.run(['ffmpeg','-y','-v','error','-f','lavfi','-i','sine=frequency=440:duration=3','-c:a','libmp3lame',str(tone)])
            segments=[{'start':.5,'end':1.5,'text':'Keep every spoken word'}]
            (folder/'transcript.json').write_text(json.dumps(segments))
            with patch('engine.speech',return_value=tone.read_bytes()):
                voice=engine.voice_track(segments,3,'voice_identifier',1,folder,{},lambda *_:None)
            options=server.validate_options({'original_volume':.2,'quality':'draft'})
            result=engine.render_video(source,voice,folder,options,lambda *_:None)
            timeline=json.loads((folder/'timeline.json').read_text())
            _,_,duration=engine.probe(result)
            self.assertAlmostEqual(duration,timeline[-1]['output_end'],delta=.2)
            self.assertGreater(duration,4)
            self.assertIn('Keep every spoken word',(folder/'english.srt').read_text())
            _,_,original_duration=engine.probe(folder/'original-retimed.wav')
            self.assertAlmostEqual(original_duration,timeline[-1]['output_end'],delta=.05)

    def test_real_person_mask_and_final_mux_duration(self):
        import cv2
        import mediapipe as mp
        import numpy as np
        import matplotlib
        image_path=Path(matplotlib.get_data_path())/'sample_data/grace_hopper.jpg'
        if not image_path.exists(): self.skipTest('Bundled test photograph missing')
        image=cv2.imread(str(image_path))
        with mp.solutions.selfie_segmentation.SelfieSegmentation(model_selection=1) as model:
            mask=model.process(cv2.cvtColor(image,cv2.COLOR_BGR2RGB)).segmentation_mask
            self.assertGreater(float(mask.max()),.8)
            self.assertLess(float(mask.min()),.2)
            self.assertGreater(int((mask>.8).sum()),100)
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);source=folder/'source.mp4'
            engine.run(['ffmpeg','-y','-v','error','-loop','1','-i',str(image_path),'-t','1.5','-r','12','-vf','scale=320:384','-c:v','libx264','-pix_fmt','yuv420p',str(source)])
            voice=folder/'english.wav'
            with wave.open(str(voice),'wb') as f:
                f.setnchannels(1);f.setsampwidth(2);f.setframerate(24000);f.writeframes(b'\0\0'*36000)
            (folder/'transcript.json').write_text(json.dumps([{'start':0,'end':1.5,'text':'English native render test'}]))
            options=server.validate_options({'colors':{'person':{'brightness':115},'background':{'saturation':30},'left':{'hue':10}}})
            events=[]
            final=engine.render_video(source,voice,folder,options,lambda *a:events.append(a))
            info,stream,duration=engine.probe(final)
            self.assertEqual(stream['codec_name'],'h264')
            self.assertAlmostEqual(duration,1.5,delta=.1)
            self.assertTrue(any(s['codec_type']=='audio' for s in info['streams']))
            output=cv2.VideoCapture(str(final));ok,frame=output.read();output.release()
            self.assertTrue(ok)
            self.assertEqual(frame.shape[:2],(384,320))
            self.assertGreater(final.stat().st_size,1000)
            self.assertIn('English native render test',(folder/'english.ass').read_text())

if __name__=='__main__':unittest.main()
