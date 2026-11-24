// Pure draft transformations: applying twice never appends duplicate sections.
export function applyCase(draft,template){
 const language=draft.promptLanguage||'zh';
 const variants=template.variants?structuredClone(template.variants):{[language]:{prompt:template.prompt,soundscape:template.soundscape,music:template.music}};
 return {...draft,name:template.name,...variants[language],promptLanguage:language,promptVariants:variants,
  references:[],audioReferences:[],settings:{...draft.settings,seconds:template.seconds}};
}

export function switchLanguage(draft,language){
 if(!['zh','en'].includes(language)||!draft.promptVariants?.[language])throw Error('此草稿没有对应译文，请先应用配套的通用案例');
 const variants=structuredClone(draft.promptVariants);
 variants[draft.promptLanguage]={prompt:draft.prompt,soundscape:draft.soundscape,music:draft.music};
 return {...draft,...variants[language],promptLanguage:language,promptVariants:variants};
}

export function promptIssues(e){
 if(!e)return [];
 const issues=[],body=e.prompt;
 if(!body.trim())issues.push('请先填写画面/对白提示词，或打开一个通用测试案例');
 for(const key of ['subject_definitions','summary','retention_analysis','detailed_description']){
  if((body.match(new RegExp('^\\s*'+key+'\\s*:','gmi'))||[]).length>1)issues.push(key+' 出现多次，请合并内容或整套替换模板');
 }
 if(/^\s*(overall_soundscape|non_diegetic_music)\s*:/mi.test(body))issues.push('主提示词含环境音或音乐段落，请移到下方对应字段，避免重复发送');
 if(/<d>\s*\[Chinese\]/i.test(body)){
  const rest=body.replace(/<d>[\s\S]*?<\/d>/gi,'')+'\n'+e.soundscape;
  if(/无人声|无对白|无对话|禁止(?:人声|对白|对话)|不要(?:人声|对白|对话)|保持闭口|\bno\s+(?:speech|dialogue|human voices?)\b/i.test(rest))issues.push('已写入中文台词，但画面/环境音仍要求无人声、无对白或闭口；请修改冲突要求');
 }
 return issues;
}
