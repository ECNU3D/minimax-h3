// An unfinished audit must never discard a completed semantic parse.
import fs from 'node:fs';
import {createHash,randomUUID} from 'node:crypto';
import {runWithProgress} from './progress.mjs';

export const PARSE_TIMEOUT_MS=15*60*1000;
export function checkpointKey(input,{provider,model,thinking}){
 return createHash('sha256').update(JSON.stringify({schemaVersion:1,text:input.text,source:input.source||null,provider,model,thinking})).digest('hex');
}
export function loadCheckpoint(file,key){
 try{
  const value=JSON.parse(fs.readFileSync(file,'utf8'));
  return value.key===key && value.parsed && Array.isArray(value.parsed.assets) && Array.isArray(value.parsed.shots) ? value : null;
 }catch(error){if(error.code==='ENOENT'||error instanceof SyntaxError)return null;throw error;}
}
export function saveCheckpoint(file,key,value){
 const tmp=file+'.'+randomUUID()+'.tmp';
 try{fs.writeFileSync(tmp,JSON.stringify({...value,key,savedAt:new Date().toISOString()},null,2));fs.renameSync(tmp,file);}
 finally{if(fs.existsSync(tmp))fs.unlinkSync(tmp);}
}
export async function runParserStage(thread,input,schema,stage,meta,timeoutMs=PARSE_TIMEOUT_MS){
 const signal=AbortSignal.timeout(timeoutMs);
 try{return await runWithProgress(thread,input,{outputSchema:schema,signal},stage,{...meta,timeoutMs});}
 catch(error){
  if(signal.aborted){
   const label={parse:'原文解析',repair:'原文行号修正',audit:'独立 Agent 校对'}[stage]||stage;
   throw Error(`${label}等待超过 ${timeoutMs/60000} 分钟，已停止本次调用。${stage==='parse'?'原始文档保留。':'已完成的解析结果已保存，继续原任务将复用结果并重试未完成阶段。'}`);
  }
  throw error;
 }
}
