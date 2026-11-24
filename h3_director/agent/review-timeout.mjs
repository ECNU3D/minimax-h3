import {runWithProgress} from './progress.mjs';
export const REVIEW_TIMEOUT_MS=15*60*1000;
export class ReviewTimeoutError extends Error {}
export async function runVisualReview(thread,content,schema,meta,timeoutMs=REVIEW_TIMEOUT_MS){
 const signal=AbortSignal.timeout(timeoutMs);
 try{return await runWithProgress(thread,content,{outputSchema:schema,signal},'review',{...meta,timeoutMs});}
 catch(error){
  if(signal.aborted)throw new ReviewTimeoutError(`视觉审核等待超过 ${timeoutMs/60000} 分钟，未取得审核结论。已生成素材保留，可单独重新审核；图片批次将继续制作其余资产。`);
  throw error;
 }
}
