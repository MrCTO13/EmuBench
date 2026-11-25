const $=id=>document.getElementById(id), title=$("title"),intro=$("intro"),controls=$("controls"),out=$("results"),status=$("status");
const route=location.pathname.split("/")[1]||"browse", params=new URLSearchParams(location.search);
const demo=params.get("demo")==="1";
function localUrl(path){return demo?path+(path.includes("?")?"&":"?")+"demo=1":path;}
if(demo){
  const note=document.createElement("p");note.className="demo";note.append("Example data · Fictional FPS for exploring the browser. ");
  const live=document.createElement("a");live.textContent="View published scores";live.href="/";note.append(live);title.before(note);
  for(const a of document.querySelectorAll("nav a"))if(!a.search)a.href=localUrl(a.pathname);
}
const make=(tag,text,cls)=>{const e=document.createElement(tag);if(text!=null)e.textContent=text;if(cls)e.className=cls;return e;};
function link(text,url){const a=make("a",text);a.href=url.startsWith("/")?localUrl(url):url;return a;}
function table(headers,rows){const wrap=make("div",null,"wrap"),t=make("table"),head=make("tr"),body=make("tbody");for(const h of headers){const th=make("th",h);th.scope="col";head.append(th);}t.createTHead().append(head);for(const cells of rows){const tr=make("tr");for(const c of cells){const td=make("td");td.append(c);tr.append(td);}body.append(tr);}t.append(body);wrap.append(t);return wrap;}
function go(){location.href=localUrl("/compare?"+new URLSearchParams({q:q.value,emulators:[...checked()].join(",")}));}
function info(heading,copy){title.textContent=heading;intro.textContent=copy;document.title=heading+" · Emu Bench";}
function list(rows){return table(["Game / scene","Emulator","System","Average FPS","1% low","1% high"],rows.map(r=>[link(r.game,"/run/"+r.run_id),r.emulator+" "+(r.version||""),r.cpu+" · "+r.os,r.outcome==="failed"?"Failed · "+r.reason:String(r.average_fps),String(r.low_1pct_fps??"—"),String(r.high_1pct_fps??"—")]));}
function empty(message){out.append(make("p",message,"empty"));}
async function get(path){const res=await fetch(path);if(!res.ok)throw Error(res.status===404?"This score could not be found.":"Scores are temporarily unavailable.");return res.json();}
const q=make("input"),checks=[],mode=make("select");q.type="search";q.name="q";q.value=params.get("q")||"";q.placeholder="Game or ROM name";
function checked(){return checks.filter(c=>c.checked).map(c=>c.value);}
function selectOption(el,value,label){const o=make("option",label);o.value=value;el.append(o);}
function filters() {
  const form=make("form",null,"tools"), label=make("label","Search scores");label.append(q);form.append(label);
  if(route==="compare"){selectOption(mode,"emulators","Emulators on one device");selectOption(mode,"devices","Devices running one build");mode.value=params.get("mode")==="devices"?"devices":"emulators";const l=make("label","Compare");l.append(mode);form.append(l);}
  const b=make("button","Search");form.append(b);controls.append(form);
  const fs=make("fieldset"),legend=make("legend","Emulators");fs.append(legend);
  const initial=params.get("emulators")?.split(",");
  for(const key of ["mGBA","Snes9x","bsnes","CartsSNES"]){const l=make("label"),c=make("input");c.type="checkbox";c.checked=initial?initial.includes(key):true;c.value=key;checks.push(c);l.append(c," "+key);fs.append(l);}
  controls.append(fs);
  if(route==="browse"){const compare=make("button","Compare selected emulators");compare.onclick=go;controls.append(compare);}
  form.onsubmit=e=>{e.preventDefault();const p=new URLSearchParams({q:q.value,emulators:checked().join(","),mode:mode.value});if(demo)p.set("demo","1");location.search=p;};
}
async function score() {
  const id=location.pathname.split("/")[2];const r=demo?demoRows().find(row=>row.run_id===id):await get("/api/run/"+id);if(!r)throw Error("Example score not found.");info(r.game,r.emulator+" "+(r.version||"")+" · "+r.cpu+" · "+r.os+" "+r.arch);
  if(r.outcome==="failed"){out.append(make("p","This scene failed during "+r.reason+". No FPS was scored."),link("View campaign","/campaign/"+r.campaign_id));return;}
  const cards=make("div",null,"cards");for(const [label,field] of [["Average FPS","average_fps"],["1% low FPS","low_1pct_fps"],["1% high FPS","high_1pct_fps"]]){const el=make("div",label);el.append(make("strong",r[field]));cards.append(el);}out.append(cards,make("h2","Frame timing"));
  const chart=make("div");out.append(chart);drawTiming(chart,r.timing);out.append(make("p","Blue shows average FPS per interval. Orange marks the slowest frame. Hover a point for its frame and time."));
  const items=[["Workload",r.profile],["Rendered frames",r.rendered_frames],["Warm-up frames",r.warmup_frames],["Submitted",new Date(r.received*1000).toISOString()],["Core SHA-256",r.core_sha256],["Worker SHA-256",r.worker_sha256]];
  if(r.campaign_id)items.push(["Campaign",link("All campaign scores","/campaign/"+r.campaign_id)]);
  if(r.paced)items.push(["Paced test",r.paced.missed_deadlines+" late deadlines / "+r.paced.frames+" frames; "+r.paced.audio_underrun_frames+" missing audio sample frames"]);
  for(const [k,v] of Object.entries({...r.accuracy?.checks,...r.chips}))items.push([k,v]);
  out.append(make("h2","Run details"),table(["Field","Value"],items.map(([k,v])=>[k,v instanceof Node?v:String(v)])));
  if(r.profile.includes("-circuit-"))out.append(make("p","Repeat using the matching local core"),make("code","emubench suite --emulator "+r.emulator.toLowerCase()+" --scene "+r.profile.split("-")[2]+" --core PATH --expect-core "+r.core_sha256+" --expect-worker "+r.worker_sha256));
}
function method(){info("Methodology","Carter Circuit v1 covers six deterministic scenes across Game Boy Advance and Super NES.");out.append(make("h2","What an FPS score measures"),make("p","The external native worker warms up for 120 console frames, times 600 uncapped frames with a monotonic clock, and requires one complete software framebuffer on every measured frame. Two untimed checkpoints verify the scene. The shortest reliable window for game libraries is still being calibrated."),make("p","Average FPS is frame count divided by elapsed time. The 1% low and high are the reciprocals of the 99th and 1st frame-time percentiles. The details page shows each interval’s slowest frame."),make("h2","Comparison rules"),make("p","For SNES rankings, each device needs both builds on easy, normal and hard. Take the median FPS per scene and build. Weight the three performance ratios equally using a geometric mean, then take the median across installations. Show a 95% device-bootstrap interval from five installations. Missing scenes are excluded and coverage is displayed. Every submission is self-reported. Public installations and completed runs alone cannot establish an independent laboratory or a game compatibility rate."),make("h2","Accuracy"),make("p","Report each named diagnostic as passed, failed or unresolved. A pass rate applies only to the listed checks. Headless frame delivery excludes physical display, speaker and controller latency."),link("Read the workload source","https://github.com/MrCTO13/EmuBench/blob/main/emubench/circuit.py"));}
async function browse(){
  const heading={browse:"Score browser",campaign:"Campaign scores",compare:"Compare results",rankings:"SNES rankings",history:"Version history"}[route];
  info(heading,{browse:"Find published emulator runs by game or ROM name.",campaign:"Published results from this campaign.",compare:"Match identical workloads across emulators or devices.",rankings:"Paired results for complete Carter Circuit suites on the same devices.",history:"Track emulator builds on the same installation, scene and timing worker."}[route]);filters();
  let rows=[],cursor=null;
  async function more(){
    const p=new URLSearchParams({q:q.value});if(route==="campaign")p.set("campaign",location.pathname.split("/")[2]);if(cursor)p.set("after",cursor);
    if(demo){ rows=demoRows().filter(r=>r.game.toLowerCase().includes(q.value.toLowerCase()));cursor=null;return; }
    const page=await get("/api/runs?"+p);rows.push(...page.rows);cursor=page.next;
  }
  await more();
  // Comparisons need the entire filtered cohort. The browser's score table pages on demand.
  if(["compare","rankings","history"].includes(route))while(cursor)await more();
  function render(){
    out.replaceChildren();const filtered=rows.filter(r=>checked().includes(r.emulator));
    if(route==="compare"){
      const groups=comparison(filtered,mode.value);if(!groups.length)empty("No matched pair for these filters yet.");
      for(const g of groups){out.append(make("h2",g[0].game),list(g));}
    }else if(route==="rankings"){
      const builds=[...new Set(filtered.filter(r=>!r.outcome && r.profile.startsWith("snes-circuit-")).map(build))].sort();
      if(builds.length<2){empty("Rankings need two builds with matched SNES scenes. No eligible pair yet.");return;}
      const a=make("select"),b=make("select");for(const v of builds){selectOption(a,v,v);selectOption(b,v,v);}b.selectedIndex=1;
      const l=make("label","Baseline"),m=make("label","Compare with");l.append(a);m.append(b);const panel=make("div",null,"tools"),result=make("div");panel.append(l,m);out.append(panel,result);
      function compare(){result.replaceChildren();if(a.value===b.value)return;const r=ranking(filtered,a.value,b.value);result.append(make("p",r.completed+" complete paired device/protocol groups out of "+r.eligible+" observed · "+r.failed+" reported failed attempts for the selected builds."));result.append(make("p",r.n?Math.round(100*r.ratio)+"% of baseline · "+r.n+" matched installations"+(r.interval?" · 95% interval "+r.interval.map(x=>Math.round(100*x)+"%").join(" to "):" · interval requires five installations"):"No complete matched suites."));if(r.matched.length){
          const bars=make("ul",null,"bars");for(const [name,ratio] of [[a.value,1],[b.value,r.ratio]]){const li=make("li",name+" · "+Math.round(ratio*100)+"%");const bar=make("meter");bar.min=0;bar.max=Math.max(1,r.ratio)*1.1;bar.value=ratio;bar.setAttribute("aria-label",name);li.append(bar);bars.append(li);}result.append(bars,list(r.matched));
        }}a.onchange=b.onchange=compare;compare();
    }else if(route==="history"){
      const cohorts=[...group(filtered.filter(r=>r.device_id && !r.outcome),r=>[device(r),workload(r),r.worker_sha256,r.emulator].join("|")).values()].filter(g=>group(g,build).size>1);
      if(!cohorts.length)empty("Version history needs two builds on the same device and scene.");
      for(const g of cohorts){out.append(make("h2",g[0].game+" · "+g[0].emulator));const versions=[...group(g.sort((a,b)=>a.received-b.received),build)];let prev=null;
        out.append(table(["Build","First submitted (UTC)","Median FPS","Change","Samples"],versions.map(([ver,rs])=>{const fps=median(rs.map(r=>r.average_fps));const change=prev?Math.round(100*(fps/prev-1))+"%":"—";prev=fps;return [link(ver,"/run/"+rs[0].run_id),new Date(rs[0].received*1000).toISOString().slice(0,10),String(Math.round(fps)),change,String(rs.length)];})));}
    }else{
      if(filtered.length)out.append(list(filtered));else empty("No published scores match this search.");
      if(cursor){const next=make("button","Load more scores");next.onclick=async()=>{next.disabled=true;try{await more();render();}catch(e){status.textContent=e.message;next.disabled=false;}};out.append(next);}
    }
  }
  for(const c of checks)c.onchange=render;mode.onchange=render;render();
}
(async()=>{try{for(const a of document.querySelectorAll("nav a"))if(a.pathname===location.pathname)a.setAttribute("aria-current","page");if(route==="method")method();else if(route==="run")await score();else await browse();status.textContent="";}catch(e){status.textContent=e.message;}})();
