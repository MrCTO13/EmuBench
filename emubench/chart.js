function drawTiming(host, bins) {
  host.replaceChildren();
  if (!bins?.length) return;
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", "0 0 720 220");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", "FPS across elapsed time. The blue line shows interval averages and the orange dots show individual frame lows.");
  svg.style.cssText = "display:block;width:100%;min-height:140px;background:#f2f6fc;border-radius:8px";
  function add(tag, attrs, label) {
    const el = document.createElementNS(ns, tag);
    for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, value);
    if (label) el.textContent = label;
    svg.append(el);
    return el;
  }
  const peak = Math.max(1, ...bins.map(b => b.avg_fps)) * 1.08;
  const end = bins[bins.length-1].end_ms;
  const x = ms => 62 + 638 * ms / end;
  const y = fps => 173 - 145 * fps / peak;
  const axis = {fill:"#385470", "font-size":13, "font-family":"system-ui"};
  for(let i=0; i<=3; i++) {
    const value = peak*i/3, height = y(value);
    add("line",{x1:62,x2:700,y1:height,y2:height,stroke:"#ccdaea"});
    add("text",{...axis,x:55,y:height+4,"text-anchor":"end"}, Math.round(value).toLocaleString());
  }
  add("text",{...axis,x:14,y:19},"FPS");
  add("text",{...axis,x:62,y:196},"0 s");
  add("text",{...axis,x:700,y:196,"text-anchor":"end"}, (end/1000).toFixed(3)+" s");
  add("text",{...axis,x:380,y:214,"text-anchor":"middle"},"Elapsed host time");
  const points = bins.map(b => x((b.start_ms+b.end_ms)/2)+","+y(b.avg_fps)).join(" ");
  add("polyline",{points,stroke:"#165bba","stroke-width":2.5,fill:"none"});
  for(const b of bins) {
    const dot = add("circle",{cx:x(b.worst_at_ms),cy:y(b.worst_fps),r:2.7,fill:"#ad4d0b"});
    const title=document.createElementNS(ns,"title");
    title.textContent="Frame "+b.worst_frame+" · "+b.worst_ms.toFixed(3)+" ms"; dot.append(title);
  }
  const cursor=add("line",{stroke:"#2c4561","stroke-dasharray":"3 3",y1:20,y2:173});
  const label=document.createElement("label"), slider=document.createElement("input"), note=document.createElement("p");
  label.textContent="Inspect interval ";
  slider.type="range";slider.min=0;slider.max=bins.length-1;slider.step=1;
  const worstIndex=bins.reduce((best,b,i)=>b.worst_ms>bins[best].worst_ms?i:best,0);
  slider.value=worstIndex;
  label.append(slider);
  label.style.cssText="display:flex;align-items:center;gap:12px;margin:10px 0 4px";
  slider.style.cssText="flex:1;accent-color:#215eb5";
  function select(index) {
    const b=bins[index];slider.value=index;
    cursor.setAttribute("x1",x(b.worst_at_ms));cursor.setAttribute("x2",x(b.worst_at_ms));
    note.textContent=(b.start_ms/1000).toFixed(3)+"–"+(b.end_ms/1000).toFixed(3)+" s · "+
      b.avg_fps.toFixed(1)+" average FPS · slowest frame #"+b.worst_frame+" took "+b.worst_ms.toFixed(3)+
      " ms ("+b.worst_fps.toFixed(1)+" FPS).";
  }
  slider.addEventListener("input",()=>select(Number(slider.value)));
  svg.addEventListener("pointerdown",event=>{
    const matrix=svg.getScreenCTM(); if(!matrix)return;
    const point=new DOMPoint(event.clientX,event.clientY).matrixTransform(matrix.inverse());
    const ms=Math.max(0,(point.x-62)*end/638);
    const i=bins.findIndex(b=>ms<=b.end_ms); select(i===-1?bins.length-1:i);
  });
  const legend=document.createElement("p");legend.textContent="Blue line · interval average     Orange dots · slowest frame in each interval";
  legend.style.cssText="font-size:.85rem;color:#405b76;margin:7px 0";
  host.append(svg,legend,label,note); select(worstIndex);
}
