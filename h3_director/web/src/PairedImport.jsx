import React,{useState} from 'react';
import AgentSettings from './AgentSettings';

export default function PairedImport({library,create,loading,existing=false}){
 const [name,setName]=useState(''),[documents,setDocuments]=useState({}),[agentOptions,setAgentOptions]=useState({agentProvider:'deepseek',agentModel:'gpt-5.6-sol',agentThinking:'high'});
 const update=(role,value)=>setDocuments(d=>({...d,[role]:value}));
 return <form onSubmit={e=>{e.preventDefault();create({name,...(!existing?agentOptions:{}),documents:Object.entries(documents).filter(([,d])=>d&&(d.text||d.libraryId)).map(([role,d])=>({role,...d}))})}}>
 <p className="modal-description">参考图文档保留现成中文生图提示词，分镜文档提供镜头与素材引用。导演 Agent 负责两份文档的对应关系和原文校对；缺失的内容才补写并标注。</p>
 {!existing&&<AgentSettings value={agentOptions} disabled={loading} onChange={d=>setAgentOptions(v=>({...v,...d}))}/>}
 {!existing&&<label>项目名称<input required value={name} onChange={e=>setName(e.target.value)} placeholder="为你的故事起个名字"/></label>}
 {[['references','参考图生成 MD'],['storyboard','分镜生成 MD / 原始剧本']].map(([role,label])=><fieldset className="document-input" key={role}><legend>{label}</legend>
 <label className="upload-zone"><b>{documents[role]?.filename||'选择 Markdown / TXT 文件'}</b><input type="file" hidden accept=".md,.txt" onChange={async e=>{const f=e.target.files[0];if(f){update(role,{text:await f.text(),filename:f.name});if(!name)setName(f.name.replace(/\.\w+$/,''))}}}/></label>
 <select aria-label={label+'仓库选择'} value={documents[role]?.libraryId||''} onChange={e=>{update(role,e.target.value?{libraryId:e.target.value}:null);if(!name)setName(library.find(x=>x.id===e.target.value)?.name.replace(/\.md$/,'')||'')}}><option value="">或选择仓库中的文档…</option>{library.filter(x=>x.role===role).map(x=><option key={x.id} value={x.id}>{x.name}</option>)}</select>
 {documents[role]&&<button type="button" className="small" onClick={()=>update(role,null)}>移除此文档</button>}</fieldset>)}
 <small>可一次上传两份，也可先导入一份，之后在剧本资料补充。原始文件完整保留。</small>
 <button className="primary full" disabled={loading||!Object.values(documents).some(Boolean)}>{existing?'补充文档并重新解析':'导入并建立项目'}</button>
 </form>
}
