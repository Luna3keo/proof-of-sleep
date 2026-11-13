"""Reads the list of face-verified human accounts from the NEAR I-Am-Human registry.

Uses only public RPC view calls. The list stays in data/cache/ (ignored by git); nothing
derived from it is published except counts.

    python -m pipeline.pull_verified
"""
import base64
import json
import time
import urllib.request

from . import config

RPC = "https://free.rpc.fastnear.com"
REGISTRY = "registry.i-am-human.near"
ISSUER = "fractal.i-am-human.near"
PATH = config.ROOT / "data" / "cache" / "verified_accounts.json"


def view(method, args):
    body = {"jsonrpc": "2.0", "id": 1, "method": "query", "params": {
        "request_type": "call_function", "finality": "final", "account_id": REGISTRY, "method_name": method,
        "args_base64": base64.b64encode(json.dumps(args).encode()).decode()}}
    req = urllib.request.Request(RPC, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        out = json.load(resp)
    if "error" in out or "error" in out.get("result", {}):
        raise SystemExit(f"RPC error: {out}")
    return json.loads(bytes(out["result"]["result"]))


def pull():
    owners = []
    next_token = 1
    while True:
        rows = view("sbt_tokens", {"issuer": ISSUER, "from_token": next_token, "limit": 100, "with_expired": True})
        if not rows:
            break
        owners += [r["owner"] for r in rows]
        next_token = max(r["token"] for r in rows) + 1
        time.sleep(0.25)
    PATH.parent.mkdir(parents=True, exist_ok=True)
    PATH.write_text(json.dumps(sorted(set(owners))), encoding="utf-8")
    return sorted(set(owners))


def load():
    if PATH.exists():
        return json.loads(PATH.read_text(encoding="utf-8"))
    return pull()


if __name__ == "__main__":
    print(len(pull()), "accounts")
