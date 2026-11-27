"""Read Libretro's RACSIG01 sidecar when its rolling index precedes a signed build."""
from dataclasses import replace
from datetime import date, datetime, timezone
from functools import lru_cache
from hashlib import sha256
import re

from ecdsa import BadSignatureError, NIST256p, VerifyingKey
from . import downloads

REVISION = "b20beba47a1683f3ac2650a90eb2f603247956e2"
KEYS_URL = f"https://raw.githubusercontent.com/libretro/RetroArch/{REVISION}/core_signing_keys.h"
KEYS_SHA256 = "988e3b48bfb8bbb4a8cadc2221d8bfa113212b3f488e7d50f3d3230063901c33"


@lru_cache(maxsize=1)
def release_signers():
    header = downloads.fetch_bytes(KEYS_URL, 16384)
    if sha256(header).hexdigest() != KEYS_SHA256:
        raise ValueError("Unexpected Libretro signing key manifest")
    # The upstream header keeps the public test key outside the production list.
    production = header.split(b"#define CORE_SIGNING_KEYS_LIST", 1)[1].split(b"#else", 1)[0]
    keys = {}
    for entry in re.findall(rb"\{([^}]+)\}", production):
        point = bytes(int(v, 16) for v in re.findall(rb"0x([0-9a-f]{2})", entry))
        if len(point) != 65 or point[0] != 4:
            raise ValueError("Invalid Libretro public verifier")
        keys[sha256(point).digest()[:8]] = VerifyingKey.from_string(point, curve=NIST256p)
    return keys


def verified_package(spec, sidecar):
    if len(sidecar) < 122 or sidecar[:8] != b"RACSIG01":
        raise ValueError("Missing Libretro core signature")
    length = sidecar[56]
    if len(sidecar) != 57 + length + 64 or sidecar[57:57+length] != spec.member.encode():
        raise ValueError("Libretro signature names a different core")
    key = release_signers().get(sidecar[8:16])
    if not key:
        raise ValueError("Unknown Libretro release signer")
    try:
        key.verify(sidecar[-64:], sidecar[:-64], hashfunc=sha256)
    except BadSignatureError as exc:
        raise ValueError("Invalid Libretro release signature") from exc
    stamp = int.from_bytes(sidecar[16:24], "big")
    build = datetime.fromtimestamp(stamp, timezone.utc).date()
    if build < date.fromisoformat(spec.version.split("+")[0]):
        raise ValueError("Signed build predates the upstream index")
    digest = sidecar[24:56].hex()
    return replace(spec, version=f"{build}+{digest[:12]}", identity=sha256(sidecar).hexdigest(),
                   checksum="member-sha256:" + digest)


def resolve(spec):
    sidecar = downloads.fetch_bytes(spec.url.removesuffix(".zip") + ".sig", 512)
    return verified_package(spec, sidecar)
