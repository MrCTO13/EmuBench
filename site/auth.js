const utf8=new TextEncoder();
const hex=b=>Array.from(new Uint8Array(b),x=>x.toString(16).padStart(2,"0")).join("");
const bytes=s=>Uint8Array.from(s.match(/../g),x=>parseInt(x,16));
const sha=async s=>hex(await crypto.subtle.digest("SHA-256",s));
async function checkSignature(key,message,signature) {
  if (!plain(key,64,SHA) || !plain(signature,128,/^[0-9a-f]{128}$/)) return false;
  const publicKey=await crypto.subtle.importKey("raw",bytes(key),"Ed25519",false,["verify"]);
  return crypto.subtle.verify("Ed25519",publicKey,bytes(signature),utf8.encode(message));
}
async function limit(db,scope,seconds,maximum) {
  const now=Math.floor(Date.now()/1000/seconds);
  const row=await db.prepare("INSERT INTO limits(scope,window,used) VALUES(?,?,1) ON CONFLICT(scope) DO UPDATE SET used=CASE WHEN window=excluded.window THEN used+1 ELSE 1 END,window=excluded.window RETURNING used").bind(scope,now).first();
  return row.used<=maximum;
}
async function permitAddress(req,db,route,max) {
  const addr=req.headers.get("CF-Connecting-IP") || "local";
  const scope=await sha(utf8.encode(route+"\n"+addr));
  return limit(db,scope,60,max);
}
async function enroll(req,db) {
  if (!await permitAddress(req,db,"enroll",12))return json({error:"Enrollment rate exceeded"},429);
  try {
    const e=await payload(req);
    if (!fields(e,["key","token_hash","signature"]) || !plain(e.token_hash,64,SHA) ||
        !await checkSignature(e.key,"EmuBench enroll v1\n"+e.token_hash,e.signature))return json({error:"Invalid enrollment"},401);
    await db.prepare("INSERT OR IGNORE INTO installs(key,token_hash) VALUES(?,?)").bind(e.key,e.token_hash).run();
    const row=await db.prepare("SELECT token_hash FROM installs WHERE key=?").bind(e.key).first();
    return row.token_hash===e.token_hash?json({enrolled:true}):json({error:"Install already enrolled"},409);
  } catch {return json({error:"Invalid enrollment"},400);}
}
async function authorize(req,db) {
  if (!await permitAddress(req,db,"uploads",600))return json({error:"Address rate exceeded"},429);
  const key=req.headers.get("X-EmuBench-Key"),auth=req.headers.get("Authorization")||"";
  if (!plain(key,64,SHA) || !/^Bearer [0-9a-f]{64}$/.test(auth))return json({error:"Install credential required"},401);
  const token=await sha(utf8.encode(auth.slice(7)));
  if (!await db.prepare("SELECT 1 FROM installs WHERE key=? AND token_hash=?").bind(key,token).first())return json({error:"Unknown credential"},401);
  if (!await limit(db,"key/"+key,60,180))return json({error:"Install rate exceeded"},429);
  return key;
}
async function signedRun(req,key) {
  const e=await payload(req);
  requireValue(fields(e,["record","game","seal","signature"]) && typeof e.record==="string");
  requireValue(await checkSignature(key,"EmuBench run v1\n"+e.record,e.seal));
  requireValue(await checkSignature(key,"EmuBench submission v1\n"+e.seal+"\n"+e.game,e.signature));
  const signed=JSON.parse(e.record);
  requireValue(!Object.hasOwn(signed,"game"));
  const r=validate({...signed,game:e.game});
  const d=(await sha(bytes(key))).slice(0,32);
  requireValue(r.device_id===d.match(/^(.{8})(.{4})(.{4})(.{4})(.{12})$/).slice(1).join("-"));
  // Generous screening ceilings. The signed CPU class is still self-reported.
  const constrained=/cortex-a(?:35|53|55)|intel.*atom/i.test(r.cpu);
  const ceiling=constrained?30000:200000;
  if(!r.outcome)requireValue(r.average_fps<=ceiling && r.high_1pct_fps<=4*ceiling);
  return {...r,proof:{key,record:e.record,seal:e.seal,signature:e.signature}};
}
