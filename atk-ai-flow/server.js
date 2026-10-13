import 'dotenv/config';
import express from 'express';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import multer from 'multer';
import { randomUUID, timingSafeEqual } from 'node:crypto';
import { models, modelInput } from './models.js';
import { binary, validateClips, mergeClips } from './render.js';
import { access, rm, mkdir, writeFile } from 'node:fs/promises';
import os from 'node:os';
import {isGoogle,makeGoogle,imageRequest,videoRequest,googlePrompt,googleImage,googleVideo} from './gemini.js';
import { fal } from '@fal-ai/client';
const app=express();
app.disable('x-powered-by');
app.use(express.json({limit:'128kb'}));
const upload=multer({storage:multer.memoryStorage(),limits:{fileSize:20*1024*1024,files:2}});
const jobs=new Map();
const mediaRoot=path.join(os.tmpdir(),'atk-ai-flow-google');
function startGoogle(model,kind,task){
 if([...jobs.values()].filter(j=>j.provider==='google'&&j.status==='IN_PROGRESS').length>=4)throw Error('Wait for current Gemini jobs to finish.');
 const id=randomUUID(),j={provider:'google',model,kind,status:'IN_PROGRESS',createdAt:Date.now()};jobs.set(id,j);
 Promise.resolve().then(()=>task(j,id)).then(data=>{j.data=data;j.status='COMPLETED'}).catch(e=>{j.status='FAILED';j.error=safeDetail(e);console.error(JSON.stringify({event:'google_request_failed',stage:kind,detail:j.error}));});return id;
}
const validModel=s=>typeof s==='string'&&/^[\w.-]+\/[\w./-]+$/.test(s);
const authorized=req=>{
 const token=process.env.ADMIN_TOKEN;
 const supplied=req.get('x-admin-token')||'';
 if(!token||!supplied)return false;
 const a=Buffer.from(token),b=Buffer.from(supplied);
 return a.length===b.length&&timingSafeEqual(a,b);
};
const auth=(req,res,next)=>authorized(req)?next():res.status(401).json({error:'Admin token required'});
function safeDetail(e){let detail=String(e.body?.detail||e.body?.message||e.message||'Unknown provider error');for(const key of [process.env.GEMINI_API_KEY,process.env.FAL_KEY,process.env.ADMIN_TOKEN])if(key)detail=detail.split(key).join('[redacted]');return detail.replace(/https?:\/\/\S+/g,'[provider URL]').slice(0,350)}
function providerFailure(res,e,stage){
 const status=Number(e.status||e.statusCode)||502;
 const detail=safeDetail(e);
 console.error(JSON.stringify({event:'fal_request_failed',stage,status,detail}));
 res.status(502).json({error:'AI provider request failed',providerStatus:status,detail});
}
app.use(express.static(path.join(path.dirname(fileURLToPath(import.meta.url)),'public')));
let googleHealthCheck;
async function verifyGoogleAccess(){
 if(!googleHealthCheck||Date.now()>googleHealthCheck.expires){googleHealthCheck={expires:Date.now()+60000,promise:(async()=>{try{const ai=makeGoogle(),names=[];for await(const m of await ai.models.list({config:{pageSize:100}}))names.push(m.name?.replace('models/',''));return {keyValid:true,prompt:names.includes(process.env.GEMINI_PROMPT_MODEL||'gemini-2.5-flash'),image:names.includes('gemini-2.5-flash-image'),video:names.includes('veo-3.1-fast-generate-preview'),generationTested:false,billingVerified:false}}catch(e){return {keyValid:false,status:Number(e.status||e.statusCode)||502,generationTested:false,billingVerified:false}}})()}}return googleHealthCheck.promise;
}
app.get('/api/health',async(req,res)=>res.json({ok:true,provider:'Gemini',configured:!!process.env.GEMINI_API_KEY,imageModel:true,videoModel:true,adminConfigured:!!process.env.ADMIN_TOKEN,...(req.query.verify==='1'?{connection:await verifyGoogleAccess()}:{})}));
app.get('/api/models',(_,res)=>res.json({models,defaults:{image:models.image[0],video:models.video[0]}}));
app.get('/api/connection',auth,async(req,res)=>{try{const ai=makeGoogle();const available=[];for await(const m of await ai.models.list({config:{pageSize:100}}))available.push(m.name?.replace('models/',''));res.json({ok:true,provider:'Gemini',image:available.filter(m=>models.image.some(s=>s==='google/'+m)),video:available.filter(m=>models.video.some(s=>s==='google/'+m)),prompt:available.includes(process.env.GEMINI_PROMPT_MODEL||'gemini-2.5-flash'),billingVerified:false})}catch(e){providerFailure(res,e,'connection')}});
app.get('/api/media/:id',(req,res)=>{const j=jobs.get(req.params.id);if(j?.status!=='COMPLETED'||!j.outputPath)return res.status(404).end();res.set('Cache-Control','private, max-age=300');res.type(j.mime).sendFile(j.outputPath)});
app.post('/api/prompts',auth,async(req,res)=>{
 try{if(req.body.provider!=='fal'){if(req.body.costApproved!==true)return res.status(400).json({error:'Approve Gemini API charges first'});const count=Number(req.body.count),brief=String(req.body.brief||'').trim().slice(0,2000);if(!Number.isInteger(count)||count<1||count>60||!brief)return res.status(400).json({error:'Brief and 1–60 scenes required'});const ai=makeGoogle();return res.json({jobId:startGoogle('google/gemini-2.5-flash','prompts',()=>googlePrompt(ai,brief,count,Math.max(1,Number(req.body.start)||1),Math.max(count,Math.min(720,Number(req.body.total)||count))))})}if(!process.env.FAL_KEY)return res.status(503).json({error:'FAL_KEY not configured'});if(req.body.costApproved!==true)return res.status(400).json({error:'Approve fal.ai charges first'});const count=Number(req.body.count),brief=String(req.body.brief||'').trim().slice(0,2000);if(!Number.isInteger(count)||count<1||count>60||!brief)return res.status(400).json({error:'Brief and 1–60 scenes per prompt batch required'});fal.config({credentials:process.env.FAL_KEY});const job=await fal.queue.submit('openrouter/router',{input:{model:process.env.PROMPT_MODEL_ID||'google/gemini-2.5-flash',prompt:`Create exactly ${count} distinct, coherent product advertisement scene prompts based on this brief: ${brief}. This batch starts at scene ${Math.max(1,Number(req.body.start)||1)} of ${Math.max(count,Math.min(720,Number(req.body.total)||count))} total scenes. Product reference is image 1; optional character is image 2. Preserve product and character identity. Include camera, setting, lighting and motion. Return only a JSON array of ${count} strings, no markdown.`,max_tokens:Math.min(16000,count*120),enable_web_search:false}});const id=randomUUID();jobs.set(id,{model:'openrouter/router',requestId:job.request_id,createdAt:Date.now()});res.json({jobId:id})}catch(e){providerFailure(res,e,'prompts')}
});
app.post('/api/generate',auth,upload.fields([{name:'image',maxCount:1},{name:'character',maxCount:1}]),async(req,res)=>{
 try{
  req.file=req.files?.image?.[0];
  const character=req.files?.character?.[0];
  if(character&&!['image/jpeg','image/png','image/webp'].includes(character.mimetype))return res.status(400).json({error:'Character must be JPEG/PNG/WebP'});
  const kind=req.body.kind;
  if(!['image','video'].includes(kind))return res.status(400).json({error:'Invalid kind'});
  const model=req.body.model||models[kind][0];
  if(!models[kind].includes(model))return res.status(400).json({error:'Unsupported model; select a verified model'});
  if(req.body.costApproved!=='true')return res.status(400).json({error:'Confirm AI API charges before generation'});
  const seconds=Number(req.body.seconds||5);
  if(!Number.isInteger(seconds)||seconds<1||seconds>10)return res.status(400).json({error:'Invalid scene duration'});
  if(!validModel(model))return res.status(503).json({error:'Model not configured'});
  if(!req.file||!['image/jpeg','image/png','image/webp'].includes(req.file.mimetype))return res.status(400).json({error:'JPEG/PNG/WebP image required'});
  const prompt=String(req.body.prompt||'').trim().slice(0,2000);
  if(!prompt)return res.status(400).json({error:'Prompt required'});
  if(isGoogle(model)){
   const ai=makeGoogle();
   const request=kind==='image'?imageRequest(model,prompt,req.file,character,req.body.ratio||'16:9'):videoRequest(model,prompt,req.file,seconds,req.body.ratio||'16:9');
   const id=startGoogle(model,kind,async(j,id)=>{await mkdir(mediaRoot,{recursive:true});j.outputPath=path.join(mediaRoot,id+(kind==='image'?'.png':'.mp4'));if(kind==='image'){const output=await googleImage(ai,request);j.mime=output.mime;await writeFile(j.outputPath,output.buffer)}else{j.mime='video/mp4';await googleVideo(ai,request,j.outputPath)}j.outputUrl='/api/media/'+id;return kind==='image'?{images:[{url:j.outputUrl}]}:{video:{url:j.outputUrl}}});
   return res.json({jobId:id,status:'IN_QUEUE'});
  }
  if(!process.env.FAL_KEY)return res.status(503).json({error:'FAL_KEY not configured'});
  fal.config({credentials:process.env.FAL_KEY});
  const url=await fal.storage.upload(new Blob([req.file.buffer],{type:req.file.mimetype}));
  const input=modelInput(kind,model,prompt,url,seconds,req.body.ratio,character?await fal.storage.upload(new Blob([character.buffer],{type:character.mimetype})):undefined);
  const job=await fal.queue.submit(model,{input});
  const id=randomUUID();
  jobs.set(id,{model,requestId:job.request_id,createdAt:Date.now()});
  res.json({jobId:id,status:'IN_QUEUE'});
 }catch(e){providerFailure(res,e,'generation')}
});
app.get('/api/jobs/:id',auth,async(req,res)=>{
 const j=jobs.get(req.params.id);
 if(!j)return res.status(404).json({error:'Job not found'});
 if(j.provider==='google'){if(j.status==='FAILED')return res.status(502).json({error:j.error});return res.json({status:j.status,data:j.data})}
 try{
  fal.config({credentials:process.env.FAL_KEY});
  const status=await fal.queue.status(j.model,{requestId:j.requestId});
  if(status.status!=='COMPLETED')return res.json({status:status.status});
  const result=await fal.queue.result(j.model,{requestId:j.requestId});
  const url=j.model.includes('image-to-video')?result.data?.video?.url:result.data?.images?.[0]?.url;
  j.outputUrl=url;
  res.json({status:'COMPLETED',data:result.data});
 }catch(e){res.status(502).json({error:'Provider status failed',detail:String(e.message||e).slice(0,200)})}
});
setInterval(()=>{for(const [id,j] of jobs)if(Date.now()-j.createdAt>86400000&&j.status!=='IN_PROGRESS'){jobs.delete(id);if(j.outputPath)rm(j.outputPath,{force:true}).catch(()=>{})}},3600000).unref();

