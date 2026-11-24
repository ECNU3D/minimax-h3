import React,{useEffect,useState} from 'react';

export default function AgentSettings({value,onChange,disabled=false}){
 const provider=value.agentProvider||'deepseek',model=value.agentModel||'gpt-5.6-sol',thinking=value.agentThinking||'high';
 const [models,setModels]=useState([]),[error,setError]=useState(''),[loading,setLoading]=useState(false),[refresh,setRefresh]=useState(0);
 useEffect(()=>{
  if(provider!=='codex')return;
  let cancelled=false;setLoading(true);setError('');
  fetch('/api/codex/models').then(async r=>{const d=await r.json();if(!r.ok)throw Error(d.error||'模型列表读取失败');return d.models}).then(m=>{if(!cancelled)setModels(m)}).catch(e=>{if(!cancelled)setError(e.message)}).finally(()=>{if(!cancelled)setLoading(false)});
  return ()=>{cancelled=true};
 },[provider,refresh]);
 const selected=models.find(m=>m.id===model),efforts=selected?.thinking||[];
 return <div className="agent-select">
  <label>导演 Agent<select aria-label="导演 Agent" value={provider} disabled={disabled} onChange={e=>onChange({agentProvider:e.target.value})}><option value="deepseek">DeepSeek · 默认</option><option value="codex">Codex 订阅</option></select></label>
  {provider==='codex'&&<>
   <label>Codex 模型<select aria-label="Codex 模型" value={model} disabled={disabled||loading||!!error} onChange={e=>{const next=models.find(m=>m.id===e.target.value);onChange({agentModel:next.id,agentThinking:next.thinking.includes(thinking)?thinking:next.thinking.includes('high')?'high':next.thinking[0]})}}>
    {!selected&&<option value={model}>{model}{loading?' · 读取中…':' · 待验证'}</option>}{models.map(m=><option key={m.id} value={m.id}>{m.name}</option>)}
   </select></label>
   <label>Thinking level<select aria-label="Thinking level" value={thinking} disabled={disabled||loading||!selected} onChange={e=>onChange({agentThinking:e.target.value})}>
    {!efforts.includes(thinking)&&<option value={thinking}>{thinking} · 待验证</option>}{efforts.map(e=><option key={e} value={e}>{e.charAt(0).toUpperCase()+e.slice(1)}</option>)}
   </select></label>
   {error&&<small role="alert">{error} <button type="button" className="small" onClick={()=>setRefresh(x=>x+1)}>重试</button></small>}
  </>}
  <small>{provider==='codex'?'使用当前账户的订阅额度；选项随模型支持能力变化。':'使用本机配置的 DeepSeek · Thinking Max（最高）。'}解析、校对和审片共用此设置。</small>
 </div>;
}
