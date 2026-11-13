"""Small SVG chart helpers. Output is plain SVG markup coloured by CSS variables, so the
charts exist without JavaScript and follow the page's light and dark themes."""
import html
import math

W = 900          # drawing width; SVGs scale down to the panel


def esc(value) -> str:
    return html.escape(str(value), quote=True)


def full(n) -> str:
    return f"{n:,.0f}"


def compact(n) -> str:
    n = float(n)
    sign = "-" if n < 0 else ""
    n = abs(n)
    for limit, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if n >= limit:
            text = f"{n / limit:.1f}".rstrip("0").rstrip(".")
            return f"{sign}{text}{suffix}"
    return f"{sign}{n:g}"


def pct(x, digits=1) -> str:
    return f"{x * 100:.{digits}f}%"


MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def month_label(iso) -> str:
    year, month, _ = iso.split("-")
    return f"{MONTHS[int(month) - 1]} {year}"


def tip(head, rows):
    """Build a data-tip attribute: head line, then label~value~colour rows."""
    return esc("|".join([head] + [f"{label}~{value}~{colour}" for label, value, colour in rows]))


class Frame:
    def __init__(self, height=320, left=64, right=132, top=20, bottom=36, width=W):
        self.width = width
        self.height = height
        self.left = left
        self.right = right
        self.top = top
        self.bottom = bottom
        self.plot_w = width - left - right
        self.plot_h = height - top - bottom
        self.parts = []

    def add(self, markup):
        self.parts.append(markup)

    def svg(self, label):
        return (f'<svg viewBox="0 0 {self.width} {self.height}" class="chart" role="img" '
                f'aria-label="{esc(label)}">' + "".join(self.parts) + "</svg>")


def time_x(frame, count):
    step = frame.plot_w / count
    return step, (lambda i: frame.left + step * (i + 0.5))


