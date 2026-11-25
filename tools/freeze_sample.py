"""Rebuild the preregistered cartridge sample from pinned public No-Intro DATs."""
import hashlib
import json
from pathlib import Path
import re
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from emubench import identify

def sample(console, path):
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=identify.CATALOGS[console][1]:
        raise ValueError("Catalog does not match pinned revision")
    entries = {}
    for block in raw.decode().split("\ngame (")[1:]:
        name = re.search(r'^\s*name "([^"\n]+)"', block)
        image = re.findall(r'\brom \( name "([^"]+)" size (\d+) ', block)
        if not name or len(image)!=1 or not re.fullmatch(r'[^()]+ \(USA\)',name[1]):
            continue
        file,size = image[0]
        if Path(file).stem==name[1]:
            entries[name[1]]=int(size)
    ordered = sorted(entries,key=lambda title:(entries[title],title))
    groups = []
    for q in range(4):
        pool = ordered[len(ordered)*q//4:len(ordered)*(q+1)//4]
        seed = "emubench-us-boot-v1/"+console+"/"
        names = sorted(pool,key=lambda name:hashlib.sha256((seed+name).encode()).digest())[:6]
        groups.append({"population":len(pool),"min_bytes":entries[pool[0]],"max_bytes":entries[pool[-1]],
                       "games":[{"title":t,"edition":hashlib.sha256(("no-intro-v1/"+console+"/"+t).encode()).hexdigest()} for t in names]})
    return {"id":console+"-us-boot-v1","console":console,"catalog_commit":identify.COMMIT,"warmup":120,"frames":1800,"groups":groups}

if __name__=="__main__":
    print(json.dumps([sample(k,Path(p)) for k,p in zip(("snes","gba"),sys.argv[1:],strict=True)],ensure_ascii=False,indent=2))
