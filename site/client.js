const $=id=>document.getElementById(id), title=$("title"),intro=$("intro"),controls=$("controls"),out=$("results"),status=$("status");
const route=location.pathname.split("/")[1]||"browse", params=new URLSearchParams(location.search);
function localUrl(path){return path;}
const make=(tag,text,cls)=>{const e=document.createElement(tag);if(text!=null)e.textContent=text;if(cls)e.className=cls;return e;};
function link(text,url){const a=make("a",text);a.href=url.startsWith("/")?localUrl(url):url;return a;}
function table(headers,rows,caption) {
  const wrap=make("div",null,"wrap"), t=make("table"), head=make("tr"), body=make("tbody");
  const name=caption||out.querySelector("h2:last-of-type")?.textContent||title.textContent;
  t.append(make("caption",name,"sr"));
  wrap.tabIndex=0;wrap.setAttribute("role","region");wrap.setAttribute("aria-label",name);
  const numeric=headers.map(h=>/speed|FPS|1%|Samples|Change/i.test(h));
  for(const [i,h] of headers.entries()){
    const th=make("th",h,numeric[i]?"num":"");th.scope="col";head.append(th);
  }
  t.createTHead().append(head);
  for(const cells of rows){
    const tr=make("tr");
    cells.forEach((value,i)=>{
      const td=make("td");td.className=numeric[i]?"num":"detail-cell";
      if(headers[i]==="Console speed")td.classList.add("primary-num");
      td.append(value);tr.append(td);
    });
    body.append(tr);
  }
  t.append(body);wrap.append(t);return wrap;
}
function go(){location.href=localUrl("/compare?"+new URLSearchParams({q:q.value,emulators:[...checked()].join(",")}));}
function info(heading,copy){title.textContent=heading;intro.textContent=copy;document.title=heading+" · EmuBench";}
function buildLabel(id){return id;}
function speedLabel(r){return Number.isFinite(r.speed_x)?r.speed_x.toFixed(2)+'×':'Unscored';}
const STANDING={verified:"Verified build",custom:"Custom build · not ranked",closed:"Closed build · unreproducible, not ranked"};
function standingLabel(r){return STANDING[r.standing]||STANDING.custom;}
function targetLabel(r){return r.video_mode?r.video_mode.refresh_hz.toFixed(2)+" FPS "+(r.video_mode.region==="handheld"?"":r.video_mode.region):"—";}
function list(rows){
  return table(["Game / scene","Emulator","Build","Console speed","Average FPS","1% low","Min FPS","Native target","Smoke checks","Device"],rows.map(r=>[
    link(r.game,"/run/"+r.run_id),r.emulator+" "+(r.version||""),standingLabel(r),speedLabel(r),
    r.outcome==="failed"?"Failed · "+r.reason:String(r.average_fps),r.low_1pct_fps??"—",r.min_fps??"—",targetLabel(r),conformance(r).label,
    deviceLabel(r)+(r.execution?" · x64 on ARM64":"")]),"Benchmark results");
}
function empty(message,action){
  const block=make("div",null,"empty");
  block.append(make("strong",message));
  if(action)block.append(action);
  out.append(block);
}
async function get(path){const res=await fetch(path);if(!res.ok)throw Error(res.status===404?"This score could not be found.":"Scores are temporarily unavailable.");return res.json();}
const q=make("input"),checks=[],mode=make("select");q.type="search";q.name="q";q.value=params.get("q")||"";q.placeholder="e.g. Carter Circuit";
function checked(){return checks.filter(c=>c.checked).map(c=>c.value);}
function selectOption(el,value,label){const o=make("option",label);o.value=value;el.append(o);}
function filters() {
  const form=make("form",null,"tools"), label=make("label","Game or ROM name","query");label.append(q);form.append(label);
  if(route==="compare"){selectOption(mode,"emulators","Emulators on one device");selectOption(mode,"devices","Devices running one build");mode.value=params.get("mode")==="devices"?"devices":"emulators";const l=make("label","Compare");l.append(mode);form.append(l);}
  const b=make("button","Search");form.append(b);document.getElementById("search").append(form);
  const fs=make("fieldset"),legend=make("legend","Emulators");fs.append(legend);
  const initial=params.get("emulators")?.split(",");
  for(const key of Object.keys(CORE_CONSOLES)){const l=make("label"),c=make("input");c.type="checkbox";c.checked=initial?initial.includes(key):true;c.value=key;checks.push(c);l.append(c," "+key);fs.append(l);}
  const disclosure=make("details"),summary=make("summary","Filter emulators");
  disclosure.append(summary,fs);controls.append(disclosure);
  if(route==="compare")disclosure.open=true;
  function summarize(){
    const visible=checks.filter(c=>!c.parentElement.hidden);
    const n=visible.filter(c=>c.checked).length;
    summary.textContent="Emulator filters · "+(n===visible.length?"All "+n:n+" of "+visible.length);
  }
  fs.addEventListener("change",summarize);summarize();
  disclosure.updateLabel=summarize;
  if(route==="browse"){const compare=make("button","Compare selected emulators","secondary");compare.onclick=go;controls.append(compare);}
  form.onsubmit=e=>{e.preventDefault();const p=new URLSearchParams({q:q.value,emulators:checked().join(","),mode:mode.value});location.search=p;};
}
async function score() {
  const id=location.pathname.split("/")[2];info("Run details","");const r=await get("/api/run/"+id);info(r.game,r.emulator+" "+(r.version||"")+" · "+r.cpu+" · "+r.os+" "+r.arch+(r.execution?" · x64 on ARM64":""));
  if(r.outcome==="failed"){out.append(make("p","This scene failed during "+r.reason+". No FPS was scored."),link("View campaign","/campaign/"+r.campaign_id));return;}
  const cards=make("div",null,"cards");for(const [label,field] of [["Console speed","speed_x"],["Average FPS","average_fps"],["1% low FPS","low_1pct_fps"],["Minimum FPS","min_fps"],["Native target","target"]]){const el=make("div",label);el.append(make("strong",field==="speed_x"?speedLabel(r):field==="target"?targetLabel(r):(r[field]??"Unavailable")));cards.append(el);}
  out.append(make("p",standingLabel(r)+" · Smoke checks · "+conformance(r).label+" · "+deviceLabel(r)),cards);if(r.timing)out.append(make("h2","Frame timing"));
  if(r.timing){const chart=make("div");out.append(chart);drawTiming(chart,r.timing);}else out.append(make("p","This runner times the whole process, from startup through rendering to exit. It reports one average."));
  const items=[["Repeatability",r.repeatability?.relative_spread!==undefined?"Three passes · "+(100*r.repeatability.relative_spread).toFixed(1)+"% spread (limit "+(100*(r.repeatability.max_spread??0.1)).toFixed(0)+"%)":"Unrecorded"],["Timed window",r.window?(r.window.timed_ns/1e9).toFixed(1)+" s · scene played "+r.window.loops+"× from the same saved state, identical frames every time":"Unrecorded"],["Device class",r.hardware?.device_class||"Unrecorded"],["Host load",r.idle?r.idle.state+" ("+r.idle.cpu_percent+"% CPU before timing)":"Unknown"],["Runner",r.mode||"Legacy libretro"],["Video timing",r.video_mode?r.video_mode.region+" · "+r.video_mode.refresh_hz+" Hz ("+r.video_mode.source+")":"Unrecorded"],["Workload",r.profile],["Rendered frames",r.rendered_frames],["Warm-up frames",r.warmup_frames],["Submitted",new Date(r.received*1000).toISOString()],["Core SHA-256",r.core_sha256],["Worker SHA-256",r.worker_sha256]];
  if(r.hardware){const h=r.hardware;items.push(["Model",h.model||"Unavailable"],["RAM",Math.round(h.ram_bytes/2**30)+" GiB"],["OS build",h.os_build],["Physical CPU cores",h.physical_cores??"Unavailable"],["Core types",Object.entries(h.core_types).map(([k,v])=>v+" "+k).join(", ")||"Unavailable"],["GPU",h.gpu.join(", ")||"Unavailable"]);}
  for(const [i,w] of (r.conditions||[]).entries()){
    for(const [phase,s] of Object.entries(w)){
      const value=(v)=>v===null?"unavailable":String(v);
      items.push(["Pass "+(i+1)+" "+phase,[s.power_source||"unknown power","low power "+value(s.low_power),"thermal "+value(s.thermal_state),"CPU °C "+value(s.temperature_c),"CPU MHz "+value(s.cpu_mhz??null),"throttled "+value(s.throttled)].join(" · ")]);
    }
  }
  if(r.campaign_id)items.push(["Campaign",link("All campaign scores","/campaign/"+r.campaign_id)]);
  if(r.paced)items.push(["Paced test",r.paced.missed_deadlines+" late deadlines / "+r.paced.frames+" frames; "+r.paced.audio_underrun_frames+" missing audio sample frames"]);
  for(const [k,v] of Object.entries({...r.accuracy?.checks,...r.chips}))items.push([k,v]);
  out.append(make("h2","Run details"),table(["Field","Value"],items.map(([k,v])=>[k,v instanceof Node?v:String(v)])));
  if(r.profile.includes("-circuit-"))out.append(make("p","Repeat using the matching local core"),make("code","emubench suite --emulator "+r.emulator.toLowerCase()+" --scene "+r.profile.split("-")[2]+" --core PATH --expect-core "+r.core_sha256+" --expect-worker "+r.worker_sha256));
}
function method(){
  info("Methodology","How a run is timed, what gets ranked, and who runs EmuBench.");
  out.append(
    make("h2","Who runs EmuBench"),
    make("p",DISCLOSURE),
    make("h2","How a run works"),
    make("p","Every emulator runs in the same small libretro harness, in its own process, with no frame skipping and no audio device. The harness warms up each scene, then times the same frames at full speed with a monotonic clock. If that takes less than 10 seconds, it restores a saved state from the start of the scene and plays it again, until at least 10 seconds of frames are timed. Every repeat must draw exactly the same sampled frames, which proves the emulator really rendered them."),
    make("p","Sampled frames are copied during the run and checked afterwards, so the harness's own checks never count as emulator time. The sampled frames move at random on every run. A run is three fresh processes with a short cool-down between them. All three must agree within 3%, and none may run hot or throttled, or the result stays private."),
    make("h2","Reading a score"),
    make("p","Console speed compares measured FPS with the console’s native refresh rate for that region (for example 60.10 FPS for an NTSC Super NES, 50.01 for PAL, 59.73 for Game Boy Advance). 2× means twice as fast as the original console."),
    make("p","Average FPS is frames divided by time. The 1% low comes from the 99th percentile of frame times. Minimum FPS is the single slowest frame. Open a run to see the slowest frame in each interval."),
    make("h2","What gets ranked"),
    make("p","Only verified builds are ranked: emulator files whose SHA-256 the lab matched to an official upstream release or signed nightly. Modified or self-built emulators show as custom builds and are never ranked. Closed emulators that nobody else can download, including CartsSNES, are shown as unreproducible and never ranked."),
    make("p","Rankings only compare runs from the same device class and power state (plugged in, low-power mode off). Builds are compared on the same installation, scene by scene, and combined with a geometric mean. With five or more installations we show a 95% bootstrap interval."),
    make("h2","EmuBench 1 score"),
    make("p","EmuBench 1 is a fixed set of Carter gameplay replays. A reference handheld (RG35XX SP class) running pinned emulators scores 1000. The Device score shows how your hardware compares running those same emulators. The Emulator score compares an emulator with the reference emulator on the same machine, so the hardware cancels out. Accuracy is a separate number and is never mixed into speed. Playable % is the share of scenes that hold full speed, including the 1% low. The reference device is still being measured, so no EmuBench 1 scores are published yet."),
    make("h2","What the smoke checks cover"),
    make("p","Each run can include a few upstream CPU and memory test programs. They are smoke tests, not an accuracy score: most serious emulators pass them all. Each test shows pass, fail, unreadable or not run, and tests that were not run never count as failures. Display, speaker and controller latency need separate hardware tests."),
    link("Read the source","https://github.com/MrCTO13/EmuBench")
  );
}
async function browse(){
  const heading={browse:"Emulator benchmarks",campaign:"Campaign scores",compare:"Compare results",rankings:"Emulator rankings",history:"Version history"}[route];
  info(heading,{browse:"See how fast a scene runs, where frame rates dip, and how it compares on the same hardware.",campaign:"All the runs published from this batch.",compare:"Compare two emulators on the same device, or one emulator across devices.",rankings:"See the lab results and how emulator builds compare in community runs.",history:"See what changed between builds tested on the same machine and scene."}[route]);
  if(route==="browse"){
    document.querySelector(".lead").classList.add("home");
    document.querySelector(".feature").hidden=false;
  }
  filters();
  let rows=[],cursor=null;
  async function more(){
    const p=new URLSearchParams({q:q.value});if(route==="campaign")p.set("campaign",location.pathname.split("/")[2]);if(cursor)p.set("after",cursor);
    const page=await get("/api/runs?"+p);rows.push(...page.rows);cursor=page.next;
  }
  await more();
  // Comparisons need the entire filtered cohort. The browser's score table pages on demand.
  if(["compare","rankings","history"].includes(route))while(cursor)await more();
  if(q.value.trim() && (route==="compare" || route==="browse") && rows.length){
    const consoles=new Set(rows.map(r=>r.profile.split("-")[0]));
    for(const c of checks)c.parentElement.hidden=!CORE_CONSOLES[c.value].some(system=>consoles.has(system));
  }
  controls.querySelector("details")?.updateLabel();
  function render(){
    out.replaceChildren();const filtered=rows.filter(r=>checked().includes(r.emulator));
    if(route==="compare"){
      const groups=comparison(filtered,mode.value);if(!groups.length)empty("No two runs match this selection yet.");
      for(const g of groups){
        const bars=make("ul",null,"bars"),sets=group(g,mode.value==="devices"?device:build);
        const values=[...sets.values()].map(rs=>[mode.value==="devices"?rs[0].cpu+" · "+rs[0].os:build(rs[0]),median(rs.map(r=>r.speed_x)),accuracyGroup(rs)]);
        const max=Math.max(1,...values.map(row=>row[1]));
        for(const [label,speed,accuracy] of values.filter(v=>Number.isFinite(v[1]))){
          const li=make("li"),heading=make("div",null,"bar-heading"),reading=make("span",null,"bar-reading");
          const name=mode.value==="devices"?label:buildLabel(label);
          reading.append(make("strong",speed.toFixed(2)+"×")," · "+accuracy);
          heading.append(make("b",name),reading);
          const bar=make("meter");bar.max=max;bar.value=speed;bar.setAttribute("aria-label",name);li.append(heading,bar);bars.append(li);
        }
        out.append(make("h2",g[0].game),make("p",mode.value==="devices"?g[0].emulator+" "+g[0].version:g[0].cpu+" · "+g[0].os,"note"),bars,list(g));
      }
    }else if(route==="rankings"){
      studyPanel();out.append(make("h2","Community SNES rankings"),make("p","Verified builds only. Each build must pass all five checks on an idle machine, plugged in, and pass the three-pass timing gate. Runs are only compared within one device class."));
      const classes=[...new Set(filtered.filter(rankable).map(deviceClass))].sort();
      if(!classes.length){empty("No verified SNES runs yet.");return;}
      const dc=make("select");for(const v of classes)selectOption(dc,v,v.split("|")[0]+" · "+v.split("|")[1]);
      const dl=make("label","Device class");dl.append(dc);out.append(dl);
      const inClass=()=>filtered.filter(r=>rankable(r)&&deviceClass(r)===dc.value);
      const builds=[...new Set(inClass().filter(r=>r.profile.startsWith("snes-circuit-")).map(build))].sort();
      if(builds.length<2){empty("No two builds have a full set of matching SNES runs yet.");return;}
      const a=make("select"),b=make("select");for(const v of builds){selectOption(a,v,buildLabel(v));selectOption(b,v,buildLabel(v));}b.selectedIndex=1;
      const l=make("label","Baseline"),m=make("label","Compare with");l.append(a);m.append(b);const panel=make("div",null,"tools"),result=make("div");panel.append(l,m);out.append(panel,result);
      function compare(){result.replaceChildren();if(a.value===b.value)return;const r=ranking(inClass(),a.value,b.value);result.append(make("p",r.completed+" complete paired device/protocol groups out of "+r.eligible+" observed · "+r.failed+" reported failed attempts for the selected builds."));result.append(make("p",r.n?Math.round(100*r.ratio)+"% of baseline · "+r.n+" matched installations"+(r.interval?" · 95% interval "+r.interval.map(x=>Math.round(100*x)+"%").join(" to "):" · interval requires five installations"):"No complete matched suites."));if(r.matched.length){
          const bars=make("ul",null,"bars");for(const [name,ratio] of [[a.value,1],[b.value,r.ratio]]){const li=make("li",buildLabel(name)+" · "+Math.round(ratio*100)+"%");const bar=make("meter");bar.min=0;bar.max=Math.max(1,r.ratio)*1.1;bar.value=ratio;bar.setAttribute("aria-label",name);li.append(bar);bars.append(li);}result.append(bars,list(r.matched));
        }}a.onchange=b.onchange=compare;dc.onchange=()=>render();compare();
    }else if(route==="history"){
      const cohorts=[...group(filtered.filter(r=>r.device_id && !r.outcome),r=>[device(r),workload(r),r.worker_sha256,r.emulator].join("|")).values()].filter(g=>group(g,build).size>1);
      if(!cohorts.length)empty("Run two builds on the same device and scene to see the change here.");
      for(const g of cohorts){out.append(make("h2",g[0].game+" · "+g[0].emulator));const versions=[...group(g.sort((a,b)=>a.received-b.received),build)];let prev=null;
        out.append(table(["Build","First submitted (UTC)","Accuracy","Median speed","Raw FPS","Change","Samples"],versions.map(([ver,rs])=>{const fps=median(rs.map(r=>r.average_fps));const change=prev?Math.round(100*(fps/prev-1))+"%":"—";prev=fps;return [link(buildLabel(ver),"/run/"+rs[0].run_id),new Date(rs[0].received*1000).toISOString().slice(0,10),accuracyGroup(rs),speedLabel({speed_x:median(rs.map(r=>r.speed_x))}),String(Math.round(fps)),change,String(rs.length)];})));}
    }else{
      out.append(make("h2",q.value?"Search results":"Published runs"));
      if(filtered.length)out.append(list(filtered));
      else if(!q.value&&!rows.length&&route==="browse"){
        empty("No public runs yet. Lab runs are being measured before launch.");
        const start=make("section",null,"first-run");
        start.append(make("h3","Benchmark Cartervania"),make("p","Run the included Game Boy Advance replay with mGBA. Your result stays on this device until you share it."),make("code","emubench carter --emulator mgba --scene normal"));
        out.append(start);
      }else{
        empty("No scores match these filters.",link("Clear filters","/"));
      }
      if(cursor){const next=make("button","Load more scores");next.onclick=async()=>{next.disabled=true;try{await more();render();}catch(e){status.textContent=e.message;next.disabled=false;}};out.append(next);}
    }
  }
  for(const c of checks)c.onchange=render;mode.onchange=render;render();
}
(async()=>{try{for(const a of document.querySelectorAll("nav a"))if(a.pathname===location.pathname||(route==="run"&&a.pathname==="/"))a.setAttribute("aria-current","page");if(route==="library")libraryPage();else if(route==="method")method();else if(route==="run")await score();else await browse();status.textContent="";}catch(e){status.textContent=e.message;}})();
