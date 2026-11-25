"""A loopback desktop launcher for the same CLI used in unattended campaigns."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import html
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import uuid
import webbrowser

from . import catalog, engines, scores


def invocation():
    return [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, "-m", "emubench"]


def job(body):
    emulator, mode = body["emulator"], body["mode"]
    if emulator not in scores.ADAPTERS or mode not in ("suite","folder"):
        raise ValueError("Unknown workload or emulator")
    source = []
    if body.get("core"):
        path = Path(body["core"]).expanduser().resolve(strict=True)
        if not path.is_file():
            raise ValueError("Choose a core library file")
        source = ["--core",str(path)]
    elif emulator == "cartssnes":
        raise ValueError("Choose your CartsSNES core library")
    elif emulator == "mgba" and catalog.host_target() == "windows-arm64":
        source = ["--version",engines.REFERENCE]
    if mode == "suite":
        return [["suite","--emulator",emulator,*source]]
    directory = Path(body["folder"]).expanduser().resolve(strict=True)
    if not body["folder"].strip() or not directory.is_dir():
        raise ValueError("Choose a ROM folder")
    queue = engines.home()/"campaigns"/(str(uuid.uuid4())+".sqlite")
    policy = [] if sys.platform == "darwin" and not body.get("reserved") else ["--dedicated"]
    if sys.platform != "darwin" and not body.get("reserved"):
        raise ValueError("Reserve this computer for the campaign, or supply an idle check in the CLI")
    return [["campaign","create",str(queue),"--rom-dir",str(directory),"--emulator",emulator,*source,*policy],
            ["campaign","resume",str(queue)]]


def launch(open_browser=True):
    secret = secrets.token_urlsafe(32)
    lock = threading.Lock()
    state = {"active":False,"lines":[]}
    def run(commands):
        try:
            for args in commands:
                with subprocess.Popen(invocation()+args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                      text=True, errors="replace", env=os.environ | {"PYTHONUNBUFFERED":"1"}) as proc:
                    for line in proc.stdout:
                        with lock:
                            state["lines"]=(state["lines"]+[line.rstrip()])[-100:]
                    if proc.wait():
                        raise ValueError("Command exited with status "+str(proc.returncode))
        except (OSError, ValueError) as exc:
            with lock:
                state["lines"].append(str(exc))
        finally:
            with lock:
                state["active"]=False
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):
            pass
        def send_body(self,code,data,kind):
            self.send_response(code)
            for k,v in {"Content-Type":kind,"Content-Length":str(len(data)),"Cache-Control":"no-store",
                        "Referrer-Policy":"no-referrer","X-Frame-Options":"DENY","X-Content-Type-Options":"nosniff"}.items():
                self.send_header(k,v)
            self.end_headers()
            self.wfile.write(data)
        def valid(self):
            return self.headers.get("Host")==authority and self.path in ("/"+secret, "/"+secret+"/state")
        def do_GET(self):
            if not self.valid():
                return self.send_error(404)
            if self.path.endswith("/state"):
                with lock:
                    body=json.dumps(state).encode()
                return self.send_body(200,body,"application/json")
            return self.send_body(200,page,"text/html; charset=utf-8")
        def do_POST(self):
            if (not self.valid() or self.path.endswith("/state") or self.headers.get("Origin")!="http://"+authority
                    or self.headers.get_content_type()!="application/json"):
                return self.send_error(403)
            try:
                length=int(self.headers.get("Content-Length","0"))
                if not 0 < length < 8192:
                    raise ValueError("Invalid request size")
                commands=job(json.loads(self.rfile.read(length)))
                with lock:
                    if state["active"]:
                        return self.send_body(409,b"Another job is running","text/plain")
                    state.update(active=True,lines=[])
                threading.Thread(target=run,args=(commands,),daemon=True).start()
                self.send_body(202,b"Started","text/plain")
            except (ValueError,TypeError,KeyError,OSError) as exc:
                self.send_body(400,str(exc).encode(),"text/plain")
    with ThreadingHTTPServer(("127.0.0.1",0),Handler) as server:
        authority=f"127.0.0.1:{server.server_port}"
        page=Path(__file__).with_name("desktop.html").read_text().replace("__SYSTEM__",html.escape(catalog.host_target())).encode()
        url=f"http://{authority}/{secret}"
        print("Emu Bench desktop:",url,flush=True)
        if open_browser:
            webbrowser.open(url)
        server.serve_forever()
