import React,{useState,useEffect} from 'react';
import MaskEditor from './MaskEditor';

export function CodexUsage(){
 const [value,setValue]=useState(null),[busy,setBusy]=useState(false);
 const refresh=async()=>{setBusy(true);try{const r=await fetch('/api/codex/usage');if(!r.ok)throw Error('用量查询失败');setValue(await r.json())}catch(e){setValue({available:false,error:e.message})}finally{setBusy(false)}};
 useEffect(()=>{refresh();const t=setInterval(refresh,60000);return()=>clearInterval(t)},[]);
 const codex=value?.buckets?.find(b=>b.id==='codex');
 return <div className="codex-usage"><div><b>Codex 用量</b><button className="small" disabled={busy} onClick={refresh}>{busy?'查询中…':'刷新'}</button></div>{value?.available?<>
 {codex?.windows.length?codex.windows.map(w=><p key={w.window}>{w.windowDurationMins===10080?'每周':w.windowDurationMins===300?'5 小时':`${w.windowDurationMins??'未知'} 分钟`}剩余 <b>{w.remainingPercent==null?'未知':w.remainingPercent+'%'}</b><small>{w.resetsAt?'重置 '+new Date(w.resetsAt*1000).toLocaleString('zh-CN'):''}</small></p>):<p>账户额度未提供</p>}
 <small>图片独立额度未公开，不能换算为张数。最多每分钟更新。</small></>:<small>{value?.error||'读取当前登录账户…'}</small>}</div>
}

