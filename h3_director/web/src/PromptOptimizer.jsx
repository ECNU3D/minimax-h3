import React,{useEffect,useState} from 'react';
import './prompt-optimizer.css';
const names={queued:'等待优化',running:'DeepSeek 优化中',ready:'待比较',applied:'已采用',rolled_back:'已回退',failed:'优化失败'};
const text=fields=>fields&&('soundscape' in fields?fields.prompt+'\noverall_soundscape:\n'+fields.soundscape+'\nnon_diegetic_music:\n'+fields.music:fields.prompt);

export default function PromptOptimizer({api,scope,owner,target,dirty,blocked,onPrepare,onChanged,defaultLanguage='zh'}){
 const [rows,setRows]=useState([]),[selected,setSelected]=useState(''),[language,setLanguage]=useState(defaultLanguage),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const url=`prompt-optimizations/${scope}/${owner}/${target}`;
 const refresh=async()=>{const next=await api(url);setRows(next);return next};
 useEffect(()=>{let alive=true;const load=()=>api(url).then(next=>{if(alive)setRows(next)}).catch(e=>{if(alive)setError(e.message)});load();const timer=setInterval(load,3000);return()=>{alive=false;clearInterval(timer)}},[url]);
 const act=async action=>{setBusy(true);setError('');try{await action()}catch(e){setError(e.message)}finally{setBusy(false)}};
 const current=rows.find(r=>r.id===selected)||(selected==='hidden'?null:rows[0]);
 const active=rows.some(r=>['queued','running'].includes(r.status));
 const optimize=()=>act(async()=>{const revision=await onPrepare();const row=await api('prompt-optimizations',{scope,owner,target,revision,language});setRows(xs=>[row,...xs]);setSelected(row.id)});
 const adopt=action=>act(async()=>{await api(`prompt-optimizations/${current.id}/${action}`,{});await onChanged();await refresh()});
 return <section className="prompt-optimizer">
  <div className="optimizer-heading"><b>官方 Skill · 提示词优化</b><a href="https://github.com/MiniMax-AI/MiniMax-H3/tree/main/skills/h3-prompt-writing" target="_blank" rel="noreferrer">查看来源 ↗</a></div>
  <p>DeepSeek 按官方 H3 指南生成候选，先比较再采用。只优化文字，不生成视频；中文正文沿用你的偏好，台词保留原文。</p>
  <div className="optimizer-actions optimizer-toolbar"><label>优化正文语言<select aria-label="优化正文语言" value={language} disabled={busy||active} onChange={e=>setLanguage(e.target.value)}><option value="zh">中文</option><option value="en">English</option></select></label><button disabled={busy||active||blocked} onClick={optimize}>{active?'DeepSeek 正在优化…':'DeepSeek 优化提示词'}</button></div>
  {dirty&&<small>开始优化会先保存当前修改；采用或回退前，请先保存手动编辑。</small>}
  {error&&<p className="warning" role="alert">{error}</p>}
  {rows.length>0&&<label>优化记录<select aria-label="提示词优化记录" value={current?.id||'hidden'} onChange={e=>setSelected(e.target.value)}><option value="hidden">收起对比</option>{rows.map(r=><option key={r.id} value={r.id}>{new Date(r.created*1000).toLocaleString('zh-CN')} · {names[r.status]} · {r.language==='zh'?'中文':'English'}</option>)}</select></label>}
  {current&&<div className="optimizer-result"><p><b>{names[current.status]}</b>{current.model?' · '+current.model:''}</p>{current.error&&<p role="alert">{current.error}</p>}
   {current.candidate&&<><div className="optimizer-comparison"><div><b>优化前</b><pre>{text(current.source.fields)}</pre></div><div><b>优化后候选</b><pre>{text(current.candidate)}</pre></div></div>
    <details><summary>逐行差异（− 删除 / + 新增）</summary><pre>{current.diff.map((line,i)=><span key={i} className={line.startsWith('+')?'diff-add':line.startsWith('-')?'diff-remove':''}>{line+'\n'}</span>)}</pre></details>
    <ul>{current.changes.map((c,i)=><li key={i}>{c}</li>)}</ul>{current.warnings.map((w,i)=><p className="warning" key={i}>{w}</p>)}
    <div className="optimizer-footer">
    <div className="optimizer-actions">{current.status==='ready'&&<><button className="primary" disabled={busy||dirty||blocked} onClick={()=>adopt('apply')}>采用优化版</button><button onClick={()=>setSelected('hidden')}>暂不采用</button></>}{current.status==='applied'&&<button disabled={busy||dirty||blocked} onClick={()=>adopt('rollback')}>回退到优化前</button>}</div>
    <small>采用与回退均保存历史。若之后改过提示词、时长或参考素材，会阻止覆盖；可从对比中复制原文。优化效果需生成后比较。</small>
    </div>
   </>}
  </div>}
 </section>;
}
