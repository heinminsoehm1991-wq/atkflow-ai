import 'dotenv/config';
import express from 'express';
import multer from 'multer';
import { randomUUID, timingSafeEqual } from 'node:crypto';
import { fal } from '@fal-ai/client';
const app=express();
app.disable('x-powered-by');
app.use(express.json({limit:'32kb'}));
const upload=multer({storage:multer.memoryStorage(),limits:{fileSize:20*1024*1024,files:1}});
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
app.get('/',(_,res)=>res.type('text/plain').send('ATK AI FLOW API — /api/health'));
app.get('/api/health',(_,res)=>res.json({ok:true,configured:!!process.env.FAL_KEY,imageModel:validModel(process.env.SCENE_IMAGE_MODEL_ID),videoModel:validModel(process.env.SCENE_VIDEO_MODEL_ID),adminConfigured:!!process.env.ADMIN_TOKEN}));
app.post('/api/generate',auth,upload.single('image'),async(req,res)=>{
 try{
  if(!process.env.FAL_KEY)return res.status(503).json({error:'FAL_KEY not configured'});
  const kind=req.body.kind;
  if(!['image','video'].includes(kind))return res.status(400).json({error:'Invalid kind'});
  const model=process.env[kind==='image'?'SCENE_IMAGE_MODEL_ID':'SCENE_VIDEO_MODEL_ID'];
  if(!validModel(model))return res.status(503).json({error:'Model not configured'});
  if(!req.file||!['image/jpeg','image/png','image/webp'].includes(req.file.mimetype))return res.status(400).json({error:'JPEG/PNG/WebP image required'});
  const prompt=String(req.body.prompt||'').trim().slice(0,2000);
  if(!prompt)return res.status(400).json({error:'Prompt required'});
  fal.config({credentials:process.env.FAL_KEY});
  const url=await fal.storage.upload(new Blob([req.file.buffer],{type:req.file.mimetype}));
  // Model-specific input schema must be verified for each selected model.
  const input={prompt,image_url:url};
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
  res.json({status:'COMPLETED',data:result.data});
 }catch(e){res.status(502).json({error:'Provider status failed',detail:String(e.message||e).slice(0,200)})}
});
setInterval(()=>{for(const [id,j] of jobs)if(Date.now()-j.createdAt>86400000)jobs.delete(id)},3600000).unref();
app.listen(process.env.PORT||3000,'0.0.0.0');