def year_ticks(frame, windows, xfn):
    for i, w in enumerate(windows):
        if w["window"].endswith("-01-01"):
            x = xfn(i)
            frame.add(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{frame.top}" y2="{frame.top + frame.plot_h}" class="grid"/>')
            frame.add(f'<text x="{x:.1f}" y="{frame.top + frame.plot_h + 20}" text-anchor="middle" class="axis">{w["window"][:4]}</text>')


def legend(items):
    """items: (label, colour, kind) with kind 'line' or 'box'. Text stays in text colour."""
    out = ['<ul class="legend">']
    for label, colour, kind in items:
        out.append(f'<li><span class="lg-{kind}" style="background:{colour}"></span>{esc(label)}</li>')
    out.append("</ul>")
    return "".join(out)


def path(points):
    return "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in points)


def bar_path(x, y, width, height, radius):
    """A column with a rounded top and a square foot."""
    r = min(radius, width / 2, height)
    return (f"M{x:.1f} {y + height:.1f} L{x:.1f} {y + r:.1f} Q{x:.1f} {y:.1f} {x + r:.1f} {y:.1f} "
            f"L{x + width - r:.1f} {y:.1f} Q{x + width:.1f} {y:.1f} {x + width:.1f} {y + r:.1f} "
            f"L{x + width:.1f} {y + height:.1f} Z")


def nice_step(maximum, ticks=4):
    raw = maximum / ticks
    power = 10 ** math.floor(math.log10(raw))
    for mult in (1, 2, 2.5, 5, 10):
        if raw <= mult * power:
            return mult * power
    return 10 * power


def line_log(windows, series, label, height=340, start=0):
    """series: list of (key, name, colour). One log axis: every series is a count of accounts."""
    data = windows[start:]
    frame = Frame(height=height)
    step, x = time_x(frame, len(data))
    values = [w[k] for k, _, _ in series for w in data if w[k]]
    low = math.floor(math.log10(min(values)))
    high = math.ceil(math.log10(max(values)))
    y = lambda v: frame.top + frame.plot_h * (1 - (math.log10(v) - low) / (high - low))
    for power in range(low, high + 1):
        v = 10 ** power
        frame.add(f'<line x1="{frame.left}" x2="{frame.width - frame.right}" y1="{y(v):.1f}" y2="{y(v):.1f}" class="grid"/>')
        frame.add(f'<text x="{frame.left - 8}" y="{y(v) + 4:.1f}" text-anchor="end" class="axis">{compact(v)}</text>')
    year_ticks(frame, data, x)
    for key, name, colour in series:
        pts = [(x(i), y(w[key])) for i, w in enumerate(data) if w[key]]
        frame.add(f'<path d="{path(pts)}" class="line" style="stroke:{colour}"/>')
        lx, ly = pts[-1]
        frame.add(f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="4.5" class="dot" style="fill:{colour}"/>')
        last = [w[key] for w in data if w[key]][-1]
        frame.add(f'<text x="{lx + 10:.1f}" y="{ly + 4:.1f}" class="end">{full(last)}</text>')
    for i, w in enumerate(data):
        rows = [(name, full(w[key]) if w[key] else "n/a", colour) for key, name, colour in series]
        frame.add(f'<rect x="{x(i) - step / 2:.1f}" y="{frame.top}" width="{step:.1f}" height="{frame.plot_h}" '
                  f'class="hit" data-tip="{tip(month_label(w["window"]), rows)}"/>')
    return frame.svg(label) + legend([(n, c, "line") for _, n, c in series])


def stacked_columns(windows, series, label, height=340, start=0, y_max=None, label_each=False):
    """series: list of (key, name, colour) stacked in order, bottom first."""
    data = windows[start:]
    frame = Frame(height=height, right=26)
    step, x = time_x(frame, len(data))
    top_value = max(sum(w[k] for k, _, _ in series) for w in data)
    maximum = y_max or top_value
    tick = nice_step(maximum)
    y_scale = math.ceil(maximum / tick) * tick
    y = lambda v: frame.top + frame.plot_h * (1 - v / y_scale)
    v = 0
    while v <= y_scale + 1e-6:
        frame.add(f'<line x1="{frame.left}" x2="{frame.width - frame.right}" y1="{y(v):.1f}" y2="{y(v):.1f}" class="grid"/>')
        frame.add(f'<text x="{frame.left - 8}" y="{y(v) + 4:.1f}" text-anchor="end" class="axis">{compact(v) if v else "0"}</text>')
        v += tick
    if label_each:
        for i, w in enumerate(data):
            frame.add(f'<text x="{x(i):.1f}" y="{frame.top + frame.plot_h + 20}" text-anchor="middle" class="axis">{month_label(w["window"])}</text>')
    else:
        year_ticks(frame, data, x)
    bar = min(step - 2, 24 if label_each else 16)
    for i, w in enumerate(data):
        cx = x(i) - bar / 2
        base = 0.0
        tops = [k for k, _, _ in series if w[k] > 0]
        for key, name, colour in series:
            value = w[key]
            if value <= 0:
                continue
            y0, y1 = y(base + value), y(base)
            h = max(y1 - y0 - 2, 0.75)                 # 2px surface gap between segments
            is_top = key == tops[-1]
            d = bar_path(cx, y0, bar, h, 3 if is_top else 0)
            frame.add(f'<path d="{d}" style="fill:{colour}"/>')
            base += value
        rows = [(name, full(w[key]), colour) for key, name, colour in reversed(series)]
        total = sum(w[key] for key, _, _ in series)
        rows.append(("total", full(total), "transparent"))
        frame.add(f'<rect x="{x(i) - step / 2:.1f}" y="{frame.top}" width="{step:.1f}" height="{frame.plot_h}" '
                  f'class="hit" data-tip="{tip(month_label(w["window"]), rows)}"/>')
    return frame.svg(label) + legend([(n, c, "box") for _, n, c in reversed(series)])


def line_share(windows, key, name, colour, label, height=280, start=0):
    data = windows[start:]
    frame = Frame(height=height, right=120)
    step, x = time_x(frame, len(data))
    y = lambda v: frame.top + frame.plot_h * (1 - v)
    for v in (0, 0.25, 0.5, 0.75, 1):
        frame.add(f'<line x1="{frame.left}" x2="{frame.width - frame.right}" y1="{y(v):.1f}" y2="{y(v):.1f}" class="grid"/>')
        frame.add(f'<text x="{frame.left - 8}" y="{y(v) + 4:.1f}" text-anchor="end" class="axis">{int(v * 100)}%</text>')
    year_ticks(frame, data, x)
    pts = [(x(i), y(w[key])) for i, w in enumerate(data)]
    area = pts + [(pts[-1][0], y(0)), (pts[0][0], y(0))]
    frame.add(f'<path d="{path(area)} Z" style="fill:{colour};opacity:.1"/>')
    frame.add(f'<path d="{path(pts)}" class="line" style="stroke:{colour}"/>')
    lx, ly = pts[-1]
    frame.add(f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="4.5" class="dot" style="fill:{colour}"/>')
    frame.add(f'<text x="{lx + 10:.1f}" y="{ly + 4:.1f}" class="end">{pct(data[-1][key])}</text>')
    for i, w in enumerate(data):
        frame.add(f'<rect x="{x(i) - step / 2:.1f}" y="{frame.top}" width="{step:.1f}" height="{frame.plot_h}" '
                  f'class="hit" data-tip="{tip(month_label(w["window"]), [(name, pct(w[key]), colour)])}"/>')
    return frame.svg(label)


def indexed_lines(windows, series, label, base_index=0, height=340):
    """Index every series to 100 at the first window, one log axis. End labels show real values."""
    data = windows[base_index:]
    frame = Frame(height=height, right=150)
    step, x = time_x(frame, len(data))
    rebased = {}
    for key, name, colour, _ in series:
        first = next(w[key] for w in data if w[key])
        rebased[key] = [w[key] / first * 100 if w[key] else None for w in data]
    allv = [v for s in rebased.values() for v in s if v]
    low = math.floor(math.log10(min(allv)))
    high = math.ceil(math.log10(max(allv)))
    y = lambda v: frame.top + frame.plot_h * (1 - (math.log10(v) - low) / (high - low))
    for power in range(low, high + 1):
        v = 10 ** power
        frame.add(f'<line x1="{frame.left}" x2="{frame.width - frame.right}" y1="{y(v):.1f}" y2="{y(v):.1f}" class="grid"/>')
        frame.add(f'<text x="{frame.left - 8}" y="{y(v) + 4:.1f}" text-anchor="end" class="axis">{compact(v)}</text>')
    for i, w in enumerate(data):
        if w["window"].endswith("-01-01") or i == 0:
            xx = x(i)
            frame.add(f'<line x1="{xx:.1f}" x2="{xx:.1f}" y1="{frame.top}" y2="{frame.top + frame.plot_h}" class="grid"/>')
            frame.add(f'<text x="{xx:.1f}" y="{frame.top + frame.plot_h + 20}" text-anchor="middle" class="axis">{w["window"][:7]}</text>')
    ends = []
    for key, name, colour, fmt in series:
        pts = [(x(i), y(v)) for i, v in enumerate(rebased[key]) if v]
        frame.add(f'<path d="{path(pts)}" class="line" style="stroke:{colour}"/>')
        ends.append((pts[-1], colour, fmt(next(w[key] for w in reversed(data) if w[key]))))
    for (lx, ly), colour, text in ends:
        frame.add(f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="4.5" class="dot" style="fill:{colour}"/>')
        frame.add(f'<text x="{lx + 10:.1f}" y="{ly + 4:.1f}" class="end">{esc(text)}</text>')
    for i, w in enumerate(data):
        rows = [(name, fmt(w[key]) if w[key] else "n/a", colour) for key, name, colour, fmt in series]
        frame.add(f'<rect x="{x(i) - step / 2:.1f}" y="{frame.top}" width="{step:.1f}" height="{frame.plot_h}" '
                  f'class="hit" data-tip="{tip(month_label(w["window"]), rows)}"/>')
    return frame.svg(label) + legend([(n, c, "line") for _, n, c, _ in series])


def histogram_compare(categories, series, label, height=300, x_title="", value_fmt=None):
    """Two distributions over the same categories, drawn as lines."""
    frame = Frame(height=height, right=24, bottom=50)
    step, x = time_x(frame, len(categories))
    fmt = value_fmt or (lambda v: f"{v * 100:.1f}%")
    maximum = max(max(s) for _, s, _ in series)
    tick = nice_step(maximum)
    y_scale = math.ceil(maximum / tick) * tick
    y = lambda v: frame.top + frame.plot_h * (1 - v / y_scale)
    v = 0
    while v <= y_scale + 1e-9:
        frame.add(f'<line x1="{frame.left}" x2="{frame.width - frame.right}" y1="{y(v):.1f}" y2="{y(v):.1f}" class="grid"/>')
        frame.add(f'<text x="{frame.left - 8}" y="{y(v) + 4:.1f}" text-anchor="end" class="axis">{v * 100:.0f}%</text>')
        v += tick
    for i, c in enumerate(categories):
        if i % 3 == 0:
            frame.add(f'<text x="{x(i):.1f}" y="{frame.top + frame.plot_h + 20}" text-anchor="middle" class="axis">{esc(c)}</text>')
    if x_title:
        frame.add(f'<text x="{frame.left + frame.plot_w / 2:.1f}" y="{frame.height - 8}" text-anchor="middle" class="axis">{esc(x_title)}</text>')
    for name, values, colour in series:
        pts = [(x(i), y(v)) for i, v in enumerate(values)]
        frame.add(f'<path d="{path(pts)}" class="line" style="stroke:{colour}"/>')
    for i, c in enumerate(categories):
        rows = [(name, fmt(values[i]), colour) for name, values, colour in series]
        frame.add(f'<rect x="{x(i) - step / 2:.1f}" y="{frame.top}" width="{step:.1f}" height="{frame.plot_h}" '
                  f'class="hit" data-tip="{tip(str(c), rows)}"/>')
    return frame.svg(label) + legend([(n, c, "line") for n, _, c in series])


def columns(categories, values, colour, label, height=260, x_every=3, x_title="", value_fmt=None, tip_prefix=""):
    """One series of plain columns."""
    frame = Frame(height=height, right=24, bottom=48)
    step, x = time_x(frame, len(categories))
    fmt = value_fmt or full
    maximum = max(values)
    tick = nice_step(maximum)
    y_scale = math.ceil(maximum / tick) * tick
    y = lambda v: frame.top + frame.plot_h * (1 - v / y_scale)
    v = 0
    while v <= y_scale + 1e-9:
        frame.add(f'<line x1="{frame.left}" x2="{frame.width - frame.right}" y1="{y(v):.1f}" y2="{y(v):.1f}" class="grid"/>')
        frame.add(f'<text x="{frame.left - 8}" y="{y(v) + 4:.1f}" text-anchor="end" class="axis">{fmt(v) if v else "0"}</text>')
        v += tick
    bar = min(step - 2, 24)
    for i, c in enumerate(categories):
        value = values[i]
        y0 = y(value)
        h = y(0) - y0
        if h > 0:
            frame.add(f'<path d="{bar_path(x(i) - bar / 2, y0, bar, h, 4)}" style="fill:{colour}"/>')
        if i % x_every == 0:
            frame.add(f'<text x="{x(i):.1f}" y="{frame.top + frame.plot_h + 20}" text-anchor="middle" class="axis">{esc(c)}</text>')
        frame.add(f'<rect x="{x(i) - step / 2:.1f}" y="{frame.top}" width="{step:.1f}" height="{frame.plot_h}" '
                  f'class="hit" data-tip="{tip(tip_prefix + str(c), [("", fmt(value), colour)])}"/>')
    if x_title:
        frame.add(f'<text x="{frame.left + frame.plot_w / 2:.1f}" y="{frame.height - 8}" text-anchor="middle" class="axis">{esc(x_title)}</text>')
    return frame.svg(label)


def grouped_bars_h(rows, label, colour, value_fmt=full, max_value=None):
    """Plain HTML bars for a ranked table."""
    maximum = max_value or max(v for _, v in rows)
    out = ['<div class="rank">']
    for name, value in rows:
        out.append(
            f'<div class="rank-row"><span class="rank-name">{esc(name)}</span>'
            f'<span class="rank-bar"><span style="width:{value / maximum * 100:.1f}%;background:{colour}"></span></span>'
            f'<span class="rank-val">{value_fmt(value)}</span></div>'
        )
    out.append("</div>")
    return "".join(out)


def table(headers, rows, numeric_from=1):
    out = ['<div class="table-wrap"><table><thead><tr>']
    for i, h in enumerate(headers):
        cls = ' class="num"' if i >= numeric_from else ""
        out.append(f"<th{cls}>{esc(h)}</th>")
    out.append("</tr></thead><tbody>")
    for row in rows:
        out.append("<tr>")
        for i, cell in enumerate(row):
            cls = ' class="num"' if i >= numeric_from else ""
            out.append(f"<td{cls}>{esc(cell)}</td>")
        out.append("</tr>")
    out.append("</tbody></table></div>")
    return "".join(out)
