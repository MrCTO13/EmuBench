"""Public score service client. Only receive payloads prepared by public_fields."""
import json
from urllib.request import Request

from . import engines

ORIGIN = "https://emubench-scores.mrcto.chatgpt.site"


def publish(public):
    request = Request(ORIGIN + "/api/runs", method="POST", data=json.dumps(public).encode(),
                      headers={"Content-Type": "application/json", "User-Agent": "EmuBench/0.6"})
    with engines.open_upstream(request) as response:
        if response.url != request.full_url:
            raise ValueError("Unexpected score service redirect")
        receipt = json.loads(response.read(2048))
    expected = ORIGIN + "/run/" + public["run_id"]
    if receipt.get("url") != expected:
        raise ValueError("Unexpected score receipt")
    return expected
