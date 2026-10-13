export const MAX_SECONDS=3600;
export const MAX_SCENES=720;
export function planDuration(total,clip=5){
 if(!Number.isInteger(total)||total<1||total>MAX_SECONDS)throw Error('Choose a duration from 1 second to 60 minutes');
 if(!Number.isInteger(clip)||clip<1||clip>5)throw Error('Scene clip length must be 1–5 seconds');
 const count=Math.ceil(total/clip);
 if(count>MAX_SCENES)throw Error('Maximum 720 scenes; increase scene clip length');
 return Array.from({length:count},(_,i)=>Math.min(clip,total-i*clip));
}