const renders=new Map();let rendering=false;
const renderRoot=path.join(os.tmpdir(),'atk-ai-flow-renders');
app.post('/api/render',auth,async(req,res)=>{
 try{
  const total=validateClips(req.body.clips);
  if(total!==Number(req.body.targetSeconds))return res.status(400).json({error:'Connected scene durations must match target duration'});
  if(rendering)return res.status(409).json({error:'A render is running; try again after it finishes'});
  const clips=req.body.clips.map(c=>{const job=jobs.get(c.jobId);if(!job?.outputUrl||!(job.kind==='video'||job.model.includes('image-to-video')))throw Error('Each connected video must be a completed job from this server');if(job.provider==='google'&&job.outputPath)return {source:job.outputPath,seconds:c.seconds};const u=new URL(job.outputUrl);if(u.protocol!=='https:'||!(u.hostname.endsWith('.fal.media')||u.hostname==='storage.googleapis.com'))throw Error('Unsupported output host');return {source:u.href,seconds:c.seconds}});
  await access(binary);const id=randomUUID(),dir=path.join(renderRoot,id);const j={status:'IN_PROGRESS',progress:0,totalSeconds:total,createdAt:Date.now(),dir};renders.set(id,j);rendering=true;
  res.status(202).json({renderId:id});
  mergeClips(clips,dir,req.body.ratio,(n,count)=>j.progress=Math.round(n/count*95)).then(()=>{j.status='COMPLETED';j.progress=100}).catch(e=>{j.status='FAILED';j.error=e.message;rm(dir,{recursive:true,force:true})}).finally(()=>rendering=false);
 }catch(e){res.status(400).json({error:e.message})}
});
app.get('/api/renders/:id',auth,(req,res)=>{const j=renders.get(req.params.id);if(!j)return res.status(404).json({error:'Render not found (server may have restarted)'});res.json({status:j.status,progress:j.progress,error:j.error,totalSeconds:j.totalSeconds})});
app.get('/api/renders/:id/download',auth,(req,res)=>{const j=renders.get(req.params.id);if(j?.status!=='COMPLETED')return res.status(404).json({error:'MP4 not ready'});res.download(path.join(j.dir,'final.mp4'),'ATK-AI-FLOW.mp4')});
setInterval(()=>{for(const [id,j] of renders)if(j.status!=='IN_PROGRESS'&&Date.now()-j.createdAt>3600000){renders.delete(id);rm(j.dir,{recursive:true,force:true})}},60000).unref();
app.use((err,req,res,next)=>res.status(400).json({error:err.code==='LIMIT_FILE_SIZE'?'Image maximum size is 20 MB':'Invalid request'}));

app.listen(process.env.PORT||3000,'0.0.0.0');
