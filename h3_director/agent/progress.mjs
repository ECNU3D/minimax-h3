// Emit only operational metadata; model text and reasoning stay out of public logs.
export function progress(stage,event,metadata={}){
 console.log(JSON.stringify({type:'director.progress',stage,event,...metadata}));
}
export async function runWithProgress(thread,input,options,stage,metadata={},emit=progress){
 emit(stage,'started',metadata);
 const items=[];let finalResponse='',usage=null,completed=false;
 try{
  const {events}=await thread.runStreamed(input,options);
  for await(const event of events){
   const info={...metadata};
   if(event.thread_id)info.threadId=event.thread_id;
   if(event.item?.type==='agent_message')info.outputChars=event.item.text?.length||0;
   if(event.type==='turn.completed'){usage=event.usage;info.usage=usage;completed=true;}
   if(event.type==='item.completed'){
    items.push(event.item);
    if(event.item.type==='agent_message')finalResponse=event.item.text;
   }
   if(event.type==='turn.failed')throw Error(event.error?.message||'模型调用失败');
   if(event.type==='error')continue; // Recoverable stream errors are not turn failures.
   if(['thread.started','turn.started','item.started','item.updated','item.completed','turn.completed'].includes(event.type))emit(stage,event.type,info);
  }
  if(!completed||!finalResponse)throw Error('模型流未完整结束或没有返回结果，请继续原任务重试');
  return {items,finalResponse,usage};
 }catch(error){emit(stage,'failed',metadata);throw error;}
}
