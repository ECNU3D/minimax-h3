import React,{useState} from 'react';
import AgentSettings from './AgentSettings';
import {VIDEO_MODES,videoMode,PREVIEW_PROFILE,FLEX_PROFILE,PORTRAIT_DIMENSIONS} from './video-modes';

export default function AutoProduction({project,scope='all',loading,start,error,onReferences}){
 const [value,setValue]=useState({maxRetries:1,regenerateAssets:false,imageModel:'qwen21',videoModel:'h3_ref2va_int8_turbo',videoResolution:'inherit',videoSeconds:'inherit',...(project.productionSettingsByScope?.[scope]||project.productionSettings),
  videoModel:videoMode(project.videoProfile).model,
  agentProvider:project.agentProvider||'deepseek',agentModel:project.agentModel||'gpt-5.6-sol',agentThinking:project.agentThinking||'high',autoReview:project.autoReview});
 const change=(key,next)=>setValue(v=>({...v,[key]:next}));
 const mode=VIDEO_MODES.find(m=>m.model===value.videoModel)||VIDEO_MODES[0];
 const videoResolution=mode.supportsPortrait?value.videoResolution:'landscape';
 const images=(scope==='assets'&&value.regenerateAssets?project.assets:project.assets.filter(a=>!a.selected)).length,shots=project.shots.filter(s=>!s.selected).length;
 const readiness=project.referenceReadiness,blocked=scope==='shots'&&!readiness?.ready;
 const submit=()=>{if(blocked)return;const {agentProvider,agentModel,agentThinking,autoReview,maxRetries,imageModel,videoModel,videoSeconds}=value;start({agentProvider,agentModel,agentThinking,autoReview,maxRetries,...(scope!=='shots'?{imageModel,...(scope==='assets'?{regenerateAssets:!!value.regenerateAssets}:{})}:{}),...(scope!=='assets'?{videoModel,videoResolution,videoSeconds}:{})})};
 return <form className="auto-production" onSubmit={e=>{e.preventDefault();submit()}}>
  {error&&<p className="warning" role="alert">{error}</p>}
  {blocked&&<section className="reference-gate" role="alert"><b>请先生成并审批所需参考图</b><p>{readiness?'以下参考图尚未准备好，暂不能开始分镜制作。':'正在检查参考图状态…'}</p><ul>{readiness?.problems.map(p=><li key={p.id}><b>{p.name}</b>：{p.reason}<small>用于 {p.shots.join('、')}</small></li>)}</ul><button type="button" onClick={onReferences}>前往参考图</button></section>}
  <p className="hint">{scope==='assets'?`${images} 个参考资产待生成，本次仅制作图片。`:scope==='shots'?`${shots} 个镜头待生成，本次仅制作分镜。`:`${images} 个参考资产、${shots} 个镜头待生成。`}{scope==='assets'&&value.regenerateAssets?'全部参考图按依赖生成新版本，旧版本保留。':'已有参考图直接保留；可单独生成新版本，或勾选全部重新生成。'}分镜只生成没有结果的镜头，已有视频一律保留。</p>
  {scope!=='shots'&&<p className="hint">单图未通过初筛会保留结果并继续其余图片，待审核图仍可作图片生成输入；整批完成后集中人工审核，分镜仍须先通过参考图审批。</p>}
  {scope==='shots'&&<p className="hint">所需参考图须为当前版本，并通过 Agent 初筛或人工采用。已有视频保留；单镜审核失败、待人工或重试达到上限后继续后续镜头，整批完成再集中审核。生成故障、在途结果不明确及执行器 STOP 仍会停止。</p>}
  {scope!=='shots'&&<fieldset disabled={loading}><legend>参考图生成</legend>
   <label>图片模型<select aria-label="自动制作图片模型" value={value.imageModel} onChange={e=>change('imageModel',e.target.value)}>
    <option value="qwen21">本地 Qwen Image 2.1 · INT8 · 25 步（默认）</option><option value="inherit">沿用每个资产的模型设置</option><option value="distilled">本地 FLUX.2 Klein 4B Distilled · FP8 · 4 步</option><option value="base">本地 FLUX.2 Klein 4B Base · FP8 · 20 步</option><option value="codex">Codex Image Gen · 当前登录账户</option>
   </select></label>
   {scope==='assets'&&<label className="auto-review-toggle"><input aria-label="全部参考图生成新版本" type="checkbox" checked={!!value.regenerateAssets} onChange={e=>change('regenerateAssets',e.target.checked)}/>全部生成新版本（保留旧版）</label>}
   <small>本地模型支持文生图与参考图生图。人物生成正、侧、背三视图；侧背面沿用同一次正面图。选择 Codex 生图使用订阅用量，与下方导演 Agent 选择相互独立。</small>
  </fieldset>}
  {scope!=='assets'&&<fieldset disabled={loading}><legend>视频生成</legend>
   <label>视频生成模式<select aria-label="自动制作视频模型" value={value.videoModel} onChange={e=>change('videoModel',e.target.value)}>{VIDEO_MODES.map(m=><option key={m.model} value={m.model}>{m.label} · {m.steps} 步 {m.sampler||'Euler'}</option>)}</select></label>
   <div className="param-row"><label>生成画幅<select aria-label="自动制作视频画幅" value={videoResolution} onChange={e=>change('videoResolution',e.target.value)}>{mode.supportsPortrait&&<option value="inherit">沿用分镜画幅</option>}<option value="landscape">横屏 · {mode.dimensions}</option>{mode.supportsPortrait&&<option value="portrait">竖屏 · {PORTRAIT_DIMENSIONS}</option>}</select></label>
   <label>生成时长<select aria-label="自动制作视频时长" value={value.videoSeconds} onChange={e=>change('videoSeconds',e.target.value==='inherit'?'inherit':Number(e.target.value))}><option value="inherit">沿用分镜时长</option>{[5,8,10,12,15].map(v=><option key={v} value={v}>{v} 秒</option>)}</select></label></div>
   <small>{mode.detail}。{mode.profile===PREVIEW_PROFILE?'预览画质低于正式出片，用于快速检查提示词。':mode.profile===FLEX_PROFILE?'使用 Flex 专用适配器与固定采样表。':'与分镜测试的「768p 基线」一致。'}适配器强度 1 · 视频 / 音频 shift 12 / 3 · denoise 1。每镜 1–9 张有序参考，沿用各镜种子；实际时长按 H3 帧数网格对齐。</small>
  </fieldset>}
  <fieldset disabled={loading}><legend>导演 Agent</legend><AgentSettings value={value} disabled={loading} onChange={next=>setValue(v=>({...v,...next}))}/>
   <label className="auto-review-toggle"><input type="checkbox" checked={value.autoReview} onChange={e=>change('autoReview',e.target.checked)}/>生成后自动视觉初筛</label>
   <label>每项最大重试次数<input aria-label="最大重试次数" type="number" min="0" max="10" step="1" required disabled={!value.autoReview} value={value.maxRetries} onChange={e=>change('maxRetries',e.target.value===''?'':Number(e.target.value))}/></label>
   <small>不含首次生成，默认 1 次；0 表示不自动重试，最多可设 10 次。Agent 可选择改提示词、保留提示词重新抽卡，或直接交人工。{scope!=='assets'&&'视频实际重试还受每镜累计 2 次提交预算限制。'}{!value.autoReview&&'自动初筛关闭时不执行审核重试。'}</small>
  </fieldset>
  <div className="notice">需要本地生成时自动启动 ComfyUI，并在任务记录显示启动进度。{scope!=='assets'&&'视频串行生成，最多 3 个 Agent 并行检测；需要重生成时追加队尾。每镜最多两次视频提交；手动清空镜头后可开始新一轮，旧记录保留。'}</div>
  <button className="primary full" disabled={loading||blocked}>{scope==='assets'?'确认设置并生成参考图':scope==='shots'?'确认设置并生成分镜':'确认设置并开始全流程制作'}</button>
 </form>;
}
