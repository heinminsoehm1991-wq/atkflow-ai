import 'dotenv/config';
import express from 'express';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import multer from 'multer';
import { randomUUID, timingSafeEqual } from 'node:crypto';
import { models, modelInput } from './models.js';
import { binary, validateClips, mergeClips } from './render.js';
import { access, rm } from 'node:fs/promises';
import os from 'node:os';
import { fal } from '@fal-ai/client';
const app=express();
app.disable('x-powered-by');
app.use(express.json({limit:'128kb'}));
const upload=multer({storage:multer.memoryStorage(),limits:{fileSize:20*1024*1024,files:2}});
const jobs=new Map();
const validModel=s=>typeof s==='string'&&/^[\w.-]+\/[\w./-]+$/.test(s);
const authorized=req=>{
 const token=process.env.ADMIN_TOKEN;
 const supplied=req.get('x-admin-token')||'';
 if(!token||!supplied)return false;
 const a=Buffer.from(token),b=Buffer.from(supplied);
 return a.length===b.length&&timingSafeEqual(a,b);
};
const auth=(req,res,next)=>authorized(req)?next():res.status(401).json({error:'Admin token required'});
app.use(express.static(path.join(path.dirname(fileURLToPath(import.meta.url)),'public')));
app.get('/api/health',(_,res)=>res.json({ok:true,configured:!!process.env.FAL_KEY,imageModel:validModel(process.env.SCENE_IMAGE_MODEL_ID),videoModel:validModel(process.env.SCENE_VIDEO_MODEL_ID),adminConfigured:!!process.env.ADMIN_TOKEN}));
app.get('/api/models',(_,res)=>res.json({models,defaults:{image:models.image.includes(process.env.SCENE_IMAGE_MODEL_ID)?process.env.SCENE_IMAGE_MODEL_ID:models.image[0],video:models.video.includes(process.env.SCENE_VIDEO_MODEL_ID)?process.env.SCENE_VIDEO_MODEL_ID:models.video[0]}}));
app.post('/api/prompts',auth,async(req,res)=>{
 try{if(!process.env.FAL_KEY)return res.status(503).json({error:'FAL_KEY not configured'});if(req.body.costApproved!==true)return res.status(400).json({error:'Approve fal.ai charges first'});const count=Number(req.body.count),brief=String(req.body.brief||'').trim().slice(0,2000);if(!Number.isInteger(count)||count<1||count>120||!brief)return res.status(400).json({error:'Brief and 1–120 scenes required'});fal.config({credentials:process.env.FAL_KEY});const job=await fal.queue.submit('openrouter/router',{input:{model:process.env.PROMPT_MODEL_ID||'google/gemini-2.5-flash',prompt:`Create exactly ${count} distinct, coherent product advertisement scene prompts based on this brief: ${brief}. Product reference is image 1; optional character is image 2. Preserve product and character identity. Include camera, setting, lighting and motion. Return only a JSON array of ${count} strings, no markdown.`,max_tokens:Math.min(16000,count*120),enable_web_search:false}});const id=randomUUID();jobs.set(id,{model:'openrouter/router',requestId:job.request_id,createdAt:Date.now()});res.json({jobId:id})}catch(e){res.status(502).json({error:'AI prompt request failed'})}
});
app.post('/api/generate',auth,upload.fields([{name:'image',maxCount:1},{name:'character',maxCount:1}]),async(req,res)=>{
 try{
  if(!process.env.FAL_KEY)return res.status(503).json({error:'FAL_KEY not configured'});
  req.file=req.files?.image?.[0];
  const character=req.files?.character?.[0];
  if(character&&!['image/jpeg','image/png','image/webp'].includes(character.mimetype))return res.status(400).json({error:'Character must be JPEG/PNG/WebP'});
  const kind=req.body.kind;
  if(!['image','video'].includes(kind))return res.status(400).json({error:'Invalid kind'});
  const model=req.body.model||process.env[kind==='image'?'SCENE_IMAGE_MODEL_ID':'SCENE_VIDEO_MODEL_ID'];
  if(!models[kind].includes(model))return res.status(400).json({error:'Unsupported model; select a verified model'});
  if(req.body.costApproved!=='true')return res.status(400).json({error:'Confirm fal.ai charges before generation'});
  const seconds=Number(req.body.seconds||5);
  if(!Number.isInteger(seconds)||seconds<1||seconds>10)return res.status(400).json({error:'Invalid scene duration'});
  if(!validModel(model))return res.status(503).json({error:'Model not configured'});
  if(!req.file||!['image/jpeg','image/png','image/webp'].includes(req.file.mimetype))return res.status(400).json({error:'JPEG/PNG/WebP image required'});
  const prompt=String(req.body.prompt||'').trim().slice(0,2000);
  if(!prompt)return res.status(400).json({error:'Prompt required'});
  fal.config({credentials:process.env.FAL_KEY});
  const url=await fal.storage.upload(new Blob([req.file.buffer],{type:req.file.mimetype}));
  const input=modelInput(kind,model,prompt,url,seconds,req.body.ratio,character?await fal.storage.upload(new Blob([character.buffer],{type:character.mimetype})):undefined);
  const job=await fal.queue.submit(model,{input});
  const id=randomUUID();
  jobs.set(id,{model,requestId:job.request_id,createdAt:Date.now()});
  res.json({jobId:id,status:'IN_QUEUE'});
 }catch(e){res.status(502).json({error:'AI provider request failed',detail:String(e.message||e).slice(0,200)})}
});
app.get('/api/jobs/:id',auth,async(req,res)=>{
 const j=jobs.get(req.params.id);
 if(!j)return res.status(404).json({error:'Job not found'});
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
setInterval(()=>{for(const [id,j] of jobs)if(Date.now()-j.createdAt>86400000)jobs.delete(id)},3600000).unref();

const renders=new Map();let rendering=false;
const renderRoot=path.join(os.tmpdir(),'atk-ai-flow-renders');
app.post('/api/render',auth,async(req,res)=>{
 try{
  const total=validateClips(req.body.clips);
  if(total!==Number(req.body.targetSeconds))return res.status(400).json({error:'Connected scene durations must match target duration'});
  if(rendering)return res.status(409).json({error:'A render is running; try again after it finishes'});
  const clips=req.body.clips.map(c=>{const job=jobs.get(c.jobId);if(!job?.outputUrl||!job.model.includes('image-to-video'))throw Error('Each connected video must be a completed job from this server');const u=new URL(job.outputUrl);if(u.protocol!=='https:'||!(u.hostname.endsWith('.fal.media')||u.hostname==='storage.googleapis.com'))throw Error('Unsupported output host');return {source:u.href,seconds:c.seconds}});
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
