"""Independent single-shot experiments; source projects are read-only imports."""
import copy
from pathlib import Path
import re
import shutil
import sys
import time

from .project import ROOT,uid,read,write,digest,selected
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from scripts.h3_lab_config import settings,DEFAULTS


class LabStore:
    def __init__(self, data_folder):
        self.folder=Path(data_folder).resolve()/'lab'

    def path(self, experiment_id):
        if not isinstance(experiment_id,str) or not re.fullmatch(r'[a-f0-9]{12}',experiment_id):
            raise ValueError('测试 ID 无效')
        return self.folder/experiment_id/'experiment.json'

    def get(self, experiment_id):
        from .lab_languages import with_languages
        return with_languages(read(self.path(experiment_id)))

    def save(self, experiment):
        experiment['revision']=experiment.get('revision',0)+1
        experiment['updated']=time.time()
        write(self.path(experiment['id']),experiment)
        return experiment

    def list(self):
        rows=[read(p) for p in self.folder.glob('*/experiment.json')]
        return sorted(rows,key=lambda x:x['updated'],reverse=True)

    def create(self,name='单镜测试'):
        experiment=dict(id=uid(),name=str(name).strip()[:100] or '单镜测试',revision=0,
                        created=time.time(),prompt='',soundscape='',music='N/A',references=[],audioReferences=[],
                        settings=copy.deepcopy(DEFAULTS),runs=[],notes='',campaign='lab_'+uid(),rounds=[])
        return self.save(experiment)

    def update(self,experiment_id,changes,revision):
        experiment=self.get(experiment_id)
        if revision!=experiment['revision']:raise ValueError('测试已更新，请刷新后保存')
        if set(changes)-{'name','prompt','soundscape','music','settings','notes','referenceOrder','audioOrder','promptLanguage','promptVariants','videoProfile'}:
            raise ValueError('不支持的测试字段')
        if 'videoProfile' in changes:
            from .production import set_video_profile
            set_video_profile(experiment,changes['videoProfile'])
        for key in ('name','prompt','soundscape','music','notes'):
            if key in changes:
                if not isinstance(changes[key],str):raise ValueError('测试文本无效')
                experiment[key]=changes[key][:100 if key=='name' else 50000]
        if 'promptLanguage' in changes:
            if changes['promptLanguage'] not in ('zh','en'):raise ValueError('提示词语言无效')
            experiment['promptLanguage']=changes['promptLanguage']
        if 'promptVariants' in changes:
            from .lab_languages import validate_variants
            experiment['promptVariants']=validate_variants(changes['promptVariants'])
        elif 'promptLanguage' not in changes and all(key in changes for key in ('prompt','soundscape','music')):
            # An already-open old client may save a newly replaced template.
            from .lab_languages import with_languages
            experiment.pop('promptVariants',None);experiment.pop('promptLanguage',None)
            experiment=with_languages(experiment)
        experiment.setdefault('promptVariants',{})[experiment['promptLanguage']]={key:experiment[key] for key in ('prompt','soundscape','music')}
        if 'settings' in changes:
            if not isinstance(changes['settings'],dict):raise ValueError('测试参数无效')
            experiment['settings']=settings(changes['settings'])
        for field,collection in [('referenceOrder','references'),('audioOrder','audioReferences')]:
            if field not in changes:continue
            order=changes[field];byid={r['id']:r for r in experiment[collection]}
            if not isinstance(order,list) or len(order)!=len(set(order)) or set(order)-set(byid):
                raise ValueError('参考图顺序无效')
            experiment[collection]=[byid[key] for key in order]
        return self.save(experiment)

    def copy_reference(self,experiment,source,label,audio=False):
        source=Path(source);key=uid()
        collection='audioReferences' if audio else 'references'
        if len(experiment[collection])>=(3 if audio else 9):raise ValueError('参考素材数量已达上限')
        if audio:
            if source.suffix.lower() not in ('.wav','.flac','.mp3','.m4a','.ogg'):raise ValueError('不支持的参考音频格式')
            from .lab_audio import inspect_audio
            evidence=inspect_audio(source)
            if not 0<evidence['duration']<=30:raise ValueError('音频参考需在 30 秒以内')
        else:
            if source.suffix.lower() not in ('.png','.jpg','.jpeg','.webp'):raise ValueError('不支持的参考图格式')
            from PIL import Image
            with Image.open(source) as image:image.verify()
        target=self.path(experiment['id']).parent/'references'/(key+source.suffix.lower())
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
        record=dict(id=key,label=str(label)[:100],path=str(target),sha256=digest(target))
        if audio:record['inspection']=evidence
        experiment[collection].append(record)
        return record

    def import_shot(self,project,shot_id):
        shot=next(s for s in project['shots'] if s['id']==shot_id)
        resolved=[]
        for key in shot['refs']:
            asset=next(a for a in project['assets'] if a['id']==key);version=selected(asset)
            if not version or not version.get('files'):raise ValueError('镜头缺少参考图：'+asset['name'])
            f=version['files'][0]
            if digest(f['path'])!=f['sha256']:raise ValueError('参考图已改变：'+asset['name'])
            resolved.append((f['path'],asset['name']))
        experiment=self.create(project['name']+' · '+shot['name'])
        body=shot['prompt'];sound={}
        for key in ('non_diegetic_music','overall_soundscape'):
            match=re.search(r'(?im)^\s*'+key+r'\s*:\s*',body)
            if match:sound[key]=body[match.end():].strip();body=body[:match.start()].strip()
        experiment.update(prompt=body,soundscape=sound.get('overall_soundscape',''),music=sound.get('non_diegetic_music','N/A'),settings=settings(dict(seed=shot['seed'],seconds=shot['seconds'])),
                          source=dict(projectId=project['id'],projectName=project['name'],shotId=shot_id,
                                      projectRevision=project['revision'],importedAt=time.time()))
        for path,label in resolved:self.copy_reference(experiment,path,label)
        return self.save(experiment)

    def public(self,experiment):
        from .lab_languages import with_languages
        result=with_languages(experiment)
        from .production import selected_profile
        result['videoProfile']=selected_profile(experiment)
        for ref in result['references']+result['audioReferences']:
            ref['url']=f'/api/lab/{result["id"]}/references/{ref["id"]}'
        result['effectivePrompt']=compose(experiment)
        from .lab_templates import prompt_issues
        result['promptIssues']=prompt_issues(experiment)
        from .runner import budget
        result['budget']=budget(experiment)
        return result


def compose(experiment):
    return experiment['prompt'].strip()+'\noverall_soundscape: '+experiment['soundscape'].strip()+'\nnon_diegetic_music: '+(experiment['music'].strip() or 'N/A')
