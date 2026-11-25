// Bundled with the public protocol, HTML and chart by site/build.py.
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const SHA = /^[a-f0-9]{64}$/;
const TEXT = /^[\p{L}\p{N} .,'’()+&!_\-]+$/u;
const CPU = /^[\p{L}\p{N} ().@+,_®™-]+$/u;
const fields = (o, names) => o && typeof o === "object" && !Array.isArray(o) && Object.keys(o).every(k => names.includes(k));
function requireValue(ok) { if (!ok) throw new Error("Invalid score fields"); }
const integer = (x, min, max) => Number.isSafeInteger(x) && x >= min && x <= max;
const plain = (v, len, rx) => typeof v === "string" && v.length > 0 && v.length <= len && rx.test(v);
const emulators = {mGBA:"gba", Snes9x:"snes", bsnes:"snes", CartsSNES:"snes"};
export function validate(r) {
  if (r?.outcome==="failed") {
    const profile=Object.hasOwn(PROFILES,r.profile) && PROFILES[r.profile];
    requireValue(fields(r,["run_id","device_id","campaign_id","outcome","reason","game","profile","emulator","core_sha256","worker_sha256","os","arch","cpu"])
      && profile && r.profile.includes("-circuit-") && r.game===profile.title && Object.hasOwn(emulators,r.emulator) && profile.console===emulators[r.emulator]
      && ["timeout","checkpoint","measurement"].includes(r.reason) && ["Darwin","Linux","Windows"].includes(r.os) && /^(arm64|aarch64|amd64|x86_64)$/i.test(r.arch)
      && [r.device_id,r.campaign_id,r.run_id].every(x=>plain(x,36,UUID)) && [r.core_sha256,r.worker_sha256].every(x=>plain(x,64,SHA)) && plain(r.cpu,160,CPU));
    return r;
  }
  requireValue(fields(r,["run_id","game","profile","emulator","version","source_commit","core_sha256","worker_sha256",
    "os","arch","cpu","warmup_frames","rendered_frames","average_fps","low_1pct_fps","high_1pct_fps","timing",
    "comparison_id","campaign_id","device_id","accuracy","scene_checkpoints","scene_description","edition","paced","chips","build_recipe","execution","speed_x","video_mode"]));
  requireValue(Object.hasOwn(CORE_CONSOLES,r.emulator) && plain(r.run_id,36,UUID) && plain(r.game,90,TEXT));
  requireValue(["Darwin","Linux","Windows"].includes(r.os) && /^(arm64|aarch64|amd64|x86_64)$/i.test(r.arch));
  requireValue(plain(r.cpu,160,CPU) && plain(r.version,80,/^[a-zA-Z0-9 ()._+-]+$/) && SHA.test(r.core_sha256)
    && SHA.test(r.worker_sha256) && (r.source_commit === null || /^[0-9a-f]{40}$/.test(r.source_commit)));
  for (const key of ["comparison_id","campaign_id","device_id"]) if (key in r) requireValue(plain(r[key],36,UUID));
  for (const key of ["average_fps","high_1pct_fps","low_1pct_fps"]) requireValue(integer(r[key],0,1e8));
  requireValue(r.high_1pct_fps >= r.low_1pct_fps && integer(r.rendered_frames,100,1e6) && integer(r.warmup_frames,0,1e6));
  const profile = Object.hasOwn(PROFILES,r.profile) && PROFILES[r.profile];
  if (profile) {
    requireValue(profile.console === emulators[r.emulator] && r.game === profile.title && r.scene_description === profile.description
      && r.rendered_frames === profile.frames && r.warmup_frames === profile.warmup
      && profile.references.some(pair => JSON.stringify(pair) === JSON.stringify(r.scene_checkpoints)));
  } else {
    requireValue(CORE_CONSOLES[r.emulator].some(c=>r.profile===c+"-boot-no-input-v1") && !r.scene_checkpoints && !r.scene_description);
  }
  requireValue(Array.isArray(r.timing) && r.timing.length > 0 && r.timing.length <= 120);
  const keys = ["start_ms","end_ms","avg_fps","worst_fps","worst_ms","worst_frame","worst_at_ms"];
  let end=0, frame=0;
  for (const bin of r.timing) {
    requireValue(fields(bin,keys) && keys.every(k => Number.isFinite(bin[k]) && bin[k]>=0 && bin[k]<=1e10)
      && end === bin.start_ms && bin.end_ms > end && bin.worst_at_ms >= end && bin.worst_at_ms <= bin.end_ms
      && integer(bin.worst_frame,frame+1,r.rendered_frames) && integer(bin.avg_fps,0,1e8) && integer(bin.worst_fps,0,1e8));
    end=bin.end_ms; frame=bin.worst_frame;
  }
  requireValue(Math.abs(r.average_fps-1000*r.rendered_frames/end)<=1);
  const mode=r.video_mode, handheld=["gb","gbc","gba"].includes(r.profile.split("-")[0]);
  requireValue(fields(mode,["region","refresh_hz","source"]) && Number.isFinite(mode.refresh_hz)
    && mode.refresh_hz>=20 && mode.refresh_hz<=240 && (handheld?
      mode.region==="handheld" && mode.source==="lcd-clock" && Math.abs(mode.refresh_hz-4194304/70224)<1e-9 :
      ["NTSC","PAL"].includes(mode.region) && mode.source==="emulator-av")
    && Number.isFinite(r.speed_x) && Math.abs(r.speed_x-1000*r.rendered_frames/end/mode.refresh_hz)<1e-6);
  if (r.accuracy) {
    const color=r.profile==="gbc-boot-no-input-v1" && ["Gambatte","SameBoy"].includes(r.emulator);
    requireValue(color || Object.hasOwn(emulators,r.emulator));
    const names=color?COLOR_CHECKS:emulators[r.emulator]==="gba"?["ARM","Thumb","Memory"]:["65C816 basic","SPC700"];
    requireValue(fields(r.accuracy,["suite","core_sha256","worker_sha256","checks"]) && r.accuracy.suite===(color?"gbc-v1":"cpu-memory-v1")
      && r.accuracy.core_sha256===r.core_sha256 && r.accuracy.worker_sha256===r.worker_sha256
      && fields(r.accuracy.checks,names) && names.every(k=>["pass","fail","unresolved"].includes(r.accuracy.checks[k])));
  }
  if ("execution" in r)requireValue(r.execution==="x64-on-arm64" && r.os==="Windows" && /^(arm64|aarch64)$/i.test(r.arch));
  if ("build_recipe" in r) requireValue(r.build_recipe==="mgba-libretro-cmake-v1" && r.emulator==="mGBA" && r.source_commit);
  if ("edition" in r) requireValue(plain(r.edition,64,SHA));
  if ("paced" in r) requireValue(fields(r.paced,["frames","missed_deadlines","audio_underrun_frames","refresh_hz","sample_rate"])
    && integer(r.paced.frames,100,1e6) && integer(r.paced.missed_deadlines,0,r.paced.frames)
    && integer(r.paced.audio_underrun_frames,0,1e10) && r.paced.refresh_hz>=45 && r.paced.refresh_hz<=75
    && r.paced.sample_rate>=8000 && r.paced.sample_rate<=192000 && typeof r.paced.refresh_hz==="number" && typeof r.paced.sample_rate==="number");
  if ("chips" in r) requireValue(emulators[r.emulator]==="snes" && fields(r.chips,CHIP_CHECKS) && Object.values(r.chips).every(v=>["pass","fail","unresolved"].includes(v))
    && ["SA-1 multiply","Super FX immediate"].every(k=>["pass","fail","unresolved"].includes(r.chips[k])));
  return r;
}
const json=(v,status=200)=>Response.json(v,{status,headers:{"cache-control":"no-store","x-content-type-options":"nosniff"}});
async function payload(req) {
  if (req.headers.get("content-type")?.split(";")[0]!=="application/json" || !req.body) throw Error();
  const reader=req.body.getReader(), chunks=[];
  let size=0;
  while (true) {
    const {done,value}=await reader.read();
    if (done) break;
    size+=value.length;
    if(size>96000){await reader.cancel();throw Error();}
    chunks.push(value);
  }
  return new Response(new Blob(chunks)).json();
}
export default {async fetch(request,env) {
  const url=new URL(request.url), path=url.pathname, db=env.DB;
  if (request.method==="POST" && path==="/api/installs")return enroll(request,db);
  if (request.method==="POST" && path==="/api/runs") {
    const key=await authorize(request,db);
    if(typeof key!=="string")return key;
    let r;
    try {r=await signedRun(request,key);} catch {return json({error:"Invalid or oversized score"},400);}
    const data=JSON.stringify(r);
    const inserted=await db.prepare("INSERT OR IGNORE INTO runs(id,received,game,profile,emulator,campaign,device,payload) VALUES(?,unixepoch(),?,?,?,?,?,?)")
      .bind(r.run_id,r.game,r.profile,r.emulator,r.campaign_id??null,r.device_id??r.run_id,data).run();
    if (!inserted.meta.changes) {
      const old=await db.prepare("SELECT payload FROM runs WHERE id=?").bind(r.run_id).first();
      if(old?.payload!==data)return json({error:"Run ID already used"},409);
    }
    return json({url:url.origin+"/run/"+r.run_id},inserted.meta.changes?201:200);
  }
  if(request.method!=="GET")return json({error:"Unsupported method"},405);
  if(path==="/api/studies")return json(LAB);
  if(path==="/api/runs") {
    const clauses=[],params=[];
    for(const [key,col] of [["campaign","campaign"],["emulator","emulator"],["profile","profile"],["device","device"]]){
      const v=url.searchParams.get(key); if(v){clauses.push(col+"=?");params.push(v.slice(0,100));}
    }
    const search=url.searchParams.get("q");if(search){clauses.push("instr(lower(game),lower(?))>0");params.push(search.slice(0,90));}
    const cursor=url.searchParams.get("after");
    if(cursor){const [stamp,id]=cursor.split(".");if(!UUID.test(id)||!/^\d{1,12}$/.test(stamp))return json({error:"Invalid cursor"},400);
      clauses.push("(received,id)<(?,?)");params.push(Number(stamp),id);}
    const found=await db.prepare("SELECT id,received,payload FROM runs "+(clauses.length?"WHERE "+clauses.join(" AND "):"")+" ORDER BY received DESC,id DESC LIMIT 101").bind(...params).all();
    const page=found.results.slice(0,100);
    return json({rows:page.map(({received,payload})=>{const {timing,scene_checkpoints,proof,...r}=JSON.parse(payload);return {...r,received};}),
      next:found.results.length>100?page[99].received+"."+page[99].id:null});
  }
  if(path.startsWith("/api/run/") && UUID.test(path.slice(9))) {
    const row=await db.prepare("SELECT received,payload FROM runs WHERE id=?").bind(path.slice(9)).first();
    return row?json({...JSON.parse(row.payload),received:row.received}):json({error:"Score not found"},404);
  }
  if(path==="/client.js")return new Response(CLIENT,{headers:{"content-type":"text/javascript; charset=utf-8"}});
  if(path==="/"||["/compare","/rankings","/history","/library","/method"].includes(path)||/^\/(run|campaign)\/[a-f0-9-]{36}$/.test(path))
    return new Response(PAGE,{headers:{"content-type":"text/html; charset=utf-8","content-security-policy":"default-src 'self'; img-src 'self' data:; style-src 'unsafe-inline'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'","referrer-policy":"no-referrer"}});
  return json({error:"Page not found"},404);
}};
