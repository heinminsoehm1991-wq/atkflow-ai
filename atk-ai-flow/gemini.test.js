import test from 'node:test';import assert from 'node:assert/strict';
import {imageRequest,videoRequest,googlePrompt,googleImage,googleVideo} from './gemini.js';
const image={buffer:Buffer.from('product-reference'),mimetype:'image/jpeg'},character={buffer:Buffer.from('character-reference'),mimetype:'image/png'};
test('Gemini preserves two separate references and Veo rounds billable durations',()=>{
 const request=imageRequest('google/gemini-2.5-flash-image','ad',image,character,'9:16');
 assert.equal(request.contents[0].parts[1].inlineData.data,image.buffer.toString('base64'));
 assert.equal(request.contents[0].parts[2].inlineData.mimeType,'image/png');
 for(const [seconds,billed] of [[1,4],[4,4],[5,6],[6,6],[7,8],[8,8]])assert.equal(videoRequest('google/veo-3.1-fast-generate-preview','ad',image,seconds,'16:9').config.durationSeconds,billed);
 assert.throws(()=>videoRequest('google/veo-3.1-fast-generate-preview','ad',image,5,'1:1'));
 assert.throws(()=>videoRequest('google/veo-3.1-fast-generate-preview','ad',image,10,'16:9'));
});
test('Gemini rejects malformed plans and safety-blocked images',async()=>{
 await assert.rejects(googlePrompt({models:{generateContent:async()=>({text:'["only one"]'})}},'ad',2,1,2),/invalid scene plan/);
 await assert.rejects(googleImage({models:{generateContent:async()=>({promptFeedback:{blockReason:'SAFETY'}})}},{}),/SAFETY/);
 const result=await googleImage({models:{generateContent:async()=>({candidates:[{content:{parts:[{inlineData:{mimeType:'image/png',data:Buffer.from('image-output').toString('base64')}}]}}]})}},{});
 assert.equal(result.buffer.toString(),'image-output');
});
test('Veo refuses blocked operations and downloads successful output using server credentials',async()=>{
 await assert.rejects(googleVideo({models:{generateVideos:async()=>({done:true,error:{message:'quota exhausted'}})}},{},'/unused'),/quota exhausted/);
 let downloaded;const video={uri:'https://generativelanguage.googleapis.com/v1beta/files/video:download'};
 await googleVideo({models:{generateVideos:async()=>({done:true,response:{generatedVideos:[{video}]}})},files:{download:async(args)=>{downloaded=args}}},{},'/tmp/test-output.mp4');
 assert.deepEqual(downloaded,{file:video,downloadPath:'/tmp/test-output.mp4'});
});
