// Shared model routing for document parsing, independent audit and visual review.
import {Codex} from '@openai/codex-sdk';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const app=path.dirname(path.dirname(fileURLToPath(import.meta.url)));
export function parseOutput(text){
 const trimmed=text.trim();
 return JSON.parse(trimmed.startsWith('```')?trimmed.replace(/^```(?:json)?\s*\n/,'').replace(/\n```$/,''):trimmed);
}
export function readConfig(){
 const cfg={},file=path.join(path.dirname(app),'.env');
 if(fs.existsSync(file))for(const line of fs.readFileSync(file,'utf8').split(/\r?\n/)){
  const m=line.match(/^\s*(\w+)\s*=\s*(.*?)\s*$/);if(m)cfg[m[1]]=m[2].replace(/^['"]|['"]$/g,'');
 }
 return cfg;
}
export function runtimeOptions(input,cfg,processEnv=process.env){
 const provider=input.agentProvider||'deepseek';
 if(!['deepseek','codex'].includes(provider))throw Error('未知导演 Agent');
 const env=Object.fromEntries(['PATH','Path','SystemRoot','WINDIR','TEMP','TMP','USERPROFILE','HOME','APPDATA','LOCALAPPDATA','COMSPEC','PATHEXT','CODEX_CA_CERTIFICATE','SSL_CERT_FILE'].filter(k=>processEnv[k]).map(k=>[k,processEnv[k]]));
 const config={features:{shell_tool:false,unified_exec:false,apply_patch_freeform:false,apps:false,image_generation:false},project_doc_max_bytes:0,web_search:'disabled',history:{persistence:'none'}};
 let model;
 if(provider==='codex'){
  if(!input.agentModel)throw Error('缺少已验证的 Codex 订阅模型，请从导演台提交任务');
  model=input.agentModel;
  if(processEnv.CODEX_HOME)env.CODEX_HOME=processEnv.CODEX_HOME;
  Object.assign(config,{model_provider:'openai',model,forced_login_method:'chatgpt'});
 }else{
  if(!cfg.DEEPSEEK_API_KEY)throw Error('缺少 DEEPSEEK_API_KEY');
  model=cfg.DEEPSEEK_MODEL||'deepseek-v4-flash';
  env.CODEX_HOME=path.join(app,'data','reviewer-runtime');env.DEEPSEEK_API_KEY=cfg.DEEPSEEK_API_KEY;
  Object.assign(config,{model_provider:'deepseek',model,model_providers:{deepseek:{name:'DeepSeek',base_url:cfg.DEEPSEEK_BASE_URL||'https://api.deepseek.com',env_key:'DEEPSEEK_API_KEY',wire_api:'responses',request_max_retries:0,stream_max_retries:0}}});
 }
 const thinking=provider==='codex'?(input.agentThinking||'high'):'max';
 return {provider,model,thinking,options:{env,config}};
}
export function createRuntime(input,cfg){
 const runtime=runtimeOptions(input,cfg);
 if(runtime.provider==='deepseek')fs.mkdirSync(runtime.options.env.CODEX_HOME,{recursive:true});
 return {...runtime,codex:new Codex(runtime.options)};
}
