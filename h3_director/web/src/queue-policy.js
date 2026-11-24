const singles=new Set(['asset','shot','shot_auto','preflight','review']);
export function queueBlocked(pending){
 return pending.some(j=>!singles.has(j.kind)||j.status==='interrupted');
}
export function itemBlocked(pending,id){
 // A single-shot automatic task can also prepare shared reference assets.
 return queueBlocked(pending)||pending.some(j=>j.target===id||(j.kind==='shot_auto'&&(j.ownedTargets||[]).includes(id)));
}
export function shotClearBlocked(pending,id){
 return pending.some(j=>j.clearBlockedShotIds ? j.clearBlockedShotIds.includes(id) :
  (['shot','shot_auto','review'].includes(j.kind)&&j.target===id)||['auto','shots_auto','parse'].includes(j.kind));
}
