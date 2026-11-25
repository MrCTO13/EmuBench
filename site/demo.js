// Deterministic fictional fixtures for the optional Example data view only.
function demoRows() {
  const rows=[];
  function add(game, profile, emulator, version, machine, avg, bytes,edition) {
    const id=String(rows.length+1).padStart(12,"0"),n=profile.includes("circuit")?600:1800;
    const elapsed=n*1000/avg;
    rows.push({run_id:"00000000-0000-4000-8000-"+id,device_id:"demo-"+machine,comparison_id:edition||profile,edition,
      game,profile,emulator,version,cpu:machine===1?"Example Apple silicon":"Example x86-64 PC",os:machine===1?"Darwin":"Windows",
      arch:machine===1?"arm64":"AMD64",core_sha256:bytes.repeat(64),worker_sha256:String(machine).repeat(64),source_commit:bytes.repeat(40),
      video_mode:{region:profile.startsWith('gba')?'handheld':'NTSC',refresh_hz:profile.startsWith('gba')?4194304/70224:60.0988},speed_x:avg/(profile.startsWith('gba')?4194304/70224:60.0988),average_fps:avg,low_1pct_fps:Math.round(avg*.72),high_1pct_fps:Math.round(avg*1.18),rendered_frames:n,warmup_frames:120,
      received:1740787200+rows.length*1800,timing:Array.from({length:16},(_,i)=>({start_ms:elapsed*i/16,end_ms:elapsed*(i+1)/16,
        avg_fps:Math.round(avg*(.98+.075*Math.sin(i)-.20*(i===8))),worst_fps:Math.round(avg*(i===8?.4:.78)),
        worst_ms:1000/(avg*.60),worst_frame:1+i*Math.floor(n/16),worst_at_ms:elapsed*(i+.5)/16}))});
  }
  for(const machine of [1,2])for(const [emu,ver,rate,key] of [["Snes9x","example A",610,"a"],["bsnes","example B",480,"b"],["CartsSNES","example C",570,"c"],["CartsSNES","example D",592,"d"]]){
    ["easy","normal","hard"].forEach((level,i)=>add("Carter Circuit (SNES "+level+")","snes-circuit-"+level+"-v1",emu,ver,machine,rate-i*54+machine*28,key));
    for(const [i,game] of ["Super Mario World (USA)","Star Fox (USA)","Super Mario RPG (USA)"].entries())
      add(game,"snes-boot-no-input-v1",emu,ver,machine,rate-i*48+machine*12,key,"demo-edition-"+i);
  }
  add("F-Zero Maximum Velocity (USA)","gba-boot-no-input-v1","mGBA","example A",1,680,"e","demo-gba");
  return rows.reverse();
}
