// Public title examples guide BYO coverage. They are distinct from the official synthetic score.
const libraryPlan = [
 ["NES","Nestopia UE, FCEUmm","Super Mario Bros.; Super Mario Bros. 3; Kirby’s Adventure; Castlevania III"],
 ["Super NES","CartsSNES, Snes9x, bsnes","Super Mario World; Super Mario Kart; Star Fox; Super Mario RPG; Super Mario World 2: Yoshi’s Island; Street Fighter Alpha 2"],
 ["Game Boy","SameBoy, Gambatte","Tetris; Super Mario Land; The Legend of Zelda: Link’s Awakening"],
 ["Game Boy Color","SameBoy, Gambatte","Pokémon Crystal; The Legend of Zelda: Oracle of Ages; Shantae"],
 ["Game Boy Advance","mGBA, gpSP","F-Zero: Maximum Velocity; Metroid Fusion; Golden Sun; Mario Kart: Super Circuit"],
 ["Master System","Gearsystem, Genesis Plus GX, PicoDrive","Alex Kidd in Miracle World; Phantasy Star; Sonic the Hedgehog"],
 ["Game Gear","Gearsystem, Genesis Plus GX, PicoDrive","Columns; Shinobi; Sonic the Hedgehog: Triple Trouble"],
 ["Genesis / Mega Drive","Genesis Plus GX, PicoDrive","Sonic the Hedgehog 2; Gunstar Heroes; Virtua Racing"],
 ["Atari 2600","Stella","Adventure; Pitfall!; River Raid"],
 ["PC Engine","Beetle PCE Fast, Beetle SuperGrafx","Bonk’s Adventure; Blazing Lazers; R-Type"],
 ["SuperGrafx","Beetle SuperGrafx","Aldynes; Ghouls ’n Ghosts; 1941: Counter Attack"],
 ["PC Engine CD","Beetle PCE Fast, Beetle SuperGrafx","Castlevania: Rondo of Blood; Ys Book I & II; Gate of Thunder"],
 ["PlayStation","DuckStation, PCSX-ReARMed","Ridge Racer; Tekken 3; Gran Turismo 2"],
 ["Neo Geo","FinalBurn Neo, MAME","Metal Slug; The King of Fighters ’98; Garou: Mark of the Wolves"]
];
function libraryPage(){
  info("Game coverage","Download the original Carter games or look up a console’s bring-your-own titles and compatible emulators.");
  const filter=make("select"),l=make("label","Console");selectOption(filter,"all","All consoles");
  for(const [name] of libraryPlan)selectOption(filter,name,name);selectOption(filter,"Nintendo 64","Nintendo 64");l.append(filter);controls.append(l);
  function display(){
    out.replaceChildren();
    const systems={atari2600:"Atari 2600",gb:"Game Boy",gbc:"Game Boy Color",gba:"Game Boy Advance",genesis:"Genesis / Mega Drive",n64:"Nintendo 64",nes:"NES",sms:"Master System",snes:"Super NES"};
    const editions=CARTER_GAMES.filter(g=>filter.value==="all"||systems[g.console]===filter.value);
    if(editions.length){
      const h=make("h2","Carter collection");h.id="carter";
      out.append(h,make("p","Two editions include recorded gameplay. Local ROM runs begin at boot. A stationary title screen can leave a run unscored."),link("Download the 12-game pack","https://github.com/MrCTO13/EmuBench/releases/download/carter-games-v1/EmuBench-Carter-Games-v1.zip"),
        table(["Game","Console","Edition","Benchmark mode"],editions.map(g=>[
          g.console==="n64"?g.title:link(g.title,"/?q="+encodeURIComponent(g.title)),systems[g.console],g.edition,
          g.console==="n64"?"Game only": ["Cartervania","Super Carter Bros. 3"].includes(g.title)?"Gameplay replay":"Local ROM"]),"Carter game editions"));
    }
    if(filter.value!=="Nintendo 64")out.append(make("h2","Bring your own games"));
    for(const [name,peers,names] of libraryPlan.filter(r=>filter.value==="all"||r[0]===filter.value)){
    out.append(make("h3",name),make("p",name==="PlayStation"?"Frame-timed scores · PCSX-ReARMed. DuckStation offers a separate regression-runner average.":"Timing adapters · "+peers));
    const ul=make("ul");for(const game of names.split("; ")){const li=make("li");li.append(link(game,"/?q="+encodeURIComponent(game)));ul.append(li);}out.append(ul);
  }}filter.onchange=display;display();
}
