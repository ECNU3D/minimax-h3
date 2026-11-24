// Validate retry instructions independently from provider transport.
export function validateRetryDecision(review){
 if(!['none','revise_prompt','reroll'].includes(review.retryAction)||typeof review.retryReason!=='string'||!review.retryReason.trim())throw Error('审核重试决策无效');
 if(typeof review.revisedPrompt!=='string'||!Array.isArray(review.revisedViewPrompts)||review.revisedViewPrompts.some(x=>typeof x!=='string'))throw Error('修订提示词结构无效');
 if(review.verdict!=='revise'&&review.retryAction!=='none')throw Error('只有明确可修复的审核问题允许自动重试');
 if(review.retryAction==='revise_prompt'&&(!review.revisedPrompt.trim()||![0,2].includes(review.revisedViewPrompts.length)||review.revisedViewPrompts.some(x=>!x.trim())))throw Error('修改提示词需完整正文及可选的两条视图提示词');
 if(review.retryAction!=='revise_prompt'&&(review.revisedPrompt.trim()||review.revisedViewPrompts.length))throw Error('不改提示词的决策不能携带修改内容');
 return review;
}
