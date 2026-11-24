"""Self-contained, project-independent native H3 sound test cases."""
import copy
import re


def case(key,name,category,seconds,description,subjects,summary,detail,soundscape,music,checks):
    return dict(id=key,name=name,category=category,seconds=seconds,description=description,
        prompt=f'subject_definitions:\n{subjects}\nsummary:\n{summary}\nretention_analysis:\nKeep the same subjects, wardrobe, positions and lighting throughout one continuous shot. No cuts, subtitles, logos or readable on-screen text.\ndetailed_description:\n{detail}',
        soundscape=soundscape,music=music,checks=checks)


CASES=[
 case('zh_solo','中文对白 · 单人','对白',8,'一个说话人、一句台词，检查普通话、音色稳定与口型。',
      'S1 is an adult woman in her thirties wearing a plain blue shirt, seated alone in a quiet living room.',
      'A locked medium close-up of S1 facing the camera, softly lit by a window. Her mouth is clearly visible.',
      '0–1 s: S1 looks calmly at the camera. 1–6 s: (S1), with a warm natural female voice and clear conversational Mandarin, says <d>[Chinese]你好，今天阳光很好，我们出去走走吧。</d> Her lips move with her own words. 6–8 s: she finishes and gives a small relaxed smile.',
      'A very quiet indoor room tone underneath the foreground dialogue. The audible speech comes only from S1 on screen. Keep the words clear and dry, with minimal room reverberation.',
      'N/A',['台词完整，无增词、漏字或重复','单一女声音色稳定，无金属感或回声','口型跟随台词；说完后停止发声']),
 case('zh_duo','中文对白 · 双人','对白',10,'固定双人同框，轮流讲话，检查声线与人物归属。',
      'S1 is an adult woman in a blue shirt seated on the left. S2 is an adult man in a gray shirt seated on the right. They face slightly toward each other across a small table in a quiet room.',
      'A locked medium two-shot keeps both faces and mouths visible, S1 on the left and S2 on the right.',
      '0–1 s: both sit quietly. 1–4 s: (S1), in a clear, warm mid-pitched female Mandarin voice, asks <d>[Chinese]你把钥匙放在哪里了？</d> S2 listens with his mouth closed. 4–5 s: a short conversational pause. 5–8 s: (S2), in a lower, relaxed male Mandarin voice, answers <d>[Chinese]就在门口的桌子上。</d> S1 listens with her mouth closed. 8–10 s: both settle into silence. The speakers take turns without overlap.',
      'Low indoor room tone beneath the two foreground voices. Each voice is attached to its visible speaker. Preserve a clear pause between turns and consistent voice identity. No off-screen narration.',
      'N/A',['左女右男的声线与台词归属正确','问答顺序正确，不抢话、不串音色','听者嘴部保持安静；对话间有停顿']),
 case('zh_group','中文对白 · 三人轮流','对白',12,'三个人分别说一句，检查多人音色区分与轮次。',
      'Three adults sit around a small table. S1 on the left is a woman in a blue shirt. S2 in the center is a man in a gray sweater. S3 on the right is a woman in a cream jacket. All three faces remain visible.',
      'A locked medium-wide frontal three-shot in a softly lit quiet living room. The camera stays still.',
      '0–1 s: everyone waits. 1–4 s: (S1), with a bright mid-pitched female Mandarin voice, asks <d>[Chinese]我们几点出发？</d> 4–5 s: a pause. 5–7 s: (S2), with a low, steady male Mandarin voice, replies <d>[Chinese]九点，在楼下见。</d> 7–8 s: a pause. 8–10 s: (S3), with a softer and slightly lower female Mandarin voice than S1, says <d>[Chinese]好的，我会准时到。</d> 10–12 s: everyone finishes and relaxes. Only the current speaker moves their lips; the other two listen. No overlapping turns.',
      'Subtle indoor room tone beneath three clearly separated foreground voices. Keep each voice identity stable and the pauses audible. Speech belongs only to the designated on-screen speaker, with no narration.',
      'N/A',['三句台词按左、中、右的顺序出现','两位女性与一位男性音色能区分','没有齐声、抢话、串台词或背景嘟囔']),
 case('sync_sfx','同步音效 · 敲桌与放杯','音效',8,'两次木桌敲击、一次陶瓷杯接触，检查声画时点与材质。',
      'A natural wooden tabletop, one white ceramic cup and a single adult right hand. The cup starts resting on the right side of the table. No faces are in frame.',
      'A locked close-up clearly shows the hand, tabletop and cup in a quiet room.',
      '0–1 s: the hand hovers above the table. At 1.5 s it taps the wooden tabletop once with a knuckle, producing one short dry wooden knock. At 3 s it taps once more, producing a second separate wooden knock. 4–5 s: it lifts the cup a few centimeters. At 5.5 s it gently sets the cup down once, producing a light ceramic-on-wood clink. 6–8 s: the hand and cup remain still. Each contact sound occurs exactly when contact is visible; there are no extra taps.',
      'Very low indoor room tone. Two dry wooden knocks and one lighter ceramic cup contact sound stand out distinctly at the visible impacts. No speech, dialogue, narration or humming.',
      'N/A',['恰好两次敲桌、一次放杯声','接触声与画面动作同步','木质与陶瓷质感可区分，无多余撞击']),
 case('ambience','环境音 · 雨声与树叶','环境',8,'无人室外静景，检查持续声、空间感与异常人声。',
      'An empty garden path with wet stone paving, shrubs and a shallow puddle in light rain. There are no people or animals.',
      'A locked wide shot of a small rain-soaked garden in soft overcast daylight.',
      'For the full shot, light rain falls steadily and makes small ripples in the puddle. A gentle breeze moves the leaves slightly. The scene remains calm and continuous without sudden events.',
      'Continuous gentle rainfall: light droplets patter on wet stone and make softer splashes in the shallow puddle. Occasional quiet leaf rustling sits behind the rain. Natural outdoor depth, smooth continuous sound. No speech, dialogue, narration or humming.',
      'N/A',['雨声连续，没有突断或循环接缝','雨滴与树叶有层次，空间感自然','没有幻觉人声、脚步、雷声或音乐']),
 case('music','背景音乐 · 纯器乐','音乐',10,'低运动空镜配钢琴，检查旋律连贯、音色与伪人声。',
      'An empty sunlit living room with a sofa, a wooden coffee table and a light curtain. No people, musical instruments or performers are visible.',
      'A locked wide shot of the peaceful living room in warm afternoon light.',
      'The curtain moves almost imperceptibly in a light breeze throughout the shot. The camera and all furniture stay still. There are no visible impact events or dialogue.',
      'Only barely audible indoor room tone. No speech, dialogue, narration, singing or humming. The instrumental score is specified separately below.',
      'A gentle non-diegetic solo piano instrumental, around 72 BPM, with a simple coherent melodic phrase and soft warm notes. Smooth natural decay, moderate quiet level, no percussion and no vocals, choir, lyrics or humming. Let the short phrase resolve softly near the end.',
      ['钢琴旋律连续，音符衰减自然','没有破音、金属噪声或突然换乐器','无歌词、哼唱及伪人声；结尾自然']),
 case('dialogue_music','混合声音 · 对白与配乐','混合',10,'一位说话人加低音量钢琴，检查对白清晰度和音乐遮盖。',
      'S1 is an adult woman in a plain blue shirt, seated alone in a quiet living room, softly lit by a window.',
      'A locked medium close-up of S1. Her expression is gentle and her mouth is clearly visible.',
      '0–2 s: S1 looks thoughtfully toward the camera. 2–7 s: (S1), in a soft but clear natural female Mandarin voice at an unhurried conversational pace, says <d>[Chinese]别着急，我们还有时间，慢慢来。</d> Her lips move with her words. 7–10 s: she finishes and gives a small reassuring smile.',
      'Quiet room tone beneath one clear foreground speaking voice. Keep S1 intelligible, close and natural, with minimal reverberation. No additional speakers or narration.',
      'Very soft non-diegetic solo piano, a sparse warm melody around 68 BPM. Keep the piano well below the speaking voice throughout the dialogue, with spacious gaps between notes. No vocals, lyrics, humming, choir or percussion. Continue gently after the sentence ends.',
      ['对白清晰完整，音乐不盖住字音','音乐与人声同时存在，无互相吞掉','说话结束后音乐自然延续，不变成歌唱']),
]


