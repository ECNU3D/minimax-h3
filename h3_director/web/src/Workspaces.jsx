import React,{useEffect,useState} from 'react';
import {FolderOpen,ArrowUpRight,Trash2,RotateCcw} from 'lucide-react';
export default function Workspaces({projects,jobs,api,choose,changed,clearCurrent}){
 const [trash,setTrash]=useState([]),[target,setTarget]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const refresh=async()=>setTrash(await api('projects/trash'));
 useEffect(()=>{refresh().catch(e=>setError(e.message))},[]);
 const action=async(p,operation)=>{setBusy(true);setError('');try{await api(`projects/${p.id}/${operation}`,{});if(operation==='delete')clearCurrent(p.id);setTarget(null);await refresh();await changed()}catch(e){setError(e.message)}finally{setBusy(false)}};
 return <div className="workspaces">
  {error&&<p role="alert" className="warning">{error}</p>}
  {target&&<section className="delete-confirm" role="alertdialog" aria-label="确认删除工作空间"><b>删除「{target.name}」？</b><p>工作空间将移入已删除列表，可随时恢复。原始文档、素材、任务记录与生成预算保留；不会释放磁盘空间。</p><div><button disabled={busy} onClick={()=>setTarget(null)}>取消</button><button className="danger" disabled={busy} onClick={()=>action(target,'delete')}>确认删除</button></div></section>}
  <div className="project-list">{projects.map(p=>{const pending=jobs.some(j=>j.projectId===p.id&&['running','queued','paused','interrupted'].includes(j.status));return <div className="workspace-row" key={p.id}><button disabled={busy} onClick={()=>choose(p)}><FolderOpen size={22}/><div><b>{p.name}</b><small>{p.shots} 镜 · {p.assets} 个参考资产</small></div><ArrowUpRight size={16}/></button><button className="workspace-delete" disabled={busy||pending} title={pending?'请先完成或取消待执行任务':'删除工作空间'} aria-label={'删除工作空间 '+p.name} onClick={()=>setTarget(p)}><Trash2 size={17}/></button></div>})}</div>
  <details className="workspace-trash"><summary>已删除工作空间 · {trash.length}</summary>{trash.length?trash.map(p=><div className="trash-row" key={p.id}><span>{p.name}<small>{new Date(p.deletedAt*1000).toLocaleString()}</small></span><button disabled={busy} onClick={()=>action(p,'restore')}><RotateCcw size={14}/>恢复</button></div>):<p>暂无已删除的工作空间。</p>}</details>
 </div>;
}
