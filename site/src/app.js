/* Page behaviour: live account check, chart hover, and the what-if model. */
(() => {
  const API = "https://tx.main.fastnear.com/v0/account";
  const WINDOW_DAYS = 14;
  const PAGE_SIZE = 200;
  const MAX_PAGES = 6;
  const DAY_MS = 86400000;

  const $ = (id) => document.getElementById(id);
  const data = window.PROOF;

  /* ---------- the live check ---------- */
  const VERDICT = {
    sleeper: { title: "Sleeps", tone: "good", text: "Across two weeks it used many hours of the day but never touched one sleep-sized stretch. Most verified humans do not pass this test, and some scripts could, so a pass is evidence, not proof." },
    routine: { title: "A narrow daily routine", tone: "mid", text: "Active only within one part of the day. That could be a person's habit or a scheduled job, and timing alone can't tell which." },
    machine: { title: "Never sleeps", tone: "bad", text: "Active around the clock, in many hours of a typical day. That is how a program behaves." },
    timer: { title: "On a timer", tone: "bad", text: "Fires in the same few hours of the day and nowhere else. That looks like a scheduled job." },
    unclear: { title: "Can't tell", tone: "mid", text: "It has been active enough to test, but its timing has no clear daily pattern. Most verified humans land here too." },
    too_few: { title: "Not enough to judge", tone: "mid", text: "It needs at least 5 active days out of 14 before the test means anything." },
    busy: { title: "Too fast to be a person", tone: "bad", text: "Its recent history fills up within hours. Nothing human keeps that pace." },
  };

  const fmtHour = (h) => String(Math.floor(((h % 24) + 24) % 24)).padStart(2, "0") + ":00";

  function offsetLabel(mid) {
    const off = Math.round(3.5 - mid - 0.0);
    const wrapped = ((off + 12) % 24 + 24) % 24 - 12;
    return "UTC" + (wrapped >= 0 ? "+" : "") + wrapped;
  }

  function normaliseAccount(raw) {
    const name = raw.trim().toLowerCase().replace(/^@/, "");
    return /^[a-z0-9._-]{2,64}$/.test(name) ? name : null;
  }

  /* A free public service: try again a couple of times before giving up. */
  async function post(body, retries) {
    for (let attempt = 0; ; attempt++) {
      try {
        const res = await fetch(API, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
        if (res.ok || attempt >= retries) return res;
      } catch (err) {
        if (attempt >= retries) throw err;
      }
      await new Promise((r) => setTimeout(r, 1300 * (attempt + 1)));
    }
  }

  async function fetchActivity(account, onProgress) {
    const now = Date.now();
    const todayStart = Math.floor(now / DAY_MS) * DAY_MS;
    const windowStart = todayStart - WINDOW_DAYS * DAY_MS;
    const times = [];
    let token = null;
    let total = 0;
    let exhausted = false;
    for (let page = 0; page < MAX_PAGES; page++) {
      const body = { account_id: account, is_any_signer: true, limit: PAGE_SIZE };
      if (token) body.resume_token = token;
      if (page > 0) await new Promise((r) => setTimeout(r, 450));   // be gentle with a free public service
      let res;
      try {
        res = await post(body, page === 0 ? 3 : 2);
      } catch (err) {
        if (page === 0) throw err;
        break;                                                       // keep what was already read
      }
      if (!res.ok) {
        if (page === 0) throw new Error("The public NEAR index answered with status " + res.status + ".");
        break;
      }
      const json = await res.json();
      const list = json.account_txs || [];
      total = json.txs_count || total;
      let oldest = Infinity;
      for (const tx of list) {
        const t = Number(BigInt(tx.tx_block_timestamp) / 1000000n);
        oldest = Math.min(oldest, t);
        times.push(t);
      }
      onProgress(times.length);
      token = json.resume_token;
      if (!token || !list.length || oldest < windowStart) { exhausted = true; break; }
    }
    const inWindow = times.filter((t) => t >= windowStart && t < todayStart);
    const newest = Math.max(...times, 0), oldest = Math.min(...times, newest);
    return { inWindow, windowStart, todayStart, total, exhausted, fetched: times.length, newest, oldest };
  }

  function toDayMasks(activity) {
    const byDay = new Map();
    for (const t of activity.inWindow) {
      const day = Math.floor((t - activity.windowStart) / DAY_MS);
      const hour = new Date(t).getUTCHours();
      byDay.set(day, (byDay.get(day) || 0) | (1 << hour));
    }
    const days = [...byDay.keys()].sort((a, b) => a - b);
    return { days, masks: days.map((d) => byDay.get(d)), byDay };
  }

  function actogramSvg(byDay, windowStart, gapInfo) {
    const rows = WINDOW_DAYS, rowH = 12, cellW = 11;
    const left = 44, top = 18, W = left + 24 * cellW + 10, H = top + rows * rowH + 22;
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Activity by hour for the last 14 days">`;
    if (gapInfo) {
      const start = ((gapInfo.mid - gapInfo.gap / 2) % 24 + 24) % 24;
      for (let i = 0; i < gapInfo.gap; i++) {
        const col = Math.floor((start + i) % 24);
        s += `<rect x="${left + col * cellW}" y="${top}" width="${cellW}" height="${rows * rowH}" class="sleep-band"/>`;
      }
    }
    for (let d = 0; d < rows; d++) {
      const mask = byDay.get(d) || 0;
      for (let h = 0; h < 24; h++) {
        if ((mask >> h) & 1) s += `<rect x="${left + h * cellW + 1}" y="${top + d * rowH + 1}" width="${cellW - 2}" height="${rowH - 2}" rx="1.5" class="tick"/>`;
      }
      if (d % 2 === 0) {
        const date = new Date(windowStart + d * DAY_MS).toISOString().slice(5, 10);
        s += `<text x="${left - 6}" y="${top + d * rowH + rowH - 2.5}" text-anchor="end" class="axis-night">${date}</text>`;
      }
    }
    for (const h of [0, 6, 12, 18, 24]) {
      s += `<line x1="${left + h * cellW}" x2="${left + h * cellW}" y1="${top - 3}" y2="${top + rows * rowH}" class="rule-night"/>`;
      s += `<text x="${left + h * cellW}" y="${top - 6}" text-anchor="middle" class="axis-night">${String(h % 24).padStart(2, "0")}</text>`;
    }
    s += `<text x="${left}" y="${H - 6}" class="axis-night">hour of day, UTC</text></svg>`;
    return s;
  }

  function showResult(account, verdictKey, info, svg) {
    const v = VERDICT[verdictKey];
    const box = $("result");
    box.hidden = false;
    box.dataset.tone = v.tone;
    $("result-title").textContent = v.title;
    $("result-account").textContent = account;
    $("result-text").textContent = v.text;
    $("result-chart").innerHTML = svg;
    const facts = $("result-facts");
    facts.textContent = "";
    for (const [k, val] of info) {
      const dt = document.createElement("dt"); dt.textContent = k;
      const dd = document.createElement("dd"); dd.textContent = val;
      facts.append(dt, dd);
    }
    $("examples").hidden = true;
  }

  function showError(message) {
    const el = $("check-status");
    el.textContent = message;
    el.dataset.state = "error";
  }

  async function runCheck(rawAccount) {
    const status = $("check-status");
    const account = normaliseAccount(rawAccount);
    if (!account) { showError("That doesn't look like a NEAR account name. Try something like root.near."); return; }
    status.dataset.state = "busy";
    status.textContent = "Reading " + account + "'s public history";
    $("check-button").disabled = true;
    try {
      const activity = await fetchActivity(account, (n) => { status.textContent = "Reading " + account + "'s public history: " + n.toLocaleString("en-US") + " transactions"; });
      const { days, masks, byDay } = toDayMasks(activity);
      const reachedStart = activity.exhausted;
      const spanDays = masks.length;
      let verdict, gapInfo = null, facts;
      if (activity.fetched === 0) {
        status.dataset.state = "error";
        status.textContent = account + " has no transactions in the public index. Check the spelling.";
        return;
      }
      if (!reachedStart && spanDays < 5) {
        verdict = "busy";
        const hours = Math.max((activity.newest - activity.oldest) / 3600000, 1 / 60);
        const spanText = hours < 1 ? Math.round(hours * 60) + " minutes" : hours.toFixed(1) + " hours";
        facts = [["Transactions read", activity.fetched.toLocaleString("en-US")], ["Spanning only", spanText], ["Pace", Math.round(activity.fetched / hours).toLocaleString("en-US") + " an hour"]];
      } else {
        const c = SleepCore.classify(masks, data.crit);
        verdict = c.class;
        if (c.class === "sleeper") gapInfo = { gap: c.gap, mid: c.mid };
        facts = [
          ["Active days", c.n_days + " of 14"],
          ["Hours of the day used", c.n_hours + " of 24"],
          ["Longest quiet stretch", c.gap + " hours"],
          ["Active hours on a typical day", c.hours_per_day.toFixed(1)],
        ];
        if (c.class === "sleeper") {
          facts.push(["Sleep window, UTC", fmtHour(c.mid - c.gap / 2) + " to " + fmtHour(c.mid + c.gap / 2)]);
          facts.push(["Fits a person living near", offsetLabel(c.mid)]);
        }
      }
      const picture = verdict === "busy"
        ? `<div class="busy-note"><b>${facts[2][1]}</b><span>transactions, and it never stops long enough to see a daily pattern.</span></div>`
        : actogramSvg(byDay, activity.windowStart, gapInfo);
      showResult(account, verdict, facts, picture);
      status.dataset.state = "done";
      status.textContent = "Computed in your browser from public chain data. Nothing was stored.";
    } catch (err) {
      showError("Could not reach the public NEAR index from this page. The live check needs a normal web page (it is blocked inside some previews). " + (err && err.message ? err.message : ""));
    } finally {
      $("check-button").disabled = false;
    }
  }

  const form = $("check-form");
  if (form) {
    form.addEventListener("submit", (e) => { e.preventDefault(); runCheck($("check-account").value); });
    document.querySelectorAll("[data-try]").forEach((btn) => btn.addEventListener("click", () => {
      $("check-account").value = btn.dataset.try;
      runCheck(btn.dataset.try);
    }));
    $("result-reset").addEventListener("click", () => {
      $("result").hidden = true;
      $("examples").hidden = false;
      $("check-status").textContent = "";
      $("check-status").removeAttribute("data-state");
    });
  }

  /* ---------- chart hover ---------- */
  const tip = document.createElement("div");
  tip.className = "tip";
  tip.setAttribute("role", "status");
  tip.hidden = true;
  document.body.append(tip);

  function renderTip(target) {
    tip.textContent = "";
    const lines = target.dataset.tip.split("|");
    lines.forEach((line, i) => {
      const row = document.createElement("div");
      if (i === 0) { row.className = "tip-head"; row.textContent = line; }
      else {
        const [label, value, color] = line.split("~");
        if (color) {
          const key = document.createElement("span");
          key.className = "tip-key";
          key.style.background = color;
          row.append(key);
        }
        const v = document.createElement("strong");
        v.textContent = value;
        const l = document.createElement("span");
        l.textContent = " " + label;
        row.append(v, l);
      }
      tip.append(row);
    });
  }

  function moveTip(e) {
    const pad = 14;
    const r = tip.getBoundingClientRect();
    let x = e.clientX + pad, y = e.clientY - r.height - pad;
    if (x + r.width > innerWidth - 8) x = e.clientX - r.width - pad;
    if (y < 8) y = e.clientY + pad;
    tip.style.transform = `translate(${x}px, ${y}px)`;
  }

  let active = null;
  document.addEventListener("pointerover", (e) => {
    const target = e.target.closest && e.target.closest("[data-tip]");
    if (active && active !== target) {
      active.classList.remove("on");
      active = null;
    }
    if (target) {
      active = target;
      target.classList.add("on");
      renderTip(target);
      tip.hidden = false;
      moveTip(e);
    } else {
      tip.hidden = true;
    }
  });
  document.addEventListener("pointermove", (e) => { if (!tip.hidden) moveTip(e); });

  /* ---------- what-if model ---------- */
  const slider = $("model-rate");
  if (slider) {
    const base = data.trend.latest;
    const peak = data.trend.peak;
    const fmt = (n) => Math.round(n).toLocaleString("en-US");
    const update = () => {
      const r = Number(slider.value) / 100;
      $("model-rate-out").textContent = (r >= 0 ? "+" : "") + (r * 100).toFixed(1) + "% a month";
      const project = (months) => base * Math.pow(1 + r, months);
      $("model-1y").textContent = fmt(project(12));
      $("model-3y").textContent = fmt(project(36));
      $("model-5y").textContent = fmt(project(60));
      const target = Number($("model-target").value);
      const needed = Math.pow(target / base, 1 / 60) - 1;
      $("model-needed").textContent = (needed >= 0 ? "+" : "") + (needed * 100).toFixed(1) + "% a month";
      $("model-target-out").textContent = fmt(target) + " people";
      let verdict;
      if (project(60) >= peak) verdict = "At this rate NEAR is back above its January 2025 peak of " + fmt(peak) + " people within five years.";
      else if (project(60) >= base) verdict = "At this rate the count grows, but stays below the January 2025 peak of " + fmt(peak) + " after five years.";
      else verdict = "At this rate the count keeps shrinking. Halving takes about " + (Math.log(0.5) / Math.log(1 + r)).toFixed(0) + " months.";
      $("model-verdict").textContent = verdict;
    };
    slider.addEventListener("input", update);
    $("model-target").addEventListener("input", update);
    update();
  }
})();
