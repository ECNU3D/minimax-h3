import test from 'node:test';
import assert from 'node:assert/strict';
import {queueBlocked,itemBlocked,shotClearBlocked} from '../web/src/queue-policy.js';

test('single shot generation allows more jobs and unrelated version actions',()=>{
 const jobs=[{kind:'shot',target:'s001',status:'running'},{kind:'asset',target:'P01',status:'queued'}];
 assert.equal(queueBlocked(jobs),false);
 assert.equal(itemBlocked(jobs,'s001'),true);
 assert.equal(itemBlocked(jobs,'s002'),false);
 assert.equal(itemBlocked(jobs,'P01'),true);
 assert.equal(itemBlocked(jobs,'P02'),false);
});
test('video archival depends on this shot, not the project or GPU queue',()=>{
 const jobs=[{kind:'shot',target:'s001',status:'running',clearBlockedShotIds:['s001']},
  {kind:'assets_auto',status:'queued',clearBlockedShotIds:[]}];
 assert.equal(shotClearBlocked(jobs,'s002'),false);
 assert.equal(shotClearBlocked(jobs,'s001'),true);
 assert.equal(shotClearBlocked([{kind:'shots_auto',clearBlockedShotIds:['s002']}],'s001'),false);
 assert.equal(shotClearBlocked([{kind:'review',target:'s001',clearBlockedShotIds:['s001']}],'s001'),true);
});
test('automatic single shot protects its shared assets; flow and uncertain work block queue',()=>{
 assert.equal(itemBlocked([{kind:'shot_auto',target:'s001',ownedTargets:['P01'],status:'queued'}],'P01'),true);
 assert.equal(queueBlocked([{kind:'shot',status:'interrupted'}]),true);
 assert.equal(queueBlocked([{kind:'shots_auto',status:'running'}]),true);
 assert.equal(queueBlocked([{kind:'preflight',status:'queued'},{kind:'review',status:'paused'}]),false);
});
