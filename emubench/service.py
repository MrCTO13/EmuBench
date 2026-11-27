"""Authenticated, resumable publication of sealed public summaries."""
import hashlib
import json
import ssl
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener
from . import attest

ORIGIN="https://emubench.games"

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        return None

def post(path,data,headers):
    req=Request(ORIGIN+path,data=json.dumps(data).encode(),headers={"Content-Type":"application/json","User-Agent":"EmuBench/0.8",**headers})
    tls=ssl.create_default_context()
    import os
    for bundle in ("/etc/ssl/cert.pem","/etc/ssl/certs/ca-certificates.crt","/etc/pki/tls/certs/ca-bundle.crt"):
        if os.path.isfile(bundle):
            tls.load_verify_locations(cafile=bundle)
            break
    with build_opener(NoRedirect(),HTTPSHandler(context=tls)).open(req,timeout=30) as resp:
        return json.loads(resp.read(2048))

def publish(public):
    if public.get("repeatability",{}).get("accepted") is False:
        raise ValueError("Series failed the acceptance gate: "+", ".join(public["repeatability"].get("rejected_for") or ["spread"]))
    if public.get("mode")=="standalone-process-v1" and not public.get("render_checkpoints"):
        raise ValueError("The standalone runner lacks framebuffer checkpoints")
    key,bearer=attest.identity()
    if not public.get("attestation") or public.get("device_id")!=attest.device(key):
        raise ValueError("A new signed measurement from this installation is required")
    pub=key.verify_key.encode().hex()
    encoded=attest.record(public)
    from nacl.exceptions import BadSignatureError
    try:
        key.verify_key.verify(("EmuBench run v1\n"+encoded).encode(),bytes.fromhex(public["attestation"]))
    except BadSignatureError as exc:
        raise ValueError("Measurement changed after capture") from exc
    body={"record":encoded,"game":public["game"],"seal":public["attestation"]}
    body["signature"]=key.sign(("EmuBench submission v1\n"+body["seal"]+"\n"+body["game"]).encode()).signature.hex()
    headers={"Authorization":"Bearer "+bearer,"X-EmuBench-Key":pub}
    try:
        receipt=post("/api/runs",body,headers)
    except HTTPError as exc:
        if exc.code!=401:
            raise
        digest=hashlib.sha256(bearer.encode()).hexdigest()
        signed=key.sign(("EmuBench enroll v1\n"+digest).encode()).signature.hex()
        post("/api/installs",{"key":pub,"token_hash":digest,"signature":signed},{})
        receipt=post("/api/runs",body,headers)
    expected=ORIGIN+"/run/"+public["run_id"]
    if receipt.get("url")!=expected:
        raise ValueError("Unexpected score receipt")
    return expected
