// Public title examples guide BYO coverage. They are distinct from the official synthetic score.
const libraryPlan = [
 ["NES","Nestopia UE, FCEUmm","Super Mario Bros.; Super Mario Bros. 3; Kirby’s Adventure; Castlevania III"],
 ["Super NES","CartsSNES, Snes9x, bsnes","Super Mario World; Super Mario Kart; Star Fox; Super Mario RPG; Super Mario World 2: Yoshi’s Island; Street Fighter Alpha 2"],
 ["Game Boy","SameBoy, Gambatte","Tetris; Super Mario Land; The Legend of Zelda: Link’s Awakening"],
 ["Game Boy Color","SameBoy, Gambatte","Pokémon Crystal; The Legend of Zelda: Oracle of Ages; Shantae"],
 ["Game Boy Advance","mGBA, gpSP","F-Zero: Maximum Velocity; Metroid Fusion; Golden Sun; Mario Kart: Super Circuit"],
 ["Master System","Gearsystem, Genesis Plus GX","Alex Kidd in Miracle World; Phantasy Star; Sonic the Hedgehog"],
 ["Game Gear","Gearsystem, Genesis Plus GX","Columns; Shinobi; Sonic the Hedgehog: Triple Trouble"],
 ["Genesis / Mega Drive","Genesis Plus GX, PicoDrive","Sonic the Hedgehog 2; Gunstar Heroes; Virtua Racing"],
 ["Atari 2600","Stella","Adventure; Pitfall!; River Raid"],
 ["PC Engine","Beetle PCE Fast","Bonk’s Adventure; Blazing Lazers; R-Type"],
 ["SuperGrafx","Beetle SuperGrafx","Aldynes; Ghouls ’n Ghosts; 1941: Counter Attack"],
 ["PC Engine CD","Beetle PCE Fast","Castlevania: Rondo of Blood; Ys Book I & II; Gate of Thunder"],
 ["PlayStation","DuckStation, PCSX-ReARMed","Ridge Racer; Tekken 3; Gran Turismo 2"],
 ["Neo Geo","FinalBurn Neo, MAME","Metal Slug; The King of Fighters ’98; Garou: Mark of the Wolves"]
];
function libraryPage(){
  info("Game coverage","The official suite uses source-built Carter Circuit cartridges. These real games are candidates for separate bring-your-own library runs.");
  const filter=make("select"),l=make("label","Console");selectOption(filter,"all","All consoles");
  for(const [name] of libraryPlan)selectOption(filter,name,name);l.append(filter);controls.append(l);
  function display(){out.replaceChildren();for(const [name,peers,names] of libraryPlan.filter(r=>filter.value==="all"||r[0]===filter.value)){
    out.append(make("h2",name),make("p",name==="Super NES"?"Timing adapters · CartsSNES, Snes9x and bsnes":name==="Game Boy Advance"?"Timing adapter · mGBA. gpSP is a download candidate.":"Planned timing coverage · "+peers));
    const ul=make("ul");for(const game of names.split("; "))ul.append(make("li",link(game,"/?q="+encodeURIComponent(game.split(" (")[0]))));out.append(ul);
  }}filter.onchange=display;display();
}
