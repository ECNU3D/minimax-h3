export const QUALITY_PROFILE='ref2v-768p-8step';
export const PREVIEW_PROFILE='ref2v-preview-4step';
export const FLEX_PROFILE='ref2v-flex-768p-6step';
export const PORTRAIT_DIMENSIONS='768 × 1344';
export const VIDEO_MODES=[
 {profile:QUALITY_PROFILE,model:'h3_ref2va_int8_turbo_768p_8step',label:'768p 高质量（默认）',dimensions:'1344 × 768',supportsPortrait:true,steps:8,detail:'768p Turbo v1.0 · 8 步 Euler · 24 fps'},
 {profile:PREVIEW_PROFILE,model:'h3_ref2va_int8_turbo_544p_4step',label:'快速预览 · 544p',dimensions:'960 × 544',steps:4,detail:'常规 4 步 Euler · 24 fps · 用于检查提示词、构图和动作'},
 {profile:FLEX_PROFILE,model:'h3_ref2va_int8_flex_768p_6step',label:'Pika H3 Flex · 768p（可选）',dimensions:'1344 × 768',steps:6,sampler:'LCM',detail:'Pika Flex · 固定 6 步 LCM · 24 fps · 画质与速度以试片为准'},
];
export const videoMode=profile=>VIDEO_MODES.find(m=>m.profile===profile)||VIDEO_MODES[0];
export const versionMode=version=>VIDEO_MODES.find(m=>m.profile===version?.profile)?.label||'历史视频';
export const shotResolution=shot=>shot.videoResolution||(shot.width===768&&shot.height===1344?'portrait':'landscape');
