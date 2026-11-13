"""The optional Explorer pull, tested against a local fake server. No network, no token."""
import datetime as dt
import json
import pathlib
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import pull_intents_explorer as pull  # noqa: E402

PAGES = {
    None: [{"amountInUsd": "1000.5", "depositAddress": f"a{i}", "depositMemo": None} for i in range(1000)],
    "a999": [{"amountInUsd": "2", "depositAddress": "b0", "depositMemo": "7"}],
}
SEEN = []


class Fake(BaseHTTPRequestHandler):
    def do_GET(self):
        query = parse_qs(urlparse(self.path).query)
        SEEN.append((self.headers.get("Authorization"), query))
        rows = PAGES.get((query.get("lastDepositAddress") or [None])[0], [])
        body = json.dumps(rows).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class ExplorerPull(unittest.TestCase):
    def test_pages_and_totals(self):
        server = HTTPServer(("127.0.0.1", 0), Fake)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        original = pull.BASE_URL
        pull.BASE_URL = f"http://127.0.0.1:{server.server_port}/transactions"
        try:
            out = pull.day_totals(dt.date(2026, 10, 1), "test-token", pause=0)
        finally:
            pull.BASE_URL = original
            server.shutdown()
        self.assertEqual(out["swaps"], 1001)
        self.assertAlmostEqual(out["volume_usd"], 1000 * 1000.5 + 2)
        self.assertEqual(len(SEEN), 2)
        self.assertEqual(SEEN[0][0], "Bearer test-token")
        self.assertEqual(SEEN[1][1]["lastDepositAddress"], ["a999"])
        self.assertNotIn("lastDepositMemo", SEEN[1][1])


if __name__ == "__main__":
    unittest.main()
