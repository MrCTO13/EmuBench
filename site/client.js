const $=id=>document.getElementById(id), title=$("title"),intro=$("intro"),controls=$("controls"),out=$("results"),status=$("status");
const route=location.pathname.split("/")[1]||"browse", params=new URLSearchParams(location.search);
const demo=params.get("demo")==="1";
function localUrl(path){return demo?path+(path.includes("?")?"&":"?")+"demo=1":path;}
if(demo){
  const note=document.createElement("p");note.className="demo";note.append("The scores in this demo are fictional. ");
  const live=document.createElement("a");live.textContent="View published scores";live.href="/";note.append(live);document.getElementById("notice").append(note);
  for(const a of document.querySelectorAll("nav a"))if(!a.search)a.href=localUrl(a.pathname);
}
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
function buildLabel(id){return demo?id.split(" · ")[0]:id;}
function speedLabel(r){return Number.isFinite(r.speed_x)?r.speed_x.toFixed(2)+'×':'Unscored';}
function list(rows){
  return table(["Game / scene","Emulator","Console speed","Accuracy","Average FPS","1% low","1% high","Device"],rows.map(r=>[
    link(r.game,"/run/"+r.run_id),r.emulator+" "+(r.version||""),speedLabel(r),conformance(r).label,
    r.outcome==="failed"?"Failed · "+r.reason:String(r.average_fps),r.low_1pct_fps??"—",r.high_1pct_fps??"—",
    r.cpu+" · "+r.os+(r.execution?" · x64 on ARM64":"")]),"Benchmark results");
}
function empty(message,action){
  const block=make("div",null,"empty");
  block.append(make("strong",message));
  if(action)block.append(action);
  out.append(block);
}
async function get(path){const res=await fetch(path);if(!res.ok)throw Error(res.status===404?"This score could not be found.":"Scores are temporarily unavailable.");return res.json();}
const q=make("input"),checks=[],mode=make("select");q.type="search";q.name="q";q.value=params.get("q")||"";q.placeholder="e.g. Star Fox";
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
  form.onsubmit=e=>{e.preventDefault();const p=new URLSearchParams({q:q.value,emulators:checked().join(","),mode:mode.value});if(demo)p.set("demo","1");location.search=p;};
}
async function score() {
  const id=location.pathname.split("/")[2];info("Run details","");const r=demo?demoRows().find(row=>row.run_id===id):await get("/api/run/"+id);if(!r)throw Error("Example score not found.");info(r.game,r.emulator+" "+(r.version||"")+" · "+r.cpu+" · "+r.os+" "+r.arch+(r.execution?" · x64 on ARM64":""));
  if(r.outcome==="failed"){out.append(make("p","This scene failed during "+r.reason+". No FPS was scored."),link("View campaign","/campaign/"+r.campaign_id));return;}
  const cards=make("div",null,"cards");for(const [label,field] of [["Console speed","speed_x"],["Average FPS","average_fps"],["1% low FPS","low_1pct_fps"],["1% high FPS","high_1pct_fps"]]){const el=make("div",label);el.append(make("strong",field==="speed_x"?speedLabel(r):(r[field]??"Unavailable")));cards.append(el);}out.append(make("p","Accuracy · "+conformance(r).label),cards);if(r.timing)out.append(make("h2","Frame timing"));
  if(r.timing){const chart=make("div");out.append(chart);drawTiming(chart,r.timing);}else out.append(make("p","This runner times the whole process, from startup through rendering to exit. It reports one average."));
  const items=[["Repeatability",r.repeatability?.relative_spread!==undefined?"Three passes · "+(100*r.repeatability.relative_spread).toFixed(1)+"% spread":"Unrecorded"],["Host load",r.idle?r.idle.state+" ("+r.idle.cpu_percent+"% CPU before timing)":"Unknown"],["Runner",r.mode||"Legacy libretro"],["Video timing",r.video_mode?r.video_mode.region+" · "+r.video_mode.refresh_hz+" Hz ("+r.video_mode.source+")":"Unrecorded"],["Workload",r.profile],["Rendered frames",r.rendered_frames],["Warm-up frames",r.warmup_frames],["Submitted",new Date(r.received*1000).toISOString()],["Core SHA-256",r.core_sha256],["Worker SHA-256",r.worker_sha256]];
  if(r.hardware){const h=r.hardware;items.push(["Model",h.model||"Unavailable"],["RAM",Math.round(h.ram_bytes/2**30)+" GiB"],["OS build",h.os_build],["Physical CPU cores",h.physical_cores??"Unavailable"],["Core types",Object.entries(h.core_types).map(([k,v])=>v+" "+k).join(", ")||"Unavailable"],["GPU",h.gpu.join(", ")||"Unavailable"]);}
  for(const [i,w] of (r.conditions||[]).entries()){
    for(const [phase,s] of Object.entries(w)){
      const value=(v)=>v===null?"unavailable":String(v);
      items.push(["Pass "+(i+1)+" "+phase,[s.power_source||"unknown power","low power "+value(s.low_power),"thermal "+value(s.thermal_state),"CPU °C "+value(s.temperature_c),"throttled "+value(s.throttled)].join(" · ")]);
    }
  }
  if(r.campaign_id)items.push(["Campaign",link("All campaign scores","/campaign/"+r.campaign_id)]);
  if(r.paced)items.push(["Paced test",r.paced.missed_deadlines+" late deadlines / "+r.paced.frames+" frames; "+r.paced.audio_underrun_frames+" missing audio sample frames"]);
  for(const [k,v] of Object.entries({...r.accuracy?.checks,...r.chips}))items.push([k,v]);
  out.append(make("h2","Run details"),table(["Field","Value"],items.map(([k,v])=>[k,v instanceof Node?v:String(v)])));
  if(!demo && r.profile.includes("-circuit-"))out.append(make("p","Repeat using the matching local core"),make("code","emubench suite --emulator "+r.emulator.toLowerCase()+" --scene "+r.profile.split("-")[2]+" --core PATH --expect-core "+r.core_sha256+" --expect-worker "+r.worker_sha256));
}
function method(){
  info("Methodology","Carter Circuit has three repeatable scenes on Game Boy Advance and three on Super NES.");
  out.append(
    make("h2","How a run works"),
    make("p","The timing worker warms up each scene for 120 console frames, then times 600 frames at full speed. It uses a monotonic clock and requires a complete software frame every time. We check two reference images outside the timed section. We’re still testing how short a run can be for larger game libraries."),
    make("h2","Reading a score"),
    make("p","Console speed compares measured FPS with the console’s refresh rate for that region. A score of 2× means the emulator ran twice as fast as the original console. We calculate it before rounding the displayed FPS."),
    make("p","Average FPS is the frame count divided by elapsed time. The 1% low comes from the 99th percentile of frame times and the 1% high from the 1st percentile. We convert both to FPS. Open a run to see the slowest frame in each interval."),
    make("h2","How the SNES rankings work"),
    make("p","We compare two builds on the same device across easy, normal and hard scenes. For each scene we take the median FPS for each build, then compare them. The three speed ratios carry equal weight in a geometric mean. The ranking reports the median across installations."),
    make("p","With five or more installations we also show a 95% bootstrap interval, resampling by installation. We exclude groups with a missing scene or a reported scene failure. The table lists the coverage and failures. Community results come from players’ own machines."),
    make("h2","What the accuracy checks cover"),
    make("p","Each named test gets a pass, fail or unresolved result. The pass count covers only the tests listed for that run. Display, speaker and controller latency need separate hardware tests."),
    link("Read the Carter Circuit source","https://github.com/MrCTO13/EmuBench/blob/d9289f7c1625a920b7dad006d5b06fd3769ed036/emubench/circuit.py")
  );
}
async function browse(){
  const heading={browse:"Emulator benchmarks",campaign:"Campaign scores",compare:"Compare results",rankings:"Emulator rankings",history:"Version history"}[route];
  info(heading,{browse:"See how fast a game runs, where frame rates dip, and which accuracy checks pass.",campaign:"All the runs published from this batch.",compare:"Compare two emulators on the same device, or one emulator across devices.",rankings:"See the lab results and how emulator builds compare in community runs.",history:"See what changed between builds tested on the same machine and scene."}[route]);
  if(route==="browse"){
    document.querySelector(".lead").classList.add("home");
    document.querySelector(".feature").hidden=false;
  }
  filters();
  let rows=[],cursor=null;
  async function more(){
    const p=new URLSearchParams({q:q.value});if(route==="campaign")p.set("campaign",location.pathname.split("/")[2]);if(cursor)p.set("after",cursor);
    if(demo){ rows=demoRows().filter(r=>r.game.toLowerCase().includes(q.value.toLowerCase()));cursor=null;return; }
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
      studyPanel();out.append(make("h2","Community SNES rankings"),make("p","Each build must pass all five checks on an idle machine and finish within the three-pass timing limit."));
      const builds=[...new Set(filtered.filter(r=>!r.outcome && r.profile.startsWith("snes-circuit-")).map(build))].sort();
      if(builds.length<2){empty("No two builds have a full set of matching SNES runs yet.");return;}
      const a=make("select"),b=make("select");for(const v of builds){selectOption(a,v,buildLabel(v));selectOption(b,v,buildLabel(v));}b.selectedIndex=1;
      const l=make("label","Baseline"),m=make("label","Compare with");l.append(a);m.append(b);const panel=make("div",null,"tools"),result=make("div");panel.append(l,m);out.append(panel,result);
      function compare(){result.replaceChildren();if(a.value===b.value)return;const r=ranking(filtered,a.value,b.value);result.append(make("p",r.completed+" complete paired device/protocol groups out of "+r.eligible+" observed · "+r.failed+" reported failed attempts for the selected builds."));result.append(make("p",r.n?Math.round(100*r.ratio)+"% of baseline · "+r.n+" matched installations"+(r.interval?" · 95% interval "+r.interval.map(x=>Math.round(100*x)+"%").join(" to "):" · interval requires five installations"):"No complete matched suites."));if(r.matched.length){
          const bars=make("ul",null,"bars");for(const [name,ratio] of [[a.value,1],[b.value,r.ratio]]){const li=make("li",buildLabel(name)+" · "+Math.round(ratio*100)+"%");const bar=make("meter");bar.min=0;bar.max=Math.max(1,r.ratio)*1.1;bar.value=ratio;bar.setAttribute("aria-label",name);li.append(bar);bars.append(li);}result.append(bars,list(r.matched));
        }}a.onchange=b.onchange=compare;compare();
    }else if(route==="history"){
      const cohorts=[...group(filtered.filter(r=>r.device_id && !r.outcome),r=>[device(r),workload(r),r.worker_sha256,r.emulator].join("|")).values()].filter(g=>group(g,build).size>1);
      if(!cohorts.length)empty("Run two builds on the same device and scene to see the change here.");
      for(const g of cohorts){out.append(make("h2",g[0].game+" · "+g[0].emulator));const versions=[...group(g.sort((a,b)=>a.received-b.received),build)];let prev=null;
        out.append(table(["Build","First submitted (UTC)","Accuracy","Median speed","Raw FPS","Change","Samples"],versions.map(([ver,rs])=>{const fps=median(rs.map(r=>r.average_fps));const change=prev?Math.round(100*(fps/prev-1))+"%":"—";prev=fps;return [link(buildLabel(ver),"/run/"+rs[0].run_id),new Date(rs[0].received*1000).toISOString().slice(0,10),accuracyGroup(rs),speedLabel({speed_x:median(rs.map(r=>r.speed_x))}),String(Math.round(fps)),change,String(rs.length)];})));}
    }else{
      out.append(make("h2",demo?"Example runs":q.value?"Search results":"Published runs"));
      if(filtered.length)out.append(list(filtered));
      else if(!demo&&!q.value&&!rows.length&&route==="browse"){
        empty("No public runs yet.",link("See a sample Mario World comparison","/compare?q=Super+Mario+World&demo=1"));
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
