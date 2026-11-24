import React,{useEffect,useState} from 'react';
import {PORTRAIT_DIMENSIONS,VIDEO_MODES} from './video-modes';
const names={parse:'解析原文',repair:'修正解析结果',audit:'独立 Agent 校对',validate:'校验原文与引用',save:'保存导入结果',review:'视觉审查',parallel_shots:'生成与检测独立运行',manual_review:'待集中人工审核'};
const taskState={queued:'排队中',running:'进行中',success:'已完成',needs_review:'待人工检查',cancelled:'已取消',failed:'失败'};
const duration=s=>s<60?`${s} 秒`:`${Math.floor(s/60)} 分 ${s%60} 秒`;
export default function JobProgress({job}){
 const [now,setNow]=useState(Date.now()/1000);
 useEffect(()=>{if(job.status!=='running')return;const timer=setInterval(()=>setNow(Date.now()/1000),1000);return()=>clearInterval(timer)},[job.status]);
 const scope=job.productionSettings?.scope||'all';
 const mode=VIDEO_MODES.find(m=>m.model===job.productionSettings?.videoModel);
 const autoSize={inherit:'沿用分镜',landscape:mode?.dimensions||VIDEO_MODES[0].dimensions,portrait:PORTRAIT_DIMENSIONS}[job.productionSettings?.videoResolution];
 const queuedMode=VIDEO_MODES.find(m=>m.profile===job.videoProfile);
 const events=[...(job.events||[]),...(job.shotTasks||[]).flatMap(t=>(t.events||[]).map(e=>({...e,message:t.name+' · '+e.message})))].sort((a,b)=>a.at-b.at).slice(-200),last=events.at(-1),model=[...events].reverse().find(e=>e.model);
 const elapsed=Math.max(0,Math.floor((job.finishedAt||now)-(job.startedAt||job.created)));
 return <div className="job-progress">
  {job.videoProfile&&<p>视频模式：{queuedMode?`${queuedMode.label} · ${queuedMode.steps} 步`:'历史 Ref2VA · 4 步'}{job.videoDimensions&&` · ${job.videoDimensions.join(' × ')}`}</p>}
  {job.shotTasks&&<details className="job-events" open><summary>生成队列与 Agent 检测 · 最多 {job.reviewConcurrency||3} 个 Agent 并行</summary>
   <p>视频生成 {job.queueSummary?.generate?.running||0} 个进行中 / {job.queueSummary?.generate?.queued||0} 个排队 · Agent 检测 {job.queueSummary?.review?.running||0} 个进行中 / {job.queueSummary?.review?.queued||0} 个排队</p>
   <small>生成完成就继续下一镜。检测要求重生成时追加生成队尾；所有检测与重试结束后汇总。暂停或取消会停止派发后续任务，已开始的生成和检测完成后保留结果。</small>
   <ul>{[...job.shotTasks].sort((a,b)=>a.ticket-b.ticket).map(t=><li key={t.id}><span><b>{t.name}</b> · {t.attempt?`重试 ${t.attempt}`:'首次'} · {t.phase==='generate'?'视频生成':'Agent 检测'} · {taskState[t.status]||t.status}<small>{t.message}</small></span></li>)}</ul>
  </details>}
  {job.pendingShotReviews?.length>0&&<details className="job-events" open><summary>本次待人工审核 · {job.pendingShotReviews.length} 个镜头</summary><ul>{job.pendingShotReviews.map(r=><li key={r.id}><span><b>{r.name}</b> · {r.reason}<small>版本 {r.version}</small></span></li>)}</ul></details>}
  {job.retryEvents?.length>0&&<details className="job-events"><summary>自动重试记录 · {job.retryEvents.length} 次</summary>{job.retryEvents.map((r,i)=><div key={i}><b>{r.name} · 重试 {r.attempt} / {r.maxRetries} · {r.action==='reroll'?'保留提示词重新抽卡':'修改提示词后重试'}</b><p>{r.reason}</p><small>种子 {r.before.seed} → {r.after.seed}</small>{r.action==='revise_prompt'&&<details><summary>查看提示词修改</summary>{['prompt','sidePrompt','backPrompt'].filter(k=>r.before[k]!==r.after[k]).map(k=><div key={k}><b>{{prompt:'主提示词',sidePrompt:'侧面',backPrompt:'背面'}[k]}</b><pre>{r.before[k]}</pre><p>修改后</p><pre>{r.after[k]}</pre></div>)}</details>}</div>)}</details>}
  {job.pendingReviews?.length>0&&<details className="job-events" open><summary>本次待人工审核 · {job.pendingReviews.length} 个资产</summary><ul>{job.pendingReviews.map(r=><li key={r.id}><span><b>{r.name}</b> · {r.reason}<small>版本 {r.version}</small></span></li>)}</ul><small>未通过的图片已保留，仍可作为图片生成的输入；分镜制作前须完成审批。此列表保留任务结束时的记录，当前审批状态以参考图页面为准。</small></details>}
  {job.productionSettings&&<details className="job-events"><summary>本次自动制作设置</summary>{scope!=='shots'&&<p>图片：{({inherit:'沿用各资产设置',qwen21:'Qwen Image 2.1 · INT8 · 25 步',base:'FLUX.2 Klein Base · 20 步',distilled:'FLUX.2 Klein Distilled · 4 步',codex:'Codex Image Gen'})[job.productionSettings.imageModel]}</p>}{scope!=='assets'&&<p>视频：{mode?`${mode.label} · ${mode.steps} 步 ${mode.sampler||'Euler'}`:'H3 Ref2VA INT8 Turbo · 4 步'} / 24 fps · 画幅：{autoSize} · 时长：{job.productionSettings.videoSeconds==='inherit'?'沿用分镜':job.productionSettings.videoSeconds+' 秒'}</p>}<p>Agent：{job.productionSettings.agentProvider==='codex'?job.productionSettings.agentModel+' / '+job.productionSettings.agentThinking:'DeepSeek / Max'} · {job.productionSettings.autoReview?'自动初筛开启':'自动初筛关闭'}</p><p>每项最大重试：{job.productionSettings.maxRetries??1} 次（不含首次生成）</p><small>已有视频保留原生成设置；自动制作只补齐没有结果的分镜。</small></details>}

  <div className="job-metrics"><b>{names[job.stage]|| (job.status==='queued'?'等待队列':'任务执行')}</b>{job.startedAt&&<span>耗时 {duration(elapsed)}</span>}{model&&<span>本次执行：{model.model} / {model.thinking}</span>}</div>
  {job.status==='running'&&<><progress aria-label="任务处理中" {...(job.kind==='parse'||job.kind==='review'?{}:{max:100,value:job.progress})}/><small>{last?`距最近活动 ${duration(Math.max(0,Math.floor(now-last.at)))}`:'等待执行器响应'} · 模型未返回期间持续计时，完成时间由模型决定。</small></>}
  {events.length>0&&<details className="job-events"><summary>运行日志 · {events.length} 条事件</summary><ol>{events.map((e,i)=><li key={i}><time>{new Date(e.at*1000).toLocaleTimeString()}</time><span>{e.message}{e.attempt?` · 第 ${e.attempt} 次`:''}{e.outputChars!==undefined?` · 返回 ${e.outputChars} 字符`:''}{e.usage?` · 输入 ${e.usage.input_tokens} / 输出 ${e.usage.output_tokens} tokens`:''}{e.threadId&&<small>会话 {e.threadId}</small>}</span></li>)}</ol><small>展示 SDK 运行事件，不展示提示词正文或模型推理内容。刷新页面后记录仍保留。</small></details>}
  {job.attempts?.length>0&&<details className="job-events"><summary>之前的执行 · {job.attempts.length} 次</summary>{job.attempts.map((a,i)=><div key={i}><b>第 {i+1} 次 · {a.agentProvider==='codex'?`${a.agentModel} / ${a.agentThinking}`:'DeepSeek'}</b><p>{a.message}</p><small>{a.events?.length||0} 条历史事件已保留</small></div>)}</details>}
 </div>;
}
