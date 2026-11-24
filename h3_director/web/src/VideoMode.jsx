import React from 'react';
import {VIDEO_MODES,videoMode,PREVIEW_PROFILE,FLEX_PROFILE,PORTRAIT_DIMENSIONS} from './video-modes';

export default function VideoMode({profile,onChange,disabled=false,label='视频生成模式',detail,shotFraming=false}){
 const mode=videoMode(profile);
 return <div className="video-mode">
  <label>{label}<select aria-label={label} value={mode.profile} disabled={disabled} onChange={e=>onChange(e.target.value)}>
   {VIDEO_MODES.map(m=><option key={m.profile} value={m.profile}>{m.label}</option>)}
  </select></label>
  <div><b>{mode.dimensions}{shotFraming&&mode.supportsPortrait?` / ${PORTRAIT_DIMENSIONS}`:''}</b><small>{detail||mode.detail}</small>
   <small>{mode.profile===PREVIEW_PROFILE?'预览画质低于正式出片；满意后切回 768p 生成新版本。':mode.profile===FLEX_PROFILE?'采用 Flex 六步配方，可切回原有 768p 默认。':'保留原有高质量参数。'}切换仅用于后续提交，已有视频与排队任务保留。</small></div>
 </div>;
}
