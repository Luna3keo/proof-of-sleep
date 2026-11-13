"""Films the demo from the real dashboard: a real browser, a real click, a live answer from public NEAR data.

Run video/make_voice.py first; the picture follows the voice. Needs Microsoft Edge or Chrome and imageio-ffmpeg.

    python video/make_film.py            # writes media/demo.mp4
    python video/make_film.py --stills   # a frame every 1.5 seconds in video/out/stills
"""
import argparse
import base64
import html
import json
import os
import pathlib
import re
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
WORK = ROOT / "video" / "out"
SITE = ROOT / "site"
TARGET = ROOT / "media" / "demo.mp4"
FPS = 30
WIDTH, HEIGHT = 1120, 630
SCALE = 12 / 7
TOP = 56
OFF_SCREEN = (1040.0, 640.0)

MOON = '<svg viewBox="0 0 24 24"><path d="M20 15.5A8.5 8.5 0 0 1 8.5 4a8.5 8.5 0 1 0 11.5 11.5Z" fill="#ffd27a"/></svg>'
PERSON = ('<svg viewBox="0 0 64 64" fill="none" stroke="#edf1fd" stroke-width="3.4" stroke-linecap="round">'
          '<circle cx="32" cy="20" r="11"/><path d="M12 56c2-15 10-22 20-22s18 7 20 22"/></svg>')
ROBOT = ('<svg viewBox="0 0 64 64" fill="none" stroke="#ff9172" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round">'
         '<rect x="12" y="22" width="40" height="30" rx="6"/><path d="M32 22V10M26 36h.01M38 36h.01M26 45h12"/><circle cx="32" cy="8" r="2.5"/></svg>')
QUESTION = '<span class="q">?</span>'

GATE_JS = """
(() => {
  const real = window.fetch.bind(window);
  const gate = window.__gate = { open: false, arrived: 0, waiting: [] };
  window.fetch = async (url, options) => {
    if (String(url).indexOf("fastnear") < 0) return real(url, options);
    const response = await real(url, options);
    const body = await response.text();
    gate.arrived += 1;
    if (!gate.open) await new Promise((go) => gate.waiting.push(go));
    return new Response(body, { status: response.status, statusText: response.statusText, headers: response.headers });
  };
  gate.release = () => { gate.open = true; gate.waiting.splice(0).forEach((go) => go()); };
})();
"""