export default function AssetGeneration({project,draft,change,onUpload,disabled,onGenerate,onSaveMask,onMaskDirty}){
 const [maskDirty,setMaskDirtyState]=useState(false);
 const setMaskDirty=v=>{setMaskDirtyState(v);onMaskDirty?.(v)};
 const provider=draft.provider||'local',mode=draft.imageMode||'text',refs=draft.generationRefs||[];
 const available=[];
 for(const a of project.assets){
  if(a.id!==draft.id&&mode!=='inpaint'){const selected=a.versions.find(v=>v.id===a.selected);available.push({key:`asset:${a.id}:0`,label:`${a.name} / 当前选中主图${selected?'':'（待生成）'}`,url:selected?.files[0]?.url})}
  for(const f of a.inputs||[])available.push({key:`input:${a.id}:${f.id}`,label:`${a.name} / 输入 / ${f.label}`,url:f.url});
  for(const v of a.versions)for(const [i,f] of v.files.entries())available.push({key:`version:${a.id}:${v.id}:${i}`,label:`${a.name} / ${f.label} / ${v.id.slice(0,6)}`,url:f.url});
 }
 const setRefs=next=>{change('generationRefs',next);change('editMask',null);setMaskDirty(false)};
 const freeze=key=>{if(!key?.startsWith('asset:'))return key;const [,id,index]=key.split(':');const a=project.assets.find(a=>a.id===id);return a?.selected?`version:${id}:${a.selected}:${index}`:null};
 const selected=draft.versions.find(v=>v.id===draft.selected);
 return <section className="generation-box">{selected&&<div className="actual-image-inputs"><b>当前版本实际输入</b>{selected.inputReferences?.length?<div className="views">{selected.inputReferences.map((f,i)=><a href={f.url} target="_blank" key={i}><img src={f.url} alt={'实际参考图 '+(i+1)}/><span>参考 {i+1} · {project.assets.find(a=>a.id===f.key?.split(':')[1])?.name||f.key}</span></a>)}</div>:<p className="hint">此版本主图未使用上游参考图（文生图）。人物侧面、背面另以本次正面图为参考。</p>}{selected.editMaskReference?.url&&<div className="views"><a href={selected.editMaskReference.url} target="_blank"><img src={selected.editMaskReference.url} alt="当前版本实际编辑选区"/><span>实际选区 · 白色可改，黑色保留</span></a></div>}</div>}<h3>生成参考图</h3><label>生成方式<select aria-label="参考图生成方式" value={provider} disabled={disabled} onChange={e=>{change('provider',e.target.value);setMaskDirty(false);if(mode==='inpaint')change('imageMode','reference')}}><option value="local">本地模型 · Qwen / FLUX</option><option value="codex">Codex · Image Gen</option></select></label>
 <div className="generation-modes">{[['text','文生图'],['reference','参考图生图'],...(provider==='local'&&(draft.imageVariant||'qwen21')==='qwen21'?[['inpaint','选区改图']]:[])].map(([v,l])=><button key={v} disabled={disabled} className={mode===v?'selected':''} onClick={()=>{change('imageMode',v);setMaskDirty(false);if(v==='inpaint')setRefs((refs.length?refs.map(freeze).filter(Boolean):selected?.files.length?[`version:${draft.id}:${selected.id}:0`]:[]).slice(0,1))}}>{l}</button>)}</div>
 {provider==='local'?<label>本地模型<select aria-label="本地图像模型" disabled={disabled} value={draft.imageVariant||'qwen21'} onChange={e=>{change('imageVariant',e.target.value);setMaskDirty(false);if(mode==='inpaint'&&e.target.value!=='qwen21')change('imageMode','reference')}}><option value="qwen21">Qwen Image 2.1 · 本地 INT8 · 25 步（默认）</option><option value="distilled">FLUX.2 Klein 4B Distilled · 4 步</option><option value="base">FLUX.2 Klein 4B Base · 20 步</option></select></label>:<small>使用本机已登录的 Codex 内置 Image Gen。种子不可控；人物依次生成正、侧、背三张图片。</small>}
 {mode!=='text'&&<><label>输入参考图 · 有序 {refs.length} / {mode==='inpaint'?1:9}</label><div className="image-inputs">{refs.map((key,i)=>{const f=available.find(f=>f.key===key);return <div key={key}>{f?.url&&<img src={f.url} alt={f.label}/>}<span>{i+1}. {f?.label||'参考图已失效'}</span><button title="上移输入图" disabled={!i||disabled} onClick={()=>{const next=[...refs];[next[i-1],next[i]]=[next[i],next[i-1]];setRefs(next)}}>↑</button><button title="移除输入图" disabled={disabled} onClick={()=>setRefs(refs.filter(k=>k!==key))}>×</button></div>})}</div>
 <select aria-label="选择已有图片作为输入" value="" disabled={disabled||refs.length>=(mode==='inpaint'?1:9)} onChange={e=>setRefs([...refs,e.target.value])}><option value="">＋ 选择上游资产 / 已有素材 / 三视图</option>{available.filter(f=>!refs.includes(f.key)).map(f=><option value={f.key} key={f.key}>{f.label}</option>)}</select>
 <label className="button small">上传输入参考图<input hidden type="file" accept="image/png,image/jpeg,image/webp" multiple={mode!=='inpaint'} disabled={disabled} onChange={e=>{const files=[...e.target.files];e.target.value='';onUpload(files)}}/></label><small>上游资产可尚未生成，自动制作按依赖先后生成；未通过初筛也可作为图片输入。输入图不会替换已有生成版本。人物侧面、背面继续使用本次正面图固定身份。</small></>}
 {provider==='local'&&(draft.imageVariant||'qwen21')==='qwen21'&&<small>参考编辑与侧背视图会自动使用独立种子，避免与输入图重复噪声；相同输入与基础种子仍可复现。</small>}
 {mode==='inpaint'&&<MaskEditor key={draft.id+':'+refs[0]} base={available.find(f=>f.key===refs[0])} mask={available.find(f=>f.key===draft.editMask)} disabled={disabled} onSave={onSaveMask} onDirty={setMaskDirty}/>}
 <button className="primary full" disabled={disabled||(mode!=='text'&&!refs.length)||(mode==='inpaint'&&(!draft.editMask||maskDirty))} onClick={onGenerate}>{draft.versions.length?'生成新版本':'生成参考图'} · {provider==='local'?'本地':'Codex'}</button>
 </section>
}
