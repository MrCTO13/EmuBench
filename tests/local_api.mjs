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
