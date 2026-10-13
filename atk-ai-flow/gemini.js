import { GoogleGenAI } from '@google/genai';
export const googleModels={image:['google/gemini-2.5-flash-image','google/gemini-3.1-flash-image'],video:['google/veo-3.1-fast-generate-preview','google/veo-3.1-generate-preview']};
export const isGoogle=model=>model?.startsWith('google/');
export function veoDuration(seconds){if(seconds>8)throw Error('Veo scenes must be 1–8 seconds');return seconds<=4?4:seconds<=6?6:8}
export function imageRequest(model,prompt,image,character,ratio){
 const images=[image,character].filter(Boolean);
 if(images.reduce((n,f)=>n+f.buffer.length,0)>12*1024*1024)throw Error('Gemini references must total at most 12 MB');
 return {model:model.replace('google/',''),contents:[{role:'user',parts:[{text:`${prompt}\nCreate one scene image in ${ratio} aspect ratio. Reference image 1 is the product; reference image 2, if present, is the character. Preserve their appearance.`},...images.map(f=>({inlineData:{data:f.buffer.toString('base64'),mimeType:f.mimetype}}))]}],config:{responseModalities:['TEXT','IMAGE'],imageConfig:{aspectRatio:ratio}}};
}
export function videoRequest(model,prompt,image,seconds,ratio){
 if(!['16:9','9:16'].includes(ratio))throw Error('Veo supports 16:9 or 9:16. Select one before generating.');
 return {model:model.replace('google/',''),prompt,image:{imageBytes:image.buffer.toString('base64'),mimeType:image.mimetype},config:{numberOfVideos:1,durationSeconds:veoDuration(seconds),aspectRatio:ratio,resolution:'720p',personGeneration:'allow_adult'}};
}
export function makeGoogle(){if(!process.env.GEMINI_API_KEY)throw Error('GEMINI_API_KEY is missing. Add it to this ATK service in Render Environment.');return new GoogleGenAI({apiKey:process.env.GEMINI_API_KEY,httpOptions:{timeout:180000}})}
export async function googlePrompt(ai,brief,count,start,total){
 const r=await ai.models.generateContent({model:process.env.GEMINI_PROMPT_MODEL||'gemini-2.5-flash',contents:`Create exactly ${count} coherent product advertisement scene prompts. Brief: ${brief}. Scenes ${start} through ${start+count-1} of ${total}. Preserve product and character reference identities. Include camera, setting, lighting and motion. Return a JSON array of ${count} strings.`,config:{responseMimeType:'application/json',maxOutputTokens:Math.min(16000,count*250+1000)}});
 if(!r.text)throw Error('Gemini returned no prompt text.');
 const plan=JSON.parse(r.text);if(!Array.isArray(plan)||plan.length!==count||plan.some(p=>typeof p!=='string'))throw Error('Gemini returned an invalid scene plan.');return {output:JSON.stringify(plan)};
}
export async function googleImage(ai,request){const r=await ai.models.generateContent(request);const part=r.candidates?.[0]?.content?.parts?.find(p=>p.inlineData?.data);if(!part)throw Error('Gemini returned no image. '+(r.promptFeedback?.blockReason||r.candidates?.[0]?.finishReason||''));if(!['image/png','image/jpeg','image/webp'].includes(part.inlineData.mimeType))throw Error('Unsupported Gemini image output');return {buffer:Buffer.from(part.inlineData.data,'base64'),mime:part.inlineData.mimeType}}
export async function googleVideo(ai,request,destination){
 let operation=await ai.models.generateVideos(request);
 for(let i=0;!operation.done&&i<180;i++){await new Promise(r=>setTimeout(r,10000));operation=await ai.operations.getVideosOperation({operation})}
 if(!operation.done)throw Error('Veo generation timed out.');if(operation.error)throw Error(operation.error.message||'Veo generation failed.');
 const video=operation.response?.generatedVideos?.[0]?.video;if(!video)throw Error('Veo returned no video. '+(operation.response?.raiMediaFilteredReasons?.join(', ')||''));
 await ai.files.download({file:video,downloadPath:destination});
}
