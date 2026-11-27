"""Seal immutable public measurement fields when the harness completes a run."""
import hashlib
import json
import os
import tempfile
import uuid
from pathlib import Path
from nacl.signing import SigningKey
from . import engines, fsutil

def identity():
    root=engines.home()
    root.mkdir(mode=0o700,parents=True,exist_ok=True)
    path=root/"installation.secret"
    if not path.exists():
        fd,tmp=tempfile.mkstemp(dir=root)
        try:
            with os.fdopen(fd,"wb") as out:
                out.write(os.urandom(64))
                out.flush()
                os.fsync(out.fileno())
            try:
                fsutil.publish_new(tmp,path)
            except FileExistsError:
                pass
        finally:
            Path(tmp).unlink(missing_ok=True)
    data=path.read_bytes()
    if len(data)!=64:
        raise ValueError("Invalid installation identity")
    return SigningKey(data[:32]), data[32:].hex()

def device(key):
    return str(uuid.UUID(bytes=hashlib.sha256(key.verify_key.encode()).digest()[:16]))

def record(public):
    return json.dumps({k:v for k,v in public.items() if k not in ("game","attestation")},
                      ensure_ascii=False,separators=(",",":"),sort_keys=True,allow_nan=False)

def seal(public):
    key,_=identity()
    if public.get("device_id")!=device(key):
        raise ValueError("Measurement belongs to a different installation")
    return key.sign(("EmuBench run v1\n"+record(public)).encode()).signature.hex()

def complete(result):
    from .scores import public_fields
    result["attestation"]=seal(public_fields(result,"Personal ROM"))
