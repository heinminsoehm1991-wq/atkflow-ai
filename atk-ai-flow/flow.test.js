import {planDuration} from './duration.js';
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,rm} from 'node:fs/promises';
import os from 'node:os';import path from 'node:path';
import {execFileSync} from 'node:child_process';
import {models,modelInput} from './models.js';
import {run,mergeClips,validateClips} from './render.js';
test('provider schemas and invalid models',()=>{assert.equal(modelInput('video','fal-ai/kling-video/v2.6/pro/image-to-video','p','https://image',5).start_image_url,'https://image');assert.equal(modelInput('video','fal-ai/wan/v2.2-5b/image-to-video','p','https://image',5).num_frames,121);assert.throws(()=>modelInput('image','unknown','p','url'));});
test('duration limits',()=>{assert.equal(validateClips(Array.from({length:24},()=>({seconds:5}))),120);assert.equal(validateClips(Array.from({length:36},()=>({seconds:5}))),180);assert.throws(()=>validateClips([{seconds:NaN}]));assert.throws(()=>validateClips([]));});
test('real MP4 merge: mixed sizes, trim and last frame hold, exact duration',async()=>{const dir=await mkdtemp(path.join(os.tmpdir(),'flow-test-'));try{await run(['-f','lavfi','-i','color=c=red:s=320x240:r=24','-t','1','-c:v','libx264',path.join(dir,'a.mp4')]);await run(['-f','lavfi','-i','color=c=blue:s=240x320:r=24','-t','3','-c:v','libx264',path.join(dir,'b.mp4')]);await mergeClips([{source:path.join(dir,'a.mp4'),seconds:2},{source:path.join(dir,'b.mp4'),seconds:1}],path.join(dir,'out'),'9:16');const data=JSON.parse(execFileSync('ffprobe',['-v','quiet','-show_format','-show_streams','-of','json',path.join(dir,'out/final.mp4')]));assert.equal(data.streams[0].width,720);assert.equal(data.streams[0].height,1280);assert.ok(Math.abs(Number(data.format.duration)-3)<.1)}finally{await rm(dir,{recursive:true,force:true})}});

test('custom durations sum exactly, including partial last scene and long video',()=>{for(const seconds of [1,75,120,180,181,900,3600]){const plan=planDuration(seconds);assert.equal(plan.reduce((a,b)=>a+b,0),seconds);assert.ok(plan.every(s=>s>=1&&s<=5));assert.equal(validateClips(plan.map(seconds=>({seconds}))),seconds)}assert.equal(planDuration(181).at(-1),1);for(const n of [0,-1,3601,1.5,NaN])assert.throws(()=>planDuration(n));assert.throws(()=>planDuration(3600,1));});

test('MP4 preserves real scene audio and safely joins silent scenes',async()=>{
 const dir=await mkdtemp(path.join(os.tmpdir(),'flow-audio-'));
 try{
  await run(['-f','lavfi','-i','color=c=green:s=320x240:r=24','-f','lavfi','-i','sine=frequency=440:sample_rate=44100','-t','1','-c:v','libx264','-c:a','aac',path.join(dir,'voice.mp4')]);
  await run(['-f','lavfi','-i','color=c=blue:s=320x240:r=24','-t','1','-c:v','libx264',path.join(dir,'silent.mp4')]);
  const out=path.join(dir,'out');await mergeClips([{source:path.join(dir,'voice.mp4'),seconds:1},{source:path.join(dir,'silent.mp4'),seconds:1}],out,'16:9');
  const file=path.join(out,'final.mp4');const metadata=JSON.parse(execFileSync('ffprobe',['-v','quiet','-show_streams','-show_format','-of','json',file]));
  const audio=metadata.streams.find(s=>s.codec_type==='audio');assert.equal(audio.codec_name,'aac');assert.equal(audio.channels,2);assert.ok(Math.abs(Number(metadata.format.duration)-2)<.1);
  const rms=start=>{const pcm=execFileSync('ffmpeg',['-v','error','-ss',String(start),'-i',file,'-t','0.3','-map','0:a:0','-f','s16le','-ac','1','pipe:1']);let sum=0;for(let i=0;i<pcm.length;i+=2)sum+=pcm.readInt16LE(i)**2;return Math.sqrt(sum/(pcm.length/2))};
  assert.ok(rms(.2)>100,'Speech/tone audio must survive render');assert.ok(rms(1.6)<20,'Silent scene must not replay previous audio');
 }finally{await rm(dir,{recursive:true,force:true})}
});
