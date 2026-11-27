// Consoles and emulators available for local bring-your-own runs. No commercial titles are listed.
const libraryPlan = [
 ["NES","Nestopia UE, FCEUmm"],
 ["Super NES","Snes9x, bsnes, CartsSNES (closed, not ranked)"],
 ["Game Boy","SameBoy, Gambatte"],
 ["Game Boy Color","SameBoy, Gambatte"],
 ["Game Boy Advance","mGBA, gpSP"],
 ["Master System","Gearsystem, Genesis Plus GX, PicoDrive"],
 ["Game Gear","Gearsystem, Genesis Plus GX, PicoDrive"],
 ["Genesis / Mega Drive","Genesis Plus GX, PicoDrive"],
 ["Atari 2600","Stella"],
 ["PC Engine","Beetle PCE Fast, Beetle SuperGrafx"],
 ["SuperGrafx","Beetle SuperGrafx"],
 ["PC Engine CD","Beetle PCE Fast, Beetle SuperGrafx"],
 ["PlayStation","DuckStation, PCSX-ReARMed"],
 ["Neo Geo","FinalBurn Neo, MAME"]
];
function libraryPage(){
  info("Game library","Get the Carter games, or pick a console to see which emulators can run your own ROMs.");
  const filter=make("select"),l=make("label","Console");selectOption(filter,"all","All consoles");
  for(const [name] of libraryPlan)selectOption(filter,name,name);selectOption(filter,"Nintendo 64","Nintendo 64");l.append(filter);controls.append(l);
  function display(){
    out.replaceChildren();
    const systems={atari2600:"Atari 2600",gb:"Game Boy",gbc:"Game Boy Color",gba:"Game Boy Advance",genesis:"Genesis / Mega Drive",n64:"Nintendo 64",nes:"NES",sms:"Master System",snes:"Super NES"};
    const editions=CARTER_GAMES.filter(g=>filter.value==="all"||systems[g.console]===filter.value);
    if(editions.length){
      const h=make("h2","Carter collection");h.id="carter";
      out.append(h,make("p","Cartervania and Super Carter Bros. 3 include recorded gameplay. Other timed games start at boot. If the title screen stays still, the run may finish without a score."),link("Download the 12-game pack","https://github.com/MrCTO13/EmuBench/releases/download/carter-games-v1/EmuBench-Carter-Games-v1.zip"),
        table(["Game","Console","Edition","Benchmark mode"],editions.map(g=>[
          g.console==="n64"?g.title:link(g.title,"/?q="+encodeURIComponent(g.title)),systems[g.console],g.edition,
          g.console==="n64"?"Game only": ["Cartervania","Super Carter Bros. 3"].includes(g.title)?"Gameplay replay":"Local ROM"]),"Carter game editions"));
    }
    if(filter.value!=="Nintendo 64"){out.append(make("h2","Bring your own games"),make("p","Your own cartridge dumps can be timed locally with these emulators. Personal ROM results stay on your device and never count toward official scores."));
    out.append(table(["Console","Emulators"],libraryPlan.filter(r=>filter.value==="all"||r[0]===filter.value).map(([name,peers])=>[name,name==="PlayStation"?peers+" · DuckStation reports one average":peers]),"Bring-your-own emulators"));}
  }filter.onchange=display;display();
}
