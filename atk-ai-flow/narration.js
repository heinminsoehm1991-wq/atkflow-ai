import { writeFile, rm, rename } from 'node:fs/promises';
import { run } from './render.js';
export function narrationRequest(text,voice='Charon'){
 if(!['Charon','Kore'].includes(voice))throw Error('Unsupported narration voice');
 return {model:'gemini-3.8-flash-tts',input:[{type:'user_input',content:[{type:'text',text,annotations:[{type:'speech_metadata',style:'Clear native Burmese (Myanmar) advertisement narration. Read only the exact text, without adding words. Natural brisk pace.'}]}]}],response_format:{type:'audio'},generation_config:{speech_config:[{voice}]}};
}
export async function googleNarration(text,voice){
 const response=await fetch('https://generativelanguage.googleapis.com/v1beta/interactions',{method:'POST',headers:{'Content-Type':'application/json','x-goog-api-key':process.env.GEMINI_API_KEY},body:JSON.stringify(narrationRequest(text,voice)),signal:AbortSignal.timeout(180000)});
 const result=await response.json();if(!response.ok)throw Error(result.error?.message||'Gemini TTS request failed');
 const blocks=(result.steps||[]).filter(s=>s.type==='model_output').flatMap(s=>s.content||[]).filter(p=>p.type==='audio'&&p.data);
 if(!blocks.length)throw Error('Gemini TTS returned no audio');return Buffer.from(blocks.at(-1).data,'base64');
}
export function wavDuration(buffer){
 if(buffer.toString('ascii',0,4)!=='RIFF'||buffer.toString('ascii',8,12)!=='WAVE')throw Error('Gemini TTS did not return a WAV file');
 let byteRate=0,dataSize=0;
 for(let offset=12;offset+8<=buffer.length;){const size=buffer.readUInt32LE(offset+4),id=buffer.toString('ascii',offset,offset+4);if(id==='fmt '&&size>=16&&offset+24<=buffer.length)byteRate=buffer.readUInt32LE(offset+16);if(id==='data'){dataSize=Math.min(size,buffer.length-offset-8);break}offset+=8+size+(size%2)}
 if(!byteRate||!dataSize)throw Error('Invalid narration audio');return dataSize/byteRate;
}
export async function overlayNarration(videoPath,wav,seconds){
 const duration=wavDuration(wav),speed=duration>seconds?duration/(seconds-0.1):1;
 if(speed>1.8)throw Error('Narration is too long. Shorten the scene dialogue or increase scene duration.');
 const audioPath=videoPath+'.voice.wav',destination=videoPath+'.voice.mp4';
 try{await writeFile(audioPath,wav);await run(['-i',videoPath,'-i',audioPath,'-map','0:v:0','-map','1:a:0','-c:v','copy','-af',`atempo=${speed},apad`,'-c:a','aac','-b:a','128k','-ar','48000','-ac','2','-t',String(seconds),'-movflags','+faststart',destination]);await rename(destination,videoPath)}finally{await rm(audioPath,{force:true});await rm(destination,{force:true})}
}
