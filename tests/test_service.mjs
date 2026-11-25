// Use actual SQLite SQL and a local D1-compatible binding; CI never publishes to the live service.
import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { readFileSync, readdirSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import { randomUUID } from 'node:crypto';
import vm from 'node:vm';
const worker=(await import(pathToFileURL(process.argv[2]))).default;
const sql=new DatabaseSync(':memory:');
for(const name of readdirSync('site/drizzle').filter(n=>n.endsWith('.sql')).sort())sql.exec(readFileSync('site/drizzle/'+name,'utf8'));
const db={prepare(query){const op=sql.prepare(query);return {bind(...args){return {all:()=>({results:op.all(...args)}),first:()=>op.get(...args),run:()=>({meta:op.run(...args)})}}}}};
const raw=(path,method='GET',value,headers={})=>worker.fetch(new Request('https://example.test'+path,{method,headers:{'content-type':'application/json',...headers},body:method==='GET'?undefined:JSON.stringify(value)}),{DB:db});
const keys=await crypto.subtle.generateKey("Ed25519",true,["sign","verify"]);
const toHex=b=>Buffer.from(b).toString("hex");
const sign=async s=>toHex(await crypto.subtle.sign("Ed25519",keys.privateKey,Buffer.from(s)));
const publicBytes=await crypto.subtle.exportKey("raw",keys.publicKey);
const pub=toHex(publicBytes), bearer=toHex(crypto.getRandomValues(new Uint8Array(32)));
const hash=async b=>toHex(await crypto.subtle.digest("SHA-256",b));
const digest=await hash(Buffer.from(bearer));
assert.equal((await raw("/api/installs","POST",{key:pub,token_hash:digest,signature:await sign("EmuBench enroll v1\n"+digest)})).status,200);
const headers={"Authorization":"Bearer "+bearer,"X-EmuBench-Key":pub};
async function envelope(value){
  const {game,...rest}=value, record=JSON.stringify(rest),seal=await sign("EmuBench run v1\n"+record);
  return {game,record,seal,signature:await sign("EmuBench submission v1\n"+seal+"\n"+game)};
}
const fetch=async(path,method='GET',value)=>method==="POST"?raw(path,method,await envelope(value),headers):raw(path);
const id=randomUUID(),device=(await hash(publicBytes)).slice(0,32).match(/^(.{8})(.{4})(.{4})(.{4})(.{12})$/).slice(1).join("-"),campaign=randomUUID(),token=randomUUID();
const score={run_id:id,device_id:device,campaign_id:campaign,comparison_id:token,game:'Test public title',profile:'snes-boot-no-input-v1',emulator:'Snes9x',version:'1.63',source_commit:null,
 core_sha256:'a'.repeat(64),worker_sha256:'b'.repeat(64),os:'Windows',arch:'ARM64',cpu:'Example CPU',rendered_frames:100,warmup_frames:120,average_fps:100,low_1pct_fps:100,high_1pct_fps:100,
 repeatability:{elapsed_ns:[1e9,1e9,1e9],selected:0,relative_spread:0,accepted:true},idle:{cpu_percent:0,state:'idle'},frame_check:{method:'full-fnv64-17',samples:6,changes:5,signature:'0000000001234567'},mode:'libretro',video_mode:{region:'NTSC',source:'emulator-av',refresh_hz:60.0988},speed_x:100/60.0988,
 timing:[{start_ms:0,end_ms:1000,avg_fps:100,worst_fps:100,worst_ms:10,worst_frame:1,worst_at_ms:10}]};
assert.equal((await fetch('/api/runs','POST',{...score,repeatability:{...score.repeatability,elapsed_ns:[1e8,1e9,2e9]}})).status,400);
assert.equal((await fetch('/api/runs','POST',score)).status,201);
assert.equal((await fetch('/api/runs','POST',score)).status,200);
assert.equal((await fetch('/api/runs','POST',{...score,game:'Different'})).status,409);
assert.equal((await fetch('/api/runs','POST',{...score,rom_sha256:'private'})).status,400);
assert.equal((await fetch('/api/runs','POST',{...score,profile:'snes-circuit-hard-v1'})).status,400);
assert.equal((await fetch('/api/runs','POST',{...score,timing:[{...score.timing[0],path:'private'}]})).status,400);
assert.equal((await (await fetch('/api/run/'+id)).json()).run_id,id);
for(let i=0;i<103;i++)assert.equal((await fetch('/api/runs','POST',{...score,run_id:randomUUID()})).status,201);
const first=await (await fetch('/api/runs?campaign='+campaign)).json();
assert.equal(first.rows.length,100);assert.ok(first.next);assert.ok(!first.rows[0].timing);
const page2=await (await fetch('/api/runs?after='+first.next)).json();
assert.equal(page2.rows.length,4);assert.equal(new Set([...first.rows,...page2.rows].map(r=>r.run_id)).size,104);
assert.equal((await (await fetch('/api/runs?q=missing')).json()).rows.length,0);
const ctx=vm.createContext({});
vm.runInContext(readFileSync('site/analysis.js','utf8')+readFileSync('site/demo.js','utf8'),ctx);
const res=vm.runInContext('(()=>{const rows=demoRows();const builds=[...new Set(rows.filter(r=>r.emulator==="CartsSNES").map(build))];const a=ranking(rows,...builds);const f=rows.find(r=>r.profile.includes("-circuit-")&&r.emulator==="CartsSNES");const b=ranking([...rows,{...f,outcome:"failed"}],...builds);return [a.n,a.interval,b.n,b.failed,comparison(rows,"devices").length,comparison(rows,"emulators").length]})()',ctx);
assert.deepEqual(Array.from(res).slice(0,4),[2,null,1,1]);assert.ok(res[4]>0 && res[5]>0);
console.log('Score creation, duplicate recovery, validation, pagination, failure coverage and two-way matching passed.');
assert.equal((await fetch('/api/runs','POST',{...score,verified:true})).status,400);
assert.equal((await fetch('/api/runs','POST',{...score,emulator:"Nestopia UE",profile:"nes-boot-no-input-v1",run_id:randomUUID()})).status,201);
assert.equal((await fetch('/api/runs','POST',{...score,emulator:"Nestopia UE",profile:"gba-boot-no-input-v1",run_id:randomUUID()})).status,400);
const studies=await (await fetch('/api/studies')).json();
assert.equal(studies.studies.length,2);
assert.equal(studies.studies[0].groups.flatMap(g=>g.games).length,24);

assert.equal((await raw("/api/runs","POST",score)).status,401);
const changed=await envelope(score);changed.record=changed.record.replace("Snes9x","bsnes");
assert.equal((await raw("/api/runs","POST",changed,headers)).status,400);
let status=0;for(let i=0;i<181 && status!==429;i++)status=(await fetch("/api/runs","POST",score)).status;
assert.equal(status,429);
