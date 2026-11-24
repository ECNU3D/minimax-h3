"""Director-agent selection. Missing settings always retain DeepSeek behavior."""
def provider(project):
    value=project.get('agentProvider','deepseek')
    if value not in ('deepseek','codex'):raise ValueError('导演 Agent 只能选择 DeepSeek 或 Codex 订阅')
    return value

DEFAULT_MODEL='gpt-5.6-sol'
DEFAULT_THINKING='high'

def catalog():
    from .codex_bridge import Client
    client=Client()
    try:
        account=client.request('account/read',{'refreshToken':False}).get('account') or {}
        if account.get('type')!='chatgpt':raise ValueError('Codex 订阅需要先在本机 Codex 登录 ChatGPT 账户；不会改用 API Key 或 DeepSeek')
        models=client.request('model/list',{'includeHidden':False}).get('data',[])
        return [dict(id=m['model'],name=m.get('displayName') or m['model'],thinking=[e['reasoningEffort'] for e in m.get('supportedReasoningEfforts',[])]) for m in models]
    finally:client.close()

def selection(project):
    model=project.get('agentModel',DEFAULT_MODEL);thinking=project.get('agentThinking',DEFAULT_THINKING)
    if not isinstance(model,str) or not model or len(model)>100:raise ValueError('Codex 模型无效')
    if thinking not in ('none','minimal','low','medium','high','xhigh','max','ultra'):raise ValueError('Thinking level 无效')
    return dict(agentModel=model,agentThinking=thinking)

def runtime(project):
    chosen=provider(project)
    if chosen=='deepseek':return dict(agentProvider=chosen)
    options=selection(project)
    model=next((m for m in catalog() if m['id']==options['agentModel']),None)
    if not model:raise ValueError('当前订阅账户不支持所选模型：'+options['agentModel'])
    if options['agentThinking'] not in model['thinking']:raise ValueError('所选模型不支持 Thinking level：'+options['agentThinking'])
    return dict(agentProvider=chosen,**options)
