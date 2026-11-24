import test from 'node:test';
import assert from 'node:assert/strict';
import {applyCase,promptIssues,switchLanguage} from '../web/src/lab-prompts.js';

const template={name:'中文单人',seconds:8,prompt:'detailed_description:\n(S1) says <d>[Chinese]你好。</d>',soundscape:'Quiet room tone beneath the dialogue.',music:'N/A'};
const original={id:'original',revision:5,campaign:'same-budget',prompt:'old instructions\ndetailed_description: No dialogue.',soundscape:'无人声、无对白。保持闭口',music:'old score',references:[{id:'img'}],audioReferences:[{id:'voice'}],settings:{seconds:5,seed:123,shift_audio:2.5},notes:'keep notes'};
test('language switches preserve independent edits, references and generation settings',()=>{
 const en={prompt:'detailed_description: (S1) <d>[Chinese]你好。</d>',soundscape:'Room tone',music:'N/A'};
 const zh={prompt:'detailed_description: (S1) <d>[Chinese]你好。</d>',soundscape:'室内底声',music:'N/A'};
 const start={...original,...en,promptLanguage:'en',promptVariants:{en,zh}};
 const changed=switchLanguage(start,'zh');changed.soundscape='修改后的中文底声';
 const back=switchLanguage(changed,'en');back.prompt+=' English edit';
 const again=switchLanguage(back,'zh');
 assert.equal(again.soundscape,'修改后的中文底声');assert.ok(again.promptVariants.en.prompt.endsWith('English edit'));
 assert.deepEqual(again.settings,start.settings);assert.deepEqual(again.references,start.references);
 assert.equal(again.campaign,start.campaign);assert.equal(start.soundscape,'Room tone');
 assert.throws(()=>switchLanguage({...start,promptVariants:{en}},'zh'));
});
test('full replacement removes contradictory sound fields and stale reference tags without appending',()=>{
 const before=structuredClone(original),after=applyCase(original,template);
 assert.deepEqual(original,before);assert.deepEqual(applyCase(after,template),after);
 assert.equal(after.soundscape,template.soundscape);assert.equal(after.music,'N/A');assert.equal(after.prompt,template.prompt);
 assert.deepEqual(after.references,[]);assert.deepEqual(after.audioReferences,[]);assert.equal(after.settings.seconds,8);
 assert.equal(after.settings.seed,123);assert.equal(after.settings.shift_audio,2.5);assert.equal(after.campaign,original.campaign);assert.equal(after.notes,original.notes);
 assert.deepEqual(promptIssues(after),[]);
});
test('live checks catch appended headings and speech bans, without treating no-vocals music as a dialogue ban',()=>{
 assert.ok(promptIssues({...original,prompt:'  '}).some(x=>x.includes('请先填写')));
 assert.ok(promptIssues({...original,prompt:template.prompt}).some(x=>x.includes('无人声')));
 assert.ok(promptIssues({...original,prompt:'detailed_description: one\ndetailed_description: two'}).some(x=>x.includes('多次')));
 assert.ok(promptIssues({...original,prompt:'overall_soundscape: extra'}).some(x=>x.includes('重复发送')));
 assert.deepEqual(promptIssues({...applyCase(original,template),music:'Piano, no vocals or lyrics.'}),[]);
});
