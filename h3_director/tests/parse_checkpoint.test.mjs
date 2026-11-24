import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {checkpointKey,loadCheckpoint,saveCheckpoint,runParserStage,PARSE_TIMEOUT_MS} from '../agent/parse-checkpoint.mjs';
import {runVisualReview,ReviewTimeoutError,REVIEW_TIMEOUT_MS} from '../agent/review-timeout.mjs';

test('completed parse survives audit failure; source or provider changes invalidate it',()=>{
 const folder=fs.mkdtempSync(path.join(os.tmpdir(),'director-checkpoint-')),file=path.join(folder,'candidate.json');
 try{
  const input={text:'中文原文',source:{id:'source-1'}},runtime={provider:'deepseek',model:'deepseek-v4-flash',thinking:'max'};
  const key=checkpointKey(input,runtime),value={parsed:{assets:[{id:'R01',referenceAssetIds:[]}],shots:[]},threadId:'original',usage:{input_tokens:3},repairs:[]};
  saveCheckpoint(file,key,value);
  assert.deepEqual(loadCheckpoint(file,key).parsed,value.parsed);
  for(const changed of [checkpointKey({...input,text:'新稿'},runtime),checkpointKey({...input,source:{id:'source-2'}},runtime),checkpointKey(input,{...runtime,provider:'codex'}),checkpointKey(input,{...runtime,thinking:'high'})])assert.equal(loadCheckpoint(file,changed),null);
  assert.deepEqual(fs.readdirSync(folder),['candidate.json']);
  fs.writeFileSync(file,'partial');assert.equal(loadCheckpoint(file,key),null);
 }finally{fs.rmSync(folder,{recursive:true,force:true});}
});
test('audit timeout is bounded and explains checkpoint recovery',async()=>{
 assert.equal(PARSE_TIMEOUT_MS,900000);
 const keepAlive=setInterval(()=>{},1000);
 try{
  const thread={runStreamed:async(_,options)=>{await new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>reject(Error('The operation was aborted')),{once:true}));}};
  await assert.rejects(runParserStage(thread,'private',{},'audit',{model:'test'},5),/独立 Agent 校对.*解析结果已保存/);
 }finally{clearInterval(keepAlive);}
});

test('visual review timeout is distinct from an execution error or quality verdict',async()=>{
 assert.equal(REVIEW_TIMEOUT_MS,900000);
 const keepAlive=setInterval(()=>{},1000);
 try{
  const thread={runStreamed:async(_,options)=>{await new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>reject(Error('The operation was aborted')),{once:true}));}};
  await assert.rejects(runVisualReview(thread,[],{}, {model:'test'},5),ReviewTimeoutError);
  const broken={runStreamed:async()=>{throw Error('missing image');}};
  await assert.rejects(runVisualReview(broken,[],{},{}),error=>!(error instanceof ReviewTimeoutError)&&error.message==='missing image');
 }finally{clearInterval(keepAlive);}
});
