"""Reviewed Chinese counterparts of the seven sound cases; no runtime translation."""
import copy
import re

FIELDS=('prompt','soundscape','music')
RETENTION='整个连续镜头保持相同的人物/物体、服装、位置与光线。不切镜，不出现字幕、标志或可读的画面文字。'

ZH={
 'zh_solo':(
  'S1 是一位三十多岁的成年女性，穿素色蓝衬衫，独自坐在安静的客厅里。',
  '固定中近景，S1 面向镜头，窗边柔光照亮她的脸。嘴部清晰可见。',
  '0–1 秒：S1 平静地看向镜头。1–6 秒：(S1) 用温暖自然的女声、清晰的普通话，以日常交谈的语速说 <d>[Chinese]你好，今天阳光很好，我们出去走走吧。</d> 她的嘴唇随自己的台词运动。6–8 秒：她说完，露出轻松的小小微笑。',
  '前景对白下方是很轻的室内底声。可听见的说话声只来自画面中的 S1。台词清楚、干净，房间混响很少。','N/A'),
 'zh_duo':(
  'S1 是穿蓝衬衫的成年女性，坐在左侧。S2 是穿灰衬衫的成年男性，坐在右侧。两人在安静房间的小桌两边，身体略朝向对方。',
  '固定双人中景，两人的脸和嘴部始终可见；S1 在左，S2 在右。',
  '0–1 秒：两人安静坐着。1–4 秒：(S1) 用清晰、温暖、中等音高的普通话女声问 <d>[Chinese]你把钥匙放在哪里了？</d> S2 闭着嘴倾听。4–5 秒：短暂的对话停顿。5–8 秒：(S2) 用较低沉、放松的普通话男声回答 <d>[Chinese]就在门口的桌子上。</d> S1 闭着嘴倾听。8–10 秒：两人结束对话，安静下来。说话轮次不重叠。',
  '两条前景人声下方是很轻的室内底声。每条人声对应其画面中的说话人。轮次之间有清楚的停顿，人物音色保持一致。没有画外旁白。','N/A'),
 'zh_group':(
  '三位成年人围坐在小桌旁。左侧 S1 是穿蓝衬衫的女性；中间 S2 是穿灰毛衣的男性；右侧 S3 是穿米色外套的女性。三人的脸始终可见。',
  '安静客厅中柔和照明，固定的正面三人中远景。摄影机不动。',
  '0–1 秒：大家等待。1–4 秒：(S1) 用明亮、中等音高的普通话女声问 <d>[Chinese]我们几点出发？</d> 4–5 秒：停顿。5–7 秒：(S2) 用低沉、平稳的普通话男声回答 <d>[Chinese]九点，在楼下见。</d> 7–8 秒：停顿。8–10 秒：(S3) 用比 S1 更柔和、音高略低的普通话女声说 <d>[Chinese]好的，我会准时到。</d> 10–12 秒：大家说完后放松下来。只有当前说话人运动嘴唇，另外两人倾听。说话轮次不重叠。',
  '三条清楚分离的前景人声下方是轻微的室内底声。每个人的音色保持稳定，停顿清晰可听。台词只来自指定的画面内说话人，没有旁白。','N/A'),
 'sync_sfx':(
  '一张原木桌面、一个白色陶瓷杯和一只成年人的右手。杯子起初放在桌子右侧。画面中没有人脸。',
  '安静室内的固定近景，清楚呈现手、桌面与杯子。',
  '0–1 秒：手悬在桌面上方。1.5 秒时，指关节敲一下木桌，发出一次短促干净的木质敲击声。3 秒时再敲一下，发出第二次独立的木质敲击声。4–5 秒：手将杯子提起几厘米。5.5 秒时轻轻放下杯子一次，发出轻微的陶瓷接触木面的碰响。6–8 秒：手和杯子静止。每次接触声都准确出现在看得见的接触时刻，不增加额外敲击。',
  '室内底声很低。两次干净的木质敲击声和一次较轻的陶瓷杯接触声，在对应的可见碰撞时清楚突出。没有说话、对白、旁白或哼唱。','N/A'),
 'ambience':(
  '小雨中的空花园小径，包含湿润石板、灌木和一处浅水洼。没有人或动物。',
  '阴天柔光下的小花园被雨水打湿，固定广角全景。',
  '整个镜头中小雨持续落下，在浅水洼里形成小涟漪。微风让树叶轻轻移动。场景平静连续，没有突发事件。',
  '持续轻柔的雨声：细小雨滴拍打湿石板，在浅水洼里溅起更柔软的水声。偶尔轻微的树叶沙沙声位于雨声后方。自然的室外纵深，声音平滑连续。没有说话、对白、旁白或哼唱。','N/A'),
 'music':(
  '阳光照进空客厅，里面有沙发、木质茶几和轻薄窗帘。画面中没有人、乐器或演奏者。',
  '温暖午后光线下的宁静客厅，固定广角全景。',
  '整个镜头中窗帘随微风作几乎难以察觉的移动。摄影机和所有家具保持静止。没有可见的碰撞事件或对白。',
  '仅有几乎听不见的室内底声。没有说话、对白、旁白、歌唱或哼唱。器乐配乐在下方单独指定。',
  '轻柔的画外钢琴独奏配乐，约 72 BPM，旋律乐句简单、连贯，音符柔和温暖。自然平滑的余音，音量适中偏低，没有打击乐，也没有人声、合唱、歌词或哼唱。短乐句在结尾附近柔和收束。'),
 'dialogue_music':(
  'S1 是穿素色蓝衬衫的成年女性，独自坐在安静的客厅里，窗边柔光照亮她。',
  'S1 的固定中近景，神情温柔，嘴部清晰可见。',
  '0–2 秒：S1 若有所思地看向镜头。2–7 秒：(S1) 用柔和但清晰、自然的普通话女声，以从容的日常交谈语速说 <d>[Chinese]别着急，我们还有时间，慢慢来。</d> 嘴唇随台词运动。7–10 秒：她说完，露出让人安心的小小微笑。',
  '一条清晰的前景说话声下方是安静的室内底声。S1 的声音清楚易懂、贴近而自然，混响很少。没有其他说话人或旁白。',
  '很轻的画外钢琴独奏，约 68 BPM，旋律稀疏而温暖。整个对白期间，钢琴音量明显低于说话声，音符之间有宽松的留白。没有歌唱人声、歌词、哼唱、合唱或打击乐。句子结束后钢琴轻柔延续。'),
}


