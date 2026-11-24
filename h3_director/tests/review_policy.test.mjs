import test from 'node:test';
import assert from 'node:assert/strict';
import {validateRetryDecision} from '../agent/review-policy.mjs';
const base={verdict:'revise',retryAction:'reroll',retryReason:'原提示词明确，随机畸变',revisedPrompt:'',revisedViewPrompts:[]};
test('reroll leaves prompts empty and revision accepts Chinese prompts',()=>{
 assert.equal(validateRetryDecision({...base}).retryAction,'reroll');
 assert.equal(validateRetryDecision({...base,retryAction:'revise_prompt',revisedPrompt:'单人全身正面',revisedViewPrompts:['侧面','背面']}).retryAction,'revise_prompt');
});
test('human/pass cannot request retries; no action can carry hidden changes',()=>{
 for(const verdict of ['pass','human'])assert.throws(()=>validateRetryDecision({...base,verdict}));
 assert.throws(()=>validateRetryDecision({...base,revisedPrompt:'隐藏修改'}));
 assert.throws(()=>validateRetryDecision({...base,retryAction:'none',revisedViewPrompts:['侧','背']}));
 assert.equal(validateRetryDecision({...base,verdict:'human',retryAction:'none'}).retryAction,'none');
});
test('invalid action, missing reason, incomplete revision are rejected',()=>{
 for(const delta of [{retryAction:'retry'},{retryReason:''},{retryAction:'revise_prompt'},{retryAction:'revise_prompt',revisedPrompt:'正面',revisedViewPrompts:['侧面']}])assert.throws(()=>validateRetryDecision({...base,...delta}));
});
