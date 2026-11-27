// Compare only runs that used the same workload and execution protocol.
function device(r){return [r.device_id,r.os,r.arch,r.cpu,JSON.stringify(r.hardware||null),r.execution||"native"].join("|");}
// Power state of all three passes: "ac" only when every reading says plugged in with low-power mode off.
function powerState(r){const s=(r.conditions||[]).flatMap(w=>[w.before,w.after]);return s.length&&s.every(x=>x.power_source==="ac"&&x.low_power!==true)?"plugged in":s.some(x=>x.power_source==="battery")?"battery":s.some(x=>x.low_power)?"low power":"power unknown";}
function deviceClass(r){return (r.hardware?.device_class||r.cpu)+"|"+powerState(r);}
function deviceLabel(r){return (r.hardware?.device_class||r.cpu+" · "+r.os)+" · "+powerState(r);}
// Rankings use verified upstream builds on plugged-in, idle, cool machines only.
function rankable(r){return !r.outcome && r.standing==="verified" && powerState(r)==="plugged in" && r.idle?.state==="idle" && r.repeatability?.accepted===true;}
function workload(r){return [r.profile,r.edition || (r.profile.includes("-circuit-")?"public":r.comparison_id||r.run_id),r.mode||"legacy",r.video_mode?.region,r.video_mode?.refresh_hz,r.warmup_frames,r.window?r.rendered_frames/r.window.loops:r.rendered_frames].join("|");}
function build(r){return r.emulator+" "+r.version+" · "+r.core_sha256.slice(0,12);}
function group(rows,key){const m=new Map();for(const r of rows){const k=key(r);if(!m.has(k))m.set(k,[]);m.get(k).push(r);}return m;}
function median(values){const v=values.slice().sort((a,b)=>a-b),i=Math.floor(v.length/2);return v.length%2?v[i]:(v[i-1]+v[i])/2;}
function checkLabel(names,outcomes){
  const c={passed:0,failed:0,unreadable:0,"not run":0};
  for(const k of names){const v=outcomes[k];c[v==="pass"?"passed":v==="fail"?"failed":v==="unresolved"?"unreadable":"not run"]++;}
  if(c.passed===names.length)return names.length+"/"+names.length+" checks passed";
  return Object.entries(c).filter(([,n])=>n).map(([k,n])=>n+" "+k).join(" · ");
}
function conformance(r){
  const consoleId=r.profile.split("-")[0], names=consoleId==="snes"?["65C816 basic","SPC700","SA-1 multiply","Super FX immediate","DSP-1 fixed-point multiply"]:consoleId==="gba"?["ARM","Thumb","Memory"]:consoleId==="gbc"?Object.keys(r.accuracy?.checks||{}):[];
  const outcomes={...r.accuracy?.checks,...r.chips};
  if(!names.length || !Object.keys(outcomes).length)return {label:"Untested",passed:false};
  const count=names.filter(k=>outcomes[k]==="pass").length;
  return {label:checkLabel(names,outcomes),passed:count===names.length};
}
function accuracyGroup(rows){return [...new Set(rows.map(r=>conformance(r).label))].join(", ");}
function comparison(rows,mode) {
  const ok=rows.filter(r=>!r.outcome && r.device_id && r.standing!=="closed" && (mode!=="devices" || r.edition || r.profile.includes("-circuit-")));
  // Emulator comparisons stay on one installation; device comparisons need the same power state.
  const key=r=>workload(r)+"|"+(mode==="devices"?r.emulator+"|"+powerState(r)+"|"+(r.source_commit && r.build_recipe ? r.source_commit+"|"+r.build_recipe : r.core_sha256):device(r)+"|"+powerState(r)+"|"+r.worker_sha256);
  const variants=r=>mode==="devices"?device(r):build(r);
  return [...group(ok,key).values()].filter(g=>group(g,variants).size>=2);
}
function seededRandom(){let n=7919;return ()=>((n=(Math.imul(n,1664525)+1013904223)>>>0)/4294967296);}
function interval(values) {
  if(values.length<5)return null;
  const rand=seededRandom(),v=[];
  for(let i=0;i<1000;i++)v.push(median(Array.from(values,()=>values[Math.floor(rand()*values.length)])));
  v.sort((a,b)=>a-b);return [v[24],v[974]];
}
// Each installation casts one vote per build pair, with equal log weight for each required scene.
function ranking(rows,baseline,challenger) {
  const hashes=new Set(rows.filter(r=>!r.outcome && [baseline,challenger].includes(build(r))).map(r=>r.core_sha256));
  const relevant=rows.filter(r=>hashes.has(r.core_sha256) && (r.outcome==="failed" || rankable(r)));
  const groups=group(relevant.filter(r=>r.device_id && /^snes-circuit-(easy|normal|hard)-v2$/.test(r.profile)),r=>device(r)+"|"+r.worker_sha256);
  const devices=new Map(), matched=[];let complete=0;
  for(const runs of groups.values()){
    const ratios=[], links=[];
    for(const level of ["easy","normal","hard"]){
      const part=runs.filter(r=>r.profile==="snes-circuit-"+level+"-v2");
      if(relevant.some(r=>r.outcome==="failed" && r.profile==="snes-circuit-"+level+"-v2" && r.device_id===runs[0].device_id && r.worker_sha256===runs[0].worker_sha256))break;
      const a=part.filter(r=>build(r)===baseline), b=part.filter(r=>build(r)===challenger);
      if(!a.length||!b.length||[...a,...b].some(r=>!conformance(r).passed || r.repeatability?.accepted!==true || r.idle?.state!=="idle")||![...a,...b].every(r=>r.speed_x>0))break;
      ratios.push(median(b.map(r=>r.speed_x))/median(a.map(r=>r.speed_x)));links.push(...a,...b);
    }
    if(ratios.length===3){
      complete++;
      const id=runs[0].device_id;
      if(!devices.has(id))devices.set(id,[]);
      devices.get(id).push(Math.exp(ratios.reduce((sum,x)=>sum+Math.log(x),0)/3));matched.push(...links);
    }
  }
  const vals=[...devices.values()].map(median);
  return {completed:complete,eligible:groups.size,failed:relevant.filter(r=>r.outcome==="failed").length,n:vals.length,ratio:vals.length?median(vals):null,interval:interval(vals),matched};
}