FILM_JS = r"""
(() => {
  const F = __SPEC__;
  const ease = (x) => (x <= 0 ? 0 : x >= 1 ? 1 : x * x * (3 - 2 * x));
  const during = (t, on, off, fade) => Math.min(ease((t - on) / fade), ease((off - t) / fade));
  const body = 'var(--body)', display = 'var(--display)';
  const sheet = document.createElement("style");
  sheet.textContent = `
    html{scroll-behavior:auto!important} body{overflow:hidden}
    #film-spot,#film-cap,#film-cursor,#film-ring,#film-end,#film-title,#film-label{pointer-events:none}
    #film-title{position:fixed;inset:0;z-index:57;display:grid;place-items:center;padding:30px 80px;opacity:0;background:#0f1835}
    #film-title>div{grid-area:1/1;display:flex;flex-direction:column;align-items:center;gap:22px;opacity:0;text-align:center}
    #film-title p{margin:0;font:700 54px/1.12 ${display};color:#edf1fd;max-width:960px;text-wrap:balance}
    #film-title .big{font:700 150px/1 ${display};color:#ffd27a;letter-spacing:-.03em}
    #film-title .art{display:flex;align-items:center;justify-content:center;gap:34px}
    #film-title .art svg{height:150px;width:auto}
    #film-title .q{font:800 150px/1 ${display};color:#ffd27a}
    #film-title pre{margin:0;text-align:left;font:500 26px/1.5 var(--mono);color:#edf1fd;background:#070c1d;border:1px solid #2f3b6a;border-radius:14px;padding:22px 30px}
    #film-title pre b{color:#ffd27a;font-weight:600}
    #film-label{position:fixed;top:12px;left:18px;z-index:59;font:700 18px/1.2 ${body};color:#ffd27a;background:rgba(7,12,29,.92);border:1px solid rgba(255,210,122,.45);border-radius:8px;padding:6px 12px;opacity:0}
    #film-spot{position:fixed;z-index:40;border-radius:14px;opacity:0;box-shadow:0 0 0 3px #ffd27a,0 0 46px 8px rgba(255,210,122,.3),0 0 0 4000px rgba(4,7,20,.66)}
    #film-cap{position:fixed;left:0;right:0;bottom:0;z-index:60;display:flex;justify-content:center;padding:46px 34px 18px;background:linear-gradient(to top,rgba(4,7,20,.97) 58%,rgba(4,7,20,0));opacity:0}
    #film-cap span{font:600 29px/1.26 ${body};color:#f4f6fd;text-align:center;max-width:1020px}
    #film-cap b{font-weight:750;color:#ffd27a}
    #film-cursor{position:fixed;left:0;top:0;z-index:70;width:34px;height:34px;opacity:0}
    #film-ring{position:fixed;left:0;top:0;z-index:69;width:44px;height:44px;border-radius:50%;border:3px solid #ffd27a;opacity:0}
    #film-end{position:fixed;inset:0;z-index:58;background:#0f1835;display:flex;flex-direction:column;justify-content:center;align-items:center;opacity:0;text-align:center;padding:0 60px 30px}
    #film-end svg{width:56px;height:56px;margin-bottom:10px}
    #film-end h2{font:700 64px/1.1 ${display};margin:0 0 26px;color:#edf1fd}
    #film-end .name{font:700 30px ${body};color:#ffd27a;margin:0 0 8px}
    #film-end .small{font:400 20px ${body};color:#b4bedb;margin:4px 0}
  `;
  document.head.append(sheet);
  const make = (id) => { const d = document.createElement("div"); d.id = id; document.body.append(d); return d; };
  const spot = make("film-spot"), cap = make("film-cap"), cursor = make("film-cursor"), ring = make("film-ring"), end = make("film-end"), title = make("film-title"), label = make("film-label");
  const cards = F.titles.map((x) => { const d = document.createElement("div"); d.innerHTML = x.html; title.append(d); return d; });
  cap.innerHTML = "<span></span>";
  cursor.innerHTML = '<svg viewBox="0 0 24 24" width="34" height="34"><path d="M4 2l16 11.5-7.2 1.3-4 6.7z" fill="#fff" stroke="#0a0a0a" stroke-width="1.6" stroke-linejoin="round"/></svg>';
  end.innerHTML = F.end.html;
  const question = end.querySelector("h2");
  window.__film = {
    clickAt: -9,
    seek(t, cx, cy, cursorOn) {
      let previous = 0, y = 0;
      const most = document.documentElement.scrollHeight - innerHeight;
      for (const shot of F.camera) {
        if (t < shot.at) break;
        const el = shot.el === "top" ? null : document.querySelector(shot.el);
        const goal = el ? Math.max(0, Math.min(most, el.getBoundingClientRect().top + scrollY - shot.offset)) : 0;
        y = shot.ease ? previous + (goal - previous) * ease((t - shot.at) / shot.ease) : goal;
        previous = goal;
      }
      scrollTo(0, y);
      let best = null, strength = 0;
      for (const s of F.spots) { const a = during(t, s.on, s.off, 0.3); if (a > strength) { strength = a; best = s; } }
      let spotKey = "";
      if (best) {
        const r = document.querySelector(best.el).getBoundingClientRect(), pad = best.pad ?? 8;
        spot.style.left = `${r.left - pad}px`; spot.style.top = `${r.top - pad}px`;
        spot.style.width = `${r.width + pad * 2}px`; spot.style.height = `${r.height + pad * 2}px`;
        spotKey = `${Math.round(r.left)},${Math.round(r.top)},${Math.round(r.width)},${Math.round(r.height)}`;
      }
      spot.style.opacity = strength;
      let text = "", capOn = 0;
      for (const c of F.captions) if (t >= c.on && t <= c.off) { text = c.html; capOn = during(t, c.on, c.off, 0.1); }
      if (cap.dataset.text !== text) { cap.firstChild.innerHTML = text; cap.dataset.text = text; }
      cap.style.opacity = capOn;
      const cardOn = Math.max(0, ...F.blocks.map((b) => during(t, b.on, b.off, 0.4)));
      title.style.opacity = cardOn;
      const cardKey = F.titles.map((x, i) => { const a = during(t, x.on, x.off, 0.2); cards[i].style.opacity = a; return a.toFixed(3); }).join();
      let name = "", nameOn = 0;
      for (const l of F.labels) if (t >= l.on && t <= l.off) { name = l.text; nameOn = during(t, l.on, l.off, 0.2); }
      if (label.textContent !== name) label.textContent = name;
      label.style.opacity = nameOn;
      const endOn = ease((t - F.end.on) / 0.6), questionOn = ease((t - F.end.question) / 0.5);
      end.style.opacity = endOn; question.style.opacity = questionOn;
      cursor.style.opacity = cursorOn; cursor.style.transform = `translate(${cx}px,${cy}px)`;
      const since = t - this.clickAt, ringOn = since >= 0 && since < 0.6 ? 1 - since / 0.6 : 0;
      ring.style.opacity = ringOn; ring.style.transform = `translate(${cx - 22}px,${cy - 22}px) scale(${0.35 + since * 2})`;
      return [cardOn.toFixed(3), cardKey, Math.round(y), spotKey, strength.toFixed(3), text, capOn.toFixed(2), name, nameOn.toFixed(2), endOn.toFixed(3), questionOn.toFixed(3),
        Math.round(cx), Math.round(cy), cursorOn, ringOn.toFixed(3), document.getElementById("check-status").textContent, document.getElementById("result").hidden].join("|");
    },
  };
})();
"""


