import {googleModels} from './gemini.js';
export const models={
 image:[...googleModels.image,'fal-ai/flux-kontext/dev','fal-ai/flux-pro/kontext','fal-ai/flux-pro/kontext/multi'],
 video:[...googleModels.video,'fal-ai/wan/v2.2-5b/image-to-video','fal-ai/kling-video/v2.6/pro/image-to-video']
};
export function modelInput(kind,model,prompt,image_url,seconds=5,ratio='16:9',characterUrl){
 if(model.startsWith('google/'))throw Error('Use the Gemini provider adapter for Google models.');
 if(!models[kind]?.includes(model))throw Error('Unsupported model. Select a verified model in the editor.');
 if(kind==='image'&&characterUrl){if(model!=='fal-ai/flux-pro/kontext/multi')throw Error('Select FLUX Kontext multi for product + character references');return {prompt,image_urls:[image_url,characterUrl]}}
 if(kind==='image'&&model.endsWith('/multi'))return {prompt,image_urls:[image_url]};
 if(kind==='image')return {prompt,image_url,num_images:1};
 if(model.includes('/wan/'))return {prompt,image_url,num_frames:Math.min(121,Math.max(25,seconds*24+1)),frames_per_second:24,aspect_ratio:ratio,resolution:'720p'};
 return {prompt,start_image_url:image_url,duration:String(seconds<=5?5:10),generate_audio:false};
}