def chinese(key):
    subjects,summary,detail,sound,music=ZH[key]
    return dict(prompt=f'subject_definitions:\n{subjects}\nsummary:\n{summary}\nretention_analysis:\n{RETENTION}\ndetailed_description:\n{detail}',soundscape=sound,music=music)


def with_languages(e):
    """Read-time upgrade: preserve existing edits and never rewrite old jobs."""
    e=copy.deepcopy(e)
    language=e.get('promptLanguage')
    if language not in ('zh','en'):
        # Ignore spoken lines: both language variants keep the exact Chinese dialogue.
        prose=re.sub(r'<d>.*?</d>','',e['prompt'],flags=re.S)
        language='zh' if re.search(r'[\u4e00-\u9fff]',prose) else 'en'
    variants=copy.deepcopy(e.get('promptVariants',{}))
    if not variants:
        # Legacy UI could replace the entire case while retaining its original ID.
        # Match all three current fields before choosing a paired translation.
        from .lab_templates import catalog
        for t in catalog():
            if any(all(e[field]==v[field] for field in FIELDS) for v in t['variants'].values()):
                variants=copy.deepcopy(t['variants']);break
    if not variants and e.get('templateId') in ZH:
        from .lab_templates import template
        for key,value in template(e['templateId'])['variants'].items():variants.setdefault(key,value)
    variants[language]={key:e[key] for key in FIELDS}
    e.update(promptLanguage=language,promptVariants=variants)
    return e


def validate_variants(value):
    if not isinstance(value,dict) or set(value)-{'zh','en'}:raise ValueError('提示词语言版本无效')
    for item in value.values():
        if not isinstance(item,dict) or set(item)!=set(FIELDS):raise ValueError('语言版本须含完整的画面、环境音和音乐')
        if any(not isinstance(v,str) or len(v)>50000 for v in item.values()):raise ValueError('语言版本文本无效或过长')
    return copy.deepcopy(value)
