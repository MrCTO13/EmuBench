// LAB contains the frozen samples and maintainer-reviewed receipts from the release.
function studyPanel() {
  out.append(make("h2","Verified lab studies"));
  const select=make("select");
  for(const s of LAB.studies)selectOption(select,s.id,s.console==="snes"?"Super NES":"Game Boy Advance");
  const label=make("label","Console ");label.append(select);out.append(label);
  const panel=make("div");out.append(panel);
  function render(){
    const s=LAB.studies.find(x=>x.id===select.value);
    const all=s.groups.flatMap(g=>g.games),N=s.groups.reduce((n,g)=>n+g.population,0);
    panel.replaceChildren(make("p",all.length+" USA editions sampled from "+N+" eligible catalog entries. Six editions per cartridge-size quartile. Each run measures "+s.frames+" uncapped boot frames after "+s.warmup+" warm-up frames, without controller input."));
    const receipts=LAB.receipts.filter(r=>r.study===s.id);
    if(!receipts.length)panel.append(make("p","Awaiting the first reviewed, complete lab campaign. No verified FPS yet.","empty"));
    for(const r of receipts){
      panel.append(make("h3",r.host.cpu+" · "+r.host.os+" "+r.host.arch),make("p",r.gate+" · "+r.campaign));
      const ranking=[];
      for(const [peer,sha] of Object.entries(r.builds)){
        const rows=r.rows.filter(row=>row.emulator===peer);
        const required=s.console==="snes"?"5/5 checks passed":"3/3 checks passed";
        if(!rows.every(row=>row.speed_x>0 && row.accuracy_label===required))continue;
        let log=0;
        for(const group of s.groups){
          const weight=group.population/N/group.games.length;
          for(const game of group.games)log+=weight*Math.log(rows.find(row=>row.edition===game.edition).speed_x);
        }
        ranking.push([peer+" "+rows[0].version,Math.exp(log).toFixed(2),required,sha]);
      }
      panel.append(table(["Build","Weighted console speed (×)","Accuracy","Build SHA-256"],ranking.sort((a,b)=>b[1]-a[1])));
      panel.append(table(["Edition","Emulator","Accuracy","Speed","Average FPS","1% low","1% high"],r.rows.map(row=>
        [all.find(g=>g.edition===row.edition).title,row.emulator,row.accuracy_label||'Untested',speedLabel(row),row.average_fps,row.low_1pct_fps,row.high_1pct_fps])));
    }
    const details=make("details");details.append(make("summary","See the 24 selected games"),table(["Cartridge-size quartile","Edition"],s.groups.flatMap((g,i)=>g.games.map(game=>[i+1,game.title]))));panel.append(details);
    panel.append(link("Sample and review protocol","https://github.com/MrCTO13/EmuBench/blob/d9289f7c1625a920b7dad006d5b06fd3769ed036/STUDIES.md"));
  }
  select.onchange=render;render();
}
