import test from 'node:test';import assert from 'node:assert/strict';
import {mkdtemp,rm,readFile} from 'node:fs/promises';import os from 'node:os';import path from 'node:path';import {execFileSync} from 'node:child_process';
import {run} from './render.js';import {overlayNarration,wavDuration} from './narration.js';
test('separate narration survives MP4 export and fits scene duration',async()=>{
 const dir=await mkdtemp(path.join(os.tmpdir(),'narration-test-'));
 try{
  const video=path.join(dir,'video.mp4'),wav=path.join(dir,'voice.wav');
  await run(['-f','lavfi','-i','color=c=green:s=320x240:r=24','-t','2','-c:v','libx264',video]);
  await run(['-f','lavfi','-i','sine=frequency=600:sample_rate=24000','-t','3','-c:a','pcm_s16le',wav]);
  const audio=await readFile(wav);assert.ok(Math.abs(wavDuration(audio)-3)<.01);
  await overlayNarration(video,audio,2);
  const d=JSON.parse(execFileSync('ffprobe',['-v','quiet','-show_format','-show_streams','-of','json',video]));assert.ok(Math.abs(Number(d.format.duration)-2)<.1);assert.equal(d.streams.find(s=>s.codec_type==='audio').codec_name,'aac');
  const pcm=execFileSync('ffmpeg',['-v','error','-i',video,'-t','1','-map','0:a:0','-ac','1','-f','s16le','pipe:1']);let energy=0;for(let i=0;i<pcm.length;i+=2)energy+=pcm.readInt16LE(i)**2;assert.ok(energy>100000,'Narration must be audible');
  await assert.rejects(overlayNarration(video,audio,1),/too long/);assert.throws(()=>wavDuration(Buffer.from('not a wav')),/WAV/);
 }finally{await rm(dir,{recursive:true,force:true})}
});