class Tab:
    """Just enough of the browser's debugging protocol, over a plain socket."""

    def __init__(self, url):
        parts = urllib.parse.urlsplit(url)
        self.sock = socket.create_connection((parts.hostname, parts.port))
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((f"GET {parts.path} HTTP/1.1\r\nHost: {parts.netloc}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                           f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        self.stream = self.sock.makefile("rb")
        while self.stream.readline().strip():
            pass
        self.count = 0

    def _send(self, payload):
        mask = os.urandom(4)
        size = len(payload)
        if size < 126:
            head = bytes([0x81, 0x80 | size])
        elif size < 65536:
            head = bytes([0x81, 0x80 | 126]) + struct.pack(">H", size)
        else:
            head = bytes([0x81, 0x80 | 127]) + struct.pack(">Q", size)
        self.sock.sendall(head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))

    def _receive(self):
        message = b""
        while True:
            first, second = self.stream.read(2)
            size = second & 0x7F
            if size == 126:
                size = struct.unpack(">H", self.stream.read(2))[0]
            elif size == 127:
                size = struct.unpack(">Q", self.stream.read(8))[0]
            data = self.stream.read(size)
            if first & 0x0F in (0, 1, 2):
                message += data
                if first & 0x80:
                    return message

    def call(self, method, **params):
        self.count += 1
        self._send(json.dumps({"id": self.count, "method": method, "params": params}).encode())
        while True:
            reply = json.loads(self._receive())
            if reply.get("id") == self.count:
                if "error" in reply:
                    raise RuntimeError(f"{method}: {reply['error']}")
                return reply.get("result", {})

    def run(self, expression):
        result = self.call("Runtime.evaluate", expression=expression, returnByValue=True, awaitPromise=True)
        if "exceptionDetails" in result:
            raise RuntimeError(f"{expression[:80]}: {result['exceptionDetails']}")
        return result["result"].get("value")

    def mouse(self, kind, x, y, **extra):
        self.call("Input.dispatchMouseEvent", type=kind, x=x, y=y, **extra)

    def rect(self, selector):
        return self.run(f"(() => {{const r = document.querySelector({json.dumps(selector)}).getBoundingClientRect(); return {{x: r.left, y: r.top, w: r.width, h: r.height}};}})()")

    def frame(self):
        return base64.b64decode(self.call("Page.captureScreenshot", format="jpeg", quality=94, fromSurface=True)["data"])


def browser():
    for path in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", r"C:\Program Files\Google\Chrome\Application\chrome.exe"):
        if os.path.exists(path):
            return path
    found = shutil.which("msedge") or shutil.which("chrome") or shutil.which("chromium")
    if not found:
        sys.exit("No Chromium browser found")
    return found


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def open_site(profile):
    site_port, debug_port = free_port(), free_port()
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(site_port), "--bind", "127.0.0.1", "--directory", str(SITE)],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    chrome = subprocess.Popen([browser(), "--headless=new", "--disable-gpu", "--hide-scrollbars", "--mute-audio", "--no-first-run",
                               f"--remote-debugging-port={debug_port}", f"--user-data-dir={profile}", "about:blank"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    tab = None
    for _ in range(150):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{debug_port}/json/list", timeout=2) as resp:
                tab = next(t for t in json.load(resp) if t["type"] == "page")
            with urllib.request.urlopen(f"http://127.0.0.1:{site_port}/", timeout=2):
                break
        except (OSError, StopIteration):
            time.sleep(0.2)
    if tab is None:
        sys.exit("The browser did not start")
    page = Tab(tab["webSocketDebuggerUrl"])
    page.call("Page.enable")
    page.call("Runtime.enable")
    page.call("Emulation.setDeviceMetricsOverride", width=WIDTH, height=HEIGHT, deviceScaleFactor=SCALE, mobile=False)
    page.call("Emulation.setEmulatedMedia", features=[{"name": "prefers-color-scheme", "value": "dark"}])
    page.call("Page.addScriptToEvaluateOnNewDocument", source=GATE_JS)
    page.call("Page.navigate", url=f"http://127.0.0.1:{site_port}/")
    for _ in range(200):
        if page.run("document.readyState") == "complete" and page.run("document.fonts.status") == "loaded":
            break
        time.sleep(0.1)
    time.sleep(1.0)
    return [server, chrome], page


def stop(processes, profile):
    for process in processes:
        process.kill()
    if os.name == "nt":
        script = ("Get-CimInstance Win32_Process -Filter \"Name='msedge.exe' OR Name='chrome.exe'\" | "
                  f"Where-Object {{ $_.CommandLine -match '{pathlib.Path(profile).name}' }} | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force }}")
        subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True)
    time.sleep(1)
    shutil.rmtree(profile, ignore_errors=True)


def caption_html(text):
    return re.sub(r"\d[\d,.]*%?", lambda m: f"<b>{m.group(0)}</b>", html.escape(text, quote=False))


def card(art, text):
    picture = f'<div class="art">{art}</div>' if art else ""
    return f"{picture}<p>{html.escape(text, quote=False)}</p>"


def rebuild_output():
    done = subprocess.run([sys.executable, "rebuild.py", "--check"], cwd=ROOT, capture_output=True, text=True, check=True)
    keep = [line for line in done.stdout.splitlines() if not line.startswith(("charts", "sha256"))]
    lines = [html.escape(line) for line in keep]
    lines[-1] = f"<b>{lines[-1]}</b>"
    return "<b>$ python rebuild.py --check</b>\n" + "\n".join(lines)


def build_spec(timeline):
    takes = {t["name"]: t for t in timeline["takes"]}
    m = {line["mark"]: line for t in timeline["takes"] for line in t["lines"]}
    start, stop_at, show = (lambda k: m[k]["start"]), (lambda k: m[k]["end"]), (lambda k: m[k]["show"])
    camera = [
        {"at": 0, "el": "top", "offset": 0, "ease": 0},
        {"at": start("rows") - 0.45, "el": ".check", "offset": TOP, "ease": 0.8},
        {"at": start("people") - 0.35, "el": ".tiles", "offset": TOP + 14, "ease": 0.8},
        {"at": start("fall") - 0.25, "el": "#families", "offset": TOP, "ease": 0.7},
        {"at": start("verified") - 0.25, "el": "#verified", "offset": TOP, "ease": 0.8},
        {"at": start("catch") - 0.25, "el": "#relayed", "offset": TOP, "ease": 0.7},
        {"at": start("clock") - 0.25, "el": "#dst", "offset": TOP, "ease": 0.7},
        {"at": start("mind") - 0.25, "el": "#changes", "offset": TOP, "ease": 0.7},
    ]
    spot = lambda key, el, pad=8, tail=0.3: {"on": start(key), "off": stop_at(key) + tail, "el": el, "pad": pad}  # noqa: E731
    spots = [
        spot("never", "h1"), spot("built", ".lede"), spot("rows", "#examples"),
        spot("person", "#examples .ex:nth-child(1)"), spot("machine", "#examples .ex:nth-child(2)"), spot("timer", "#examples .ex:nth-child(3)"),
        spot("live", '[data-try="sweat-relayer.near"]', 6), spot("click", "#check-status", 6),
        spot("verdict", "#result", 6, 0.55),
        {"on": start("people"), "off": stop_at("est") + 0.3, "el": ".tile:nth-child(1)", "pad": 8}, spot("mach", ".tile:nth-child(2)"),
        spot("fall", "#families .plot", 10), spot("verified", "#verified .plot", 10), spot("floor", "#verified .says", 8),
        spot("catch", "#relayed .plot", 10), spot("clock", "#dst .plot", 10), spot("mind", "#changes table", 8),
    ]
    on_cards = {"ask", "count", "either", "which", "thesis", "rebuild", "yours", "never", "verdict"}
    captions = [{"on": line["start"] - 0.06, "off": line["end"] + 0.2, "html": caption_html(line["show"])}
                for take in timeline["takes"] for line in take["lines"] if line["mark"] not in on_cards]
    count_show = show("count")
    big_number = re.match(r"[\d,]+", count_show).group(0)
    titles = [
        {"on": -1, "off": start("count") - 0.05, "html": card(PERSON + PERSON + QUESTION, show("ask"))},
        {"on": start("count") - 0.05, "off": start("either") - 0.05, "html": f'<div class="big">{big_number}</div><p>accounts were active on NEAR in two weeks of October</p>'},
        {"on": start("either") - 0.05, "off": start("which") - 0.05, "html": card(PERSON + ROBOT, show("either"))},
        {"on": start("which") - 0.05, "off": stop_at("which") + 0.45, "html": card(QUESTION, show("which"))},
        {"on": start("thesis") - 0.25, "off": stop_at("thesis") + 0.3, "html": card("", show("thesis"))},
        {"on": start("rebuild") - 0.25, "off": start("yours") + 0.1, "html": f"<pre>{rebuild_output()}</pre><p style=\"font-size:34px\">{html.escape(show('rebuild'))}</p>"},
    ]
    blocks = [{"on": -1, "off": stop_at("which") + 0.45}, {"on": start("thesis") - 0.5, "off": stop_at("thesis") + 0.5},
              {"on": start("rebuild") - 0.5, "off": start("yours") + 0.2}]
    ordered = timeline["takes"]
    labels = [{"on": -1 if i == 0 else t["start"] - 0.2, "off": ordered[i + 1]["start"] - 0.2 if i + 1 < len(ordered) else 9999, "text": t["label"]}
              for i, t in enumerate(ordered) if t["name"] != "you"]
    end_html = (f"{MOON}<h2>{html.escape(show('yours'))}</h2><p class=\"name\">Proof of Sleep</p>"
                "<p class=\"small\">Humans sleep. Machines don't. A reproducible test on public NEAR data.</p>"
                "<p class=\"small\">Narration: AI voice. Research, not financial advice.</p>")
    return {"camera": camera, "spots": spots, "captions": captions, "titles": titles, "blocks": blocks, "labels": labels,
            "end": {"on": start("yours") - 0.1, "question": start("yours") - 0.1, "html": end_html}}


class Director:
    """Runs the real click and the cursor, in step with the voice."""

    def __init__(self, page, timeline):
        self.page = page
        m = {line["mark"]: line for t in timeline["takes"] for line in t["lines"]}
        self.x, self.y = OFF_SCREEN
        self.path = None
        click = m["click"]["start"] + 0.15
        self.events = [
            (m["live"]["start"] + 0.2, self.to_button),
            (click, self.press_button),
            (m["verdict"]["start"] - 0.15, self.release),
        ]
        self.fades = [(m["live"]["start"] + 0.1, 1.0), (m["verdict"]["start"] + 0.6, 0.0)]

    def opacity(self, t):
        value = 0.0
        for at, target in self.fades:
            if t >= at:
                value = target if t - at >= 0.25 else value + (target - value) * min((t - at) / 0.25, 1.0)
        return round(value, 2)

    def position(self, t):
        if self.path:
            begin, seconds, x0, y0, x1, y1 = self.path
            k = min(max((t - begin) / seconds, 0), 1)
            k = k * k * (3 - 2 * k)
            self.x, self.y = x0 + (x1 - x0) * k, y0 + (y1 - y0) * k
            if k >= 1:
                self.path = None
        return self.x, self.y

    def to_button(self, t):
        r = self.page.rect('[data-try="sweat-relayer.near"]')
        self.path = (t, 1.0, self.x, self.y, r["x"] + r["w"] * 0.55, r["y"] + r["h"] * 0.55)

    def press_button(self, t):
        x, y = self.position(t)
        self.page.mouse("mouseMoved", x, y)
        self.page.mouse("mousePressed", x, y, button="left", clickCount=1)
        self.page.mouse("mouseReleased", x, y, button="left", clickCount=1)
        self.page.run(f"window.__film.clickAt = {t}")

    def release(self, t):
        for _ in range(1800):
            if self.page.run("window.__gate.arrived") >= 1:
                break
            time.sleep(0.05)
        else:
            sys.exit("The public NEAR index did not answer in time. Status: "
                     + str(self.page.run("document.getElementById('check-status').textContent + ' | input=' + document.getElementById('check-account').value")))
        self.page.run("window.__gate.release()")
        for _ in range(600):
            if not self.page.run("document.getElementById('result').hidden"):
                break
            time.sleep(0.05)
        else:
            sys.exit("The live check did not finish: " + str(self.page.run("document.getElementById('check-status').textContent")))
        title = self.page.run("document.getElementById('result-title').textContent")
        print("live verdict:", title, flush=True)
        if title != "Too fast to be a person":
            sys.exit(f"Live verdict was {title!r}, but the voice says 'Too fast to be a person'")

    def step(self, t):
        touched = False
        while self.events and self.events[0][0] <= t:
            _, action = self.events.pop(0)
            action(t)
            touched = True
        return touched


def ffmpeg_exe():
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def film(page, spec, timeline, stills):
    page.run(FILM_JS.replace("__SPEC__", json.dumps(spec)))
    director = Director(page, timeline)
    total = int(timeline["duration"] * FPS)
    still_every = int(FPS * 1.5)
    folder = WORK / "stills"
    encoder = None
    if stills:
        shutil.rmtree(folder, ignore_errors=True)
        folder.mkdir(parents=True)
    else:
        encoder = subprocess.Popen([
            ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(FPS), "-c:v", "mjpeg", "-i", "-",
            "-vf", "scale=in_color_matrix=bt601:in_range=pc:out_color_matrix=bt709:out_range=tv,format=yuv420p",
            "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
            str(WORK / "picture.mp4")], stdin=subprocess.PIPE)
    last_key, last_frame = None, None
    began = time.time()
    for i in range(total):
        t = i / FPS
        touched = director.step(t)
        x, y = director.position(t)
        key = page.run(f"window.__film.seek({t}, {x}, {y}, {director.opacity(t)})")
        if stills:
            if i % still_every == 0:
                (folder / f"{t:06.1f}.jpg").write_bytes(page.frame())
            continue
        if key != last_key or touched or last_frame is None:
            last_frame = page.frame()
            last_key = key
        encoder.stdin.write(last_frame)
        if i % 300 == 0:
            print(f"{t:.0f} of {timeline['duration']:.0f} s, {time.time() - began:.0f} s so far", flush=True)
    if encoder:
        encoder.stdin.close()
        if encoder.wait():
            sys.exit("The video encoder failed")


def loudness(graph, inputs):
    done = subprocess.run([ffmpeg_exe(), "-hide_banner", "-nostats", *inputs, "-filter_complex", f"{graph},loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
                          capture_output=True, text=True, check=True)
    return json.loads(done.stderr[done.stderr.rindex("{"): done.stderr.rindex("}") + 1])


def finish():
    inputs = ["-i", str(WORK / "voice.wav"), "-i", str(WORK / "music.wav")]
    graph = "[0:a]aresample=48000,pan=stereo|c0=c0|c1=c0[v];[v][1:a]amix=inputs=2:normalize=0:duration=longest"
    level = loudness(graph, inputs)
    second = (f"{graph},loudnorm=I=-16:TP=-1.5:LRA=11:linear=true:measured_I={level['input_i']}:measured_TP={level['input_tp']}:"
              f"measured_LRA={level['input_lra']}:measured_thresh={level['input_thresh']}:offset={level['target_offset']}")
    mix = WORK / "mix.wav"
    subprocess.run([ffmpeg_exe(), "-y", "-loglevel", "error", *inputs, "-filter_complex", second, "-ar", "48000", "-c:a", "pcm_s16le", str(mix)], check=True)
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(WORK / "picture.mp4"), "-i", str(mix), "-map", "0:v", "-map", "1:a",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(TARGET)], check=True)
    print(f"{TARGET.relative_to(ROOT)}: {TARGET.stat().st_size / 1e6:.1f} MB")
    timeline = json.loads((WORK / "timeline.json").read_text(encoding="utf-8"))
    (ROOT / "data" / "out" / "video_seconds.txt").write_text(f"{timeline['duration']:.0f}\n", encoding="utf-8", newline="\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--stills", action="store_true")
    parser.add_argument("--audio-only", action="store_true")
    args = parser.parse_args()
    if not (WORK / "timeline.json").exists():
        sys.exit("Run video/make_voice.py first")
    if args.audio_only:
        finish()
        return 0
    timeline = json.loads((WORK / "timeline.json").read_text(encoding="utf-8"))
    profile = tempfile.mkdtemp(prefix="pos-film-")
    processes, page = open_site(profile)
    try:
        film(page, build_spec(timeline), timeline, args.stills)
    finally:
        stop(processes, profile)
    if not args.stills:
        finish()
    return 0


if __name__ == "__main__":
    sys.exit(main())
