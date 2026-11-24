// Opt-in SDK wire verification with a loopback mock, no external API or credentials.
import http from 'node:http';
import assert from 'node:assert/strict';
import {createRuntime} from '../agent/runtime.mjs';
let observed;
const server=http.createServer((req,res)=>{let data='';req.on('data',c=>data+=c);req.on('end',()=>{const body=JSON.parse(data);observed={model:body.model,reasoning:body.reasoning};res.writeHead(400,{'Content-Type':'application/json'});res.end(JSON.stringify({error:{message:'intentional wire test stop',type:'invalid_request_error'}}));});});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
try{
 const {codex,model,thinking}=createRuntime({}, {DEEPSEEK_API_KEY:'test-only',DEEPSEEK_BASE_URL:`http://127.0.0.1:${server.address().port}`});
 const thread=codex.startThread({model,modelReasoningEffort:thinking,skipGitRepoCheck:true,sandboxMode:'read-only',approvalPolicy:'never'});
 try{await thread.run('Return OK',{signal:AbortSignal.timeout(20000)});}catch{}
 assert.equal(observed?.reasoning?.effort,'max');console.log(JSON.stringify({status:'passed',...observed}));
}finally{server.closeAllConnections();server.close();}