def catalog():return [template(t['id']) for t in CASES]


def template(key):
    found=next((x for x in CASES if x['id']==key),None)
    if found is None:raise ValueError('通用测试案例不存在')
    result=copy.deepcopy(found)
    from .lab_languages import chinese,FIELDS
    result['variants']={'en':{key:result[key] for key in FIELDS},'zh':chinese(key)}
    return result


def create_case(store,key):
    t=template(key);e=store.create(t['name'])
    e.update(templateId=t['id'],templateVersion=2,**t['variants']['zh'],promptLanguage='zh',promptVariants=t['variants'],
             notes='试听检查：\n'+'\n'.join('□ '+x for x in t['checks']))
    e['settings']['seconds']=t['seconds']
    return store.save(e)


def prompt_issues(e):
    """Catch explicit structural and speech contradictions; not semantic QA."""
    issues=[];body=e['prompt']
    if not body.strip():issues.append('请先填写画面/对白提示词，或打开一个通用测试案例')
    for key in ('subject_definitions','summary','retention_analysis','detailed_description'):
        if len(re.findall(r'(?im)^\s*'+key+r'\s*:',body))>1:issues.append(key+' 出现多次，请合并内容或整套替换模板')
    if re.search(r'(?im)^\s*(overall_soundscape|non_diegetic_music)\s*:',body):
        issues.append('主提示词含环境音或音乐段落，请移到下方对应字段，避免重复发送')
    if re.search(r'<d>\s*\[Chinese\]',body,re.I):
        rest=re.sub(r'<d>.*?</d>','',body,flags=re.S|re.I)+'\n'+e['soundscape']
        if re.search(r'无人声|无对白|无对话|禁止(?:人声|对白|对话)|不要(?:人声|对白|对话)|保持闭口|\bno\s+(?:speech|dialogue|human voices?)\b',rest,re.I):
            issues.append('已写入中文台词，但画面/环境音仍要求无人声、无对白或闭口；请修改冲突要求')
    return issues
