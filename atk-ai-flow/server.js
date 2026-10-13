import 'dotenv/config';
import express from 'express';
import multer from 'multer';
import { fal } from '@fal-ai/client';
const app=express();
app.disable('x-powered-by');
app.use(express.json({limit:'32kb'}));
const upload=multer({storage:multer.memoryStorage(),limits:{fileSize:20*1024*1024}});
const jobs=new Map();
const validModel=s=>typeof s==='string'&&/^[\w.-]+\/[\w./-]+$/.test(s);
app.get('/api/health',(_,res)=>res.json({ok:true,configured:!!process.env.FAL_KEY,imageModel:!!process.env.SCENE_IMAGE_MODEL_ID,videoModel:!!process.env.SCENE_VIDEO_MODEL_ID}));
app.post('/api/generate',upload.single('image'),async(req,res)=>{
 try{
  if(!process.env.FAL_KEY)return res.status(503).json({error:'FAL_KEY not configured'});
  const kind=req.body.kind;
  if(!['image','video'].includes(kind))return res.status(400).json({error:'Invalid kind'});
  const model=process.env[kind==='image'?'SCENE_IMAGE_MODEL_ID':'SCENE_VIDEO_MODEL_ID'];
  if(!validModel(model))return res.status(503).json({error:'Model not configured'});
  if(!req.file||!req.file.mimetype.startsWith('image/'))return res.status(400).json({error:'Image upload required'});
  const prompt=String(req.body.prompt||'').trim().slice(0,2000);
  if(!prompt)return res.status(400).json({error:'Prompt required'});
  fal.config({credentials:process.env.FAL_KEY});
  const url=await fal.storage.upload(new Blob([req.file.buffer],{type:req.file.mimetype}));
  const input={prompt,image_url:url};
  const job=await fal.queue.submit(model,{input});
  const id=crypto.randomUUID();
  jobs.set(id,{model,requestId:job.request_id});
  res.json({jobId:id,status:'IN_QUEUE'});
 }catch(e){res.status(502).json({error:'AI provider request failed',detail:String(e.message||e).slice(0,200)})}
});
app.get('/api/jobs/:id',async(req,res)=>{
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
app.listen(process.env.PORT||3000,'0.0.0.0');
