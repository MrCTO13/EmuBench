"""Submit a real CLI receipt using the production Python client and a local worker."""
import json
from pathlib import Path
import subprocess
import sys
from urllib.request import urlopen
from emubench import scores, service

with subprocess.Popen(["node","--experimental-sqlite","tests/local_api.mjs",sys.argv[1]],stdout=subprocess.PIPE,text=True) as server:
    try:
        service.ORIGIN=server.stdout.readline().strip()
        assert service.ORIGIN.startswith("http://127.0.0.1:")
        verified=0
        for path in sys.argv[2:]:
            data=json.loads(Path(path).read_text())
            public=scores.public_fields(data,"EmuBench homebrew")
            if not data["repeatability"]["accepted"]:
                try:
                    service.publish(public)
                except ValueError as exc:
                    assert "acceptance gate" in str(exc), exc
                else:
                    raise AssertionError("Unstable timing was accepted")
                continue
            url=service.publish(public)
            assert service.publish(public)==url
            stored=json.load(urlopen(url.replace("/run/","/api/run/"),timeout=3))
            assert stored["speed_x"]==data["speed_x"] and stored["mode"]==data["mode"]
            assert "content_sha256" not in stored and "rom_sha256" not in stored and stored["proof"]["seal"]
            verified+=1
            print(stored["emulator"],stored["mode"],"signed receipt verified")
        assert verified, "No stable run was available to exercise a valid signed upload"
    finally:
        server.terminate()
