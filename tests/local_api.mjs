// Serve the exact production worker over loopback with its actual SQL migrations.
import {DatabaseSync} from "node:sqlite";
import {createServer} from "node:http";
import {readFileSync,readdirSync} from "node:fs";
import {pathToFileURL} from "node:url";
const app=(await import(pathToFileURL(process.argv[2]))).default;
const sql=new DatabaseSync(":memory:");
for(const file of readdirSync("site/drizzle").filter(f=>f.endsWith(".sql")).sort())
  sql.exec(readFileSync("site/drizzle/"+file,"utf8"));
const DB={prepare(query){const stmt=sql.prepare(query);return {bind(...args){return {
  first:()=>stmt.get(...args),all:()=>({results:stmt.all(...args)}),run:()=>({meta:stmt.run(...args)})};}};}};
// Optional fixture rows for browser QA: synthetic Carter Circuit runs, never real scores.
if(process.argv.includes("--seed")){
  const ac={thermal_state:"nominal",temperature_c:null,throttled:false,throttle_count:null,power_source:"ac",low_power:false,cpu_mhz:null};
  let n=0;
  for(const dev of [1,2])for(const [emu,ver,sha,rate] of [["Snes9x","1.63","a",3600],["bsnes","115","b",700]])for(const [i,level] of ["easy","normal","hard"].entries()){
    const id="00000000-0000-4000-8000-"+String(++n).padStart(12,"0"),fps=rate-i*50+dev*40,frames=600*Math.ceil(10*fps/600),ms=1000*frames/fps;
    const r={run_id:id,device_id:"00000000-0000-4000-9000-00000000000"+dev,game:"Carter Circuit (SNES "+level+")",profile:"snes-circuit-"+level+"-v2",emulator:emu,version:ver,
      source_commit:null,core_sha256:sha.repeat(64),worker_sha256:"c".repeat(64),os:"Linux",arch:"x86_64",cpu:"Fixture CPU "+dev,standing:"verified",
      hardware:{device_class:"Fixture CPU "+dev+" / 4c",model:null,ram_bytes:8*2**30,os_build:"1",physical_cores:4,core_types:{},gpu:[]},
      conditions:[1,2,3].map(()=>({before:ac,after:ac})),idle:{state:"idle",cpu_percent:3},repeatability:{elapsed_ns:[1,1,1].map(()=>Math.round(ms*1e6)),frames:[frames,frames,frames],selected:0,relative_spread:0.01,max_spread:0.03,min_window_ns:1e10,accepted:true,rejected_for:[]},
      window:{loops:frames/600,timed_ns:Math.round(ms*1e6),minimum_ns:1e10,loops_identical:true},mode:"libretro",video_mode:{region:"NTSC",refresh_hz:60.09881389744051,source:"snes-progressive"},
      speed_x:fps/60.09881389744051,average_fps:fps,low_1pct_fps:Math.round(fps*.9),high_1pct_fps:Math.round(fps*1.05),min_fps:Math.round(fps*.5),rendered_frames:frames,warmup_frames:120,
      accuracy:{suite:"cpu-memory-v1",core_sha256:sha.repeat(64),worker_sha256:"c".repeat(64),checks:{"65C816 basic":"pass",SPC700:"pass"}},
      chips:{"SA-1 multiply":"pass","Super FX immediate":"pass","DSP-1 fixed-point multiply":"pass"},
      timing:Array.from({length:16},(_,k)=>({start_ms:ms*k/16,end_ms:ms*(k+1)/16,avg_fps:fps,worst_fps:Math.round(fps*.6),worst_ms:1000/(fps*.6),worst_frame:1+k*Math.floor(frames/16),worst_at_ms:ms*(k+.5)/16}))};
    sql.prepare("INSERT INTO runs(id,received,game,profile,emulator,campaign,device,payload) VALUES(?,?,?,?,?,?,?,?)").run(id,1767225600+n*60,r.game,r.profile,emu,null,r.device_id,JSON.stringify(r));
  }
}
const server=createServer(async(req,res)=>{
  try{
    const chunks=[];for await(const chunk of req)chunks.push(chunk);
    const request=new Request("http://127.0.0.1:"+server.address().port+req.url,{method:req.method,headers:req.headers,
      body:chunks.length?Buffer.concat(chunks):undefined});
    const response=await app.fetch(request,{DB});
    res.writeHead(response.status,Object.fromEntries(response.headers));res.end(Buffer.from(await response.arrayBuffer()));
  }catch{res.writeHead(500);res.end();}
});
server.listen(0,"127.0.0.1",()=>console.log("http://127.0.0.1:"+server.address().port));
