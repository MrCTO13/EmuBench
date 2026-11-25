// Compare only runs that used the same workload and execution protocol.
function device(r){return [r.device_id,r.os,r.arch,r.cpu,r.execution||"native"].join("|");}
function workload(r){return [r.profile,r.edition || (r.profile.includes("-circuit-")?"public":r.comparison_id||r.run_id),r.mode||"legacy",r.video_mode?.region,r.video_mode?.refresh_hz,r.warmup_frames,r.rendered_frames].join("|");}
function build(r){return r.emulator+" "+r.version+" · "+r.core_sha256.slice(0,12);}
function group(rows,key){const m=new Map();for(const r of rows){const k=key(r);if(!m.has(k))m.set(k,[]);m.get(k).push(r);}return m;}
function median(values){const v=values.slice().sort((a,b)=>a-b),i=Math.floor(v.length/2);return v.length%2?v[i]:(v[i-1]+v[i])/2;}
function comparison(rows,mode) {
  const ok=rows.filter(r=>!r.outcome && r.device_id && (mode!=="devices" || r.edition || r.profile.includes("-circuit-")));
  const key=r=>workload(r)+"|"+(mode==="devices"?r.emulator+"|"+(r.source_commit && r.build_recipe ? r.source_commit+"|"+r.build_recipe : r.core_sha256):device(r)+"|"+r.worker_sha256);
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
  const relevant=rows.filter(r=>hashes.has(r.core_sha256));
  const groups=group(relevant.filter(r=>r.device_id && /^snes-circuit-(easy|normal|hard)-v2$/.test(r.profile)),r=>device(r)+"|"+r.worker_sha256);
  const devices=new Map(), matched=[];let complete=0;
  for(const runs of groups.values()){
    const ratios=[], links=[];
    for(const level of ["easy","normal","hard"]){
      const part=runs.filter(r=>r.profile==="snes-circuit-"+level+"-v2");
      if(part.some(r=>r.outcome==="failed"))break;
      const a=part.filter(r=>build(r)===baseline), b=part.filter(r=>build(r)===challenger);
      if(!a.length||!b.length||![...a,...b].every(r=>r.speed_x>0))break;
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
