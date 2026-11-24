import test from 'node:test';
import assert from 'node:assert/strict';
import {runtimeOptions,parseOutput} from '../agent/runtime.mjs';
test('DeepSeek remains default and keeps isolated credentials',()=>{
 const r=runtimeOptions({}, {DEEPSEEK_API_KEY:'test-secret'}, {PATH:'bin',CODEX_HOME:'user-home',OPENAI_API_KEY:'never'});
 assert.equal(r.provider,'deepseek');assert.equal(r.model,'deepseek-v4-flash');
 assert.equal(r.options.env.DEEPSEEK_API_KEY,'test-secret');assert.notEqual(r.options.env.CODEX_HOME,'user-home');
 assert.equal(r.options.env.OPENAI_API_KEY,undefined);
});
test('subscription shares login home, requires ChatGPT and strips all API keys',()=>{
 const r=runtimeOptions({agentProvider:'codex',agentModel:'account-default'}, {}, {CODEX_HOME:'user-home',OPENAI_API_KEY:'never',CODEX_API_KEY:'never',DEEPSEEK_API_KEY:'never'});
 assert.equal(r.options.env.CODEX_HOME,'user-home');assert.equal(r.options.config.forced_login_method,'chatgpt');
 assert.equal(r.options.config.model_provider,'openai');assert.equal(r.model,'account-default');
 assert.equal(r.thinking,'high');
 for(const key of ['OPENAI_API_KEY','CODEX_API_KEY','DEEPSEEK_API_KEY'])assert.equal(r.options.env[key],undefined);
 assert.equal(r.options.config.features.shell_tool,false);
});
test('selected thinking reaches shared runtime without changing DeepSeek default',()=>{
 assert.equal(runtimeOptions({agentProvider:'codex',agentModel:'chosen',agentThinking:'xhigh'},{}).thinking,'xhigh');
 assert.equal(runtimeOptions({agentThinking:'high'},{DEEPSEEK_API_KEY:'test'}).thinking,'max');
});
test('invalid routing and absent model/key fail without fallback',()=>{
 assert.throws(()=>runtimeOptions({agentProvider:'unknown'},{}));
 assert.throws(()=>runtimeOptions({agentProvider:'codex'},{}));
 assert.throws(()=>runtimeOptions({},{}));
});
test('strict JSON accepts a single Markdown wrapper only',()=>{
 assert.deepEqual(parseOutput('```json\n{"ok":true}\n```'),{ok:true});
 assert.throws(()=>parseOutput('Here is JSON: {"ok":true}'));
});
