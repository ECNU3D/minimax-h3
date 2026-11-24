"""Reject incomplete reviewer output before it can authorize a retry or reach the UI."""
import math

def validate_result(r):
    if not isinstance(r,dict):raise ValueError('审核结果必须为对象')
    if r.get('verdict') not in ('pass','human','revise'):raise ValueError('审核结论无效')
    confidence=r.get('confidence')
    if isinstance(confidence,bool) or not isinstance(confidence,(int,float)) or not math.isfinite(confidence) or not 0<=confidence<=1:raise ValueError('审核置信度无效')
    if not isinstance(r.get('summary'),str) or not isinstance(r.get('limitations'),list) or any(not isinstance(s,str) for s in r['limitations']):raise ValueError('审核说明结构无效')
    if not isinstance(r.get('issues'),list) or any(not isinstance(x,dict) or x.get('severity') not in ('major','minor') or not all(isinstance(x.get(k),str) for k in ('evidence','fix')) for x in r['issues']):raise ValueError('审核问题结构无效')
    action=r.get('retryAction');reason=r.get('retryReason');prompt=r.get('revisedPrompt');views=r.get('revisedViewPrompts')
    if action not in ('none','revise_prompt','reroll') or not isinstance(reason,str) or not reason.strip():raise ValueError('审核重试决策缺失或无效')
    if not isinstance(prompt,str) or not isinstance(views,list) or any(not isinstance(v,str) for v in views):raise ValueError('审核修订提示词结构无效')
    if r['verdict']!='revise' and action!='none':raise ValueError('该审核结论不允许重试')
    if action=='revise_prompt':
        if not prompt.strip() or len(views) not in (0,2) or any(not v.strip() for v in views):raise ValueError('审核修订提示词不完整')
    elif prompt.strip() or views:raise ValueError('不改词决策不能携带修改内容')
    return r
