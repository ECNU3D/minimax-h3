import test from 'node:test';
import assert from 'node:assert/strict';
import {runWithProgress} from '../agent/progress.mjs';
const thread=events=>({runStreamed:async()=>({events:(async function*(){for(const e of events)yield e;})()})});
test('stream preserves final response and usage without logging model text',async()=>{
 const rows=[],usage={input_tokens:10,output_tokens:20};
 const result=await runWithProgress(thread([{type:'thread.started',thread_id:'thread-1'},{type:'item.completed',item:{type:'reasoning',text:'PRIVATE reasoning'}},{type:'item.completed',item:{type:'agent_message',text:'PRIVATE output'}},{type:'turn.completed',usage}]),'secret prompt',{},'parse',{},(...args)=>rows.push(args));
 assert.equal(result.finalResponse,'PRIVATE output');assert.deepEqual(result.usage,usage);
 assert.ok(!JSON.stringify(rows).includes('PRIVATE'));assert.ok(!JSON.stringify(rows).includes('secret'));
 assert.equal(rows[1][2].threadId,'thread-1');
});
test('failed and truncated streams fail instead of accepting partial JSON',async()=>{
 for(const events of [[{type:'turn.failed',error:{message:'rate limit'}}],[{type:'item.completed',item:{type:'agent_message',text:'partial'}}]]){
  const rows=[];await assert.rejects(runWithProgress(thread(events),'',{},'parse',{},(...args)=>rows.push(args)));
  assert.equal(rows.at(-1)[1],'failed');
 }
});
