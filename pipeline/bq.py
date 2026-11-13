"""Minimal BigQuery client: standard library plus a gcloud sign-in. No pip install."""
import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

from . import config

_token = {"value": None, "at": 0.0}


def _access_token() -> str:
    if _token["value"] and time.time() - _token["at"] < 1800:
        return _token["value"]
    exe = shutil.which("gcloud.cmd") or shutil.which("gcloud") or "gcloud"
    out = subprocess.run([exe, "auth", "print-access-token"], capture_output=True, text=True)
    if out.returncode != 0 or not out.stdout.strip():
        raise SystemExit("gcloud is not signed in. Run: gcloud auth login\n" + out.stderr[:500])
    _token.update(value=out.stdout.strip(), at=time.time())
    return _token["value"]


def _call(url: str, body=None, tries: int = 6):
    for attempt in range(tries):
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Authorization": "Bearer " + _access_token(), "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as err:
            text = err.read().decode("utf-8", "replace")
            if err.code in (429, 500, 502, 503) and attempt < tries - 1:
                time.sleep(5 * (attempt + 1))
                continue
            raise SystemExit(f"BigQuery error {err.code}: {text[:1500]}")
        except (urllib.error.URLError, TimeoutError) as err:
            if attempt < tries - 1:
                time.sleep(5 * (attempt + 1))
                continue
            raise SystemExit(f"Network error talking to BigQuery: {err}")


def _jobs_url() -> str:
    return f"https://bigquery.googleapis.com/bigquery/v2/projects/{config.project()}/jobs"


def _results_url(job_id: str, location: str) -> str:
    return (f"https://bigquery.googleapis.com/bigquery/v2/projects/{config.project()}"
            f"/queries/{job_id}?location={location}")


def _ref() -> dict:
    """The NEAR dataset lives in us-east1, so jobs and our own tables must run there too."""
    return {"projectId": config.project(), "location": config.LOCATION}


def dry_run(sql: str) -> int:
    """Bytes BigQuery would read. Costs nothing."""
    job = _call(_jobs_url(), {"jobReference": _ref(), "configuration": {
        "dryRun": True, "query": {"query": sql, "useLegacySql": False}}})
    return int(job["statistics"]["totalBytesProcessed"])


def query(sql: str, max_bytes: int):
    """Run SQL with a hard byte cap. Returns (rows as a list of dicts, bytes read)."""
    planned = dry_run(sql)
    if planned > max_bytes:
        raise SystemExit(f"Refusing to run: would read {planned/1e9:.1f} GB, limit is {max_bytes/1e9:.1f} GB.")
    job = _call(_jobs_url(), {"jobReference": _ref(), "configuration": {"query": {
        "query": sql, "useLegacySql": False, "maximumBytesBilled": str(max_bytes)}}})
    job_id = job["jobReference"]["jobId"]
    location = job["jobReference"].get("location", config.LOCATION)
    base = _results_url(job_id, location)
    while True:
        page = _call(base + "&maxResults=20000&timeoutMs=20000")
        if page.get("jobComplete"):
            break
    if page.get("errors"):
        raise SystemExit(f"Query failed: {page['errors']}")
    schema = page.get("schema")
    if not schema:                       # DDL statement: no result set
        return [], planned
    columns = [field["name"] for field in schema["fields"]]
    rows = []
    while True:
        for row in page.get("rows", []):
            rows.append({c: cell["v"] for c, cell in zip(columns, row["f"])})
        token = page.get("pageToken")
        if not token:
            break
        page = _call(base + "&maxResults=20000&pageToken=" + token)
    return rows, planned


def log(message: str):
    print(message, file=sys.stderr, flush=True)
