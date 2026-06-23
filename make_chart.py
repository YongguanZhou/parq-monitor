"""
make_chart.py  —  读取 parq_traffic.csv,生成 chart.html。

只画 tables(不画 wait)。三个场馆共 14 张 NLH 图:
  Parq:    1/3 / 1/3/6 / 2/5/10
  Wynn:    1/3 / 2/5 / 5/10 / 10/20 / 20/40
  Hustler: 1/3 / 2/3 / 2/5 / 5/5 / 5/5/10 / 10/20

每张图:横轴=一周 Mon-Sun,每周一条曲线。
某档若历史上从未开过桌(整列全0),该图自动跳过不渲染。

用法:
  python make_chart.py                    # 读 parq_traffic.csv
  python make_chart.py path/to/data.csv
"""

import csv, sys, datetime, collections, json, os
from zoneinfo import ZoneInfo

CSV_PATH  = sys.argv[1] if len(sys.argv) > 1 else "parq_traffic.csv"
HTML_PATH = os.path.join(os.path.dirname(os.path.abspath(CSV_PATH)), "chart.html")

DAYS = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]

def week_colors(n):
    """生成 n 个 HSL 等间距色相，饱和度/亮度固定，感知差距最大化。"""
    import colorsys
    colors = []
    for i in range(n):
        h = i / n          # 0.0 ~ 1.0，均匀分布
        r, g, b = colorsys.hls_to_rgb(h, 0.58, 0.72)
        colors.append(f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}")
    return colors

# 要画的图：(图标题, CSV中的 tables 列名)
CHARTS = [
    ("Parq $1/$3 NLH",        "1/3 NLH tables"),
    ("Parq $1/$3/$6 NLH",     "1/3/6 NLH tables"),
    ("Parq $2/$5/$10 NLH",    "2/5/10 NLH tables"),
    ("Wynn $1/$3 NLH",        "wynn_1/3 tables"),
    ("Wynn $2/$5 NLH",        "wynn_2/5 tables"),
    ("Wynn $5/$10 NLH",       "wynn_5/10 tables"),
    ("Wynn $10/$20 NLH",      "wynn_10/20 tables"),
    ("Wynn $20/$40 NLH",      "wynn_20/40 tables"),
    ("Hustler $1/$3 NLH",     "hustler_1/3 tables"),
    ("Hustler $2/$3 NLH",     "hustler_2/3 tables"),
    ("Hustler $2/$5 NLH",     "hustler_2/5 tables"),
    ("Hustler $5/$5 NLH",     "hustler_5/5 tables"),
    ("Hustler $5/$5/$10 NLH", "hustler_5/5/10 tables"),
    ("Hustler $10/$20 NLH",   "hustler_10/20 tables"),
]


def week_monday(ts):
    return (ts - datetime.timedelta(
        days=ts.weekday(), hours=ts.hour,
        minutes=ts.minute, seconds=ts.second,
        microseconds=ts.microsecond
    )).strftime("%Y-%m-%d")


def minutes_in_week(ts):
    return ts.weekday() * 1440 + ts.hour * 60 + ts.minute


def load(path):
    """返回 {week_str: [(minutes, ts, {col: val}), ...]}"""
    by_week = collections.defaultdict(list)
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        cols = [c for c in (reader.fieldnames or []) if c not in ("time","weekday","hour")]
        for row in reader:
            t = (row.get("time") or "").strip()
            if not t:
                continue
            try:
                ts = datetime.datetime.fromisoformat(t)
            except ValueError:
                continue
            wk = week_monday(ts)
            m  = minutes_in_week(ts)
            data = {}
            for col in cols:
                v = row.get(col)
                try:
                    data[col] = int(v) if v not in (None, "") else 0
                except ValueError:
                    data[col] = 0
            by_week[wk].append((m, ts, data))
    for wk in by_week:
        by_week[wk].sort(key=lambda r: r[0])
    return by_week


def smooth(y, window=6):
    """简单滑动平均，window=6 约等于 1 小时（每 10 分钟采样）。"""
    out = []
    for i in range(len(y)):
        lo = max(0, i - window // 2)
        hi = min(len(y), lo + window)
        chunk = [v for v in y[lo:hi] if v is not None]
        out.append(round(sum(chunk) / len(chunk), 2) if chunk else None)
    return out


def make_traces(by_week, col):
    weeks  = sorted(by_week)
    colors = week_colors(len(weeks))
    traces = []
    for i, wk in enumerate(weeks):
        pts = by_week[wk]
        x   = [m        for m, ts, data in pts]
        y   = [data.get(col, 0) for _, _, data in pts]
        text = []
        for m, ts, data in pts:
            day = DAYS[m // 1440]
            hh  = (m % 1440) // 60
            mm  = m % 60
            text.append(f"{day} {hh:02d}:{mm:02d}<br>桌数: {data.get(col,0)}<br>({ts.strftime('%Y-%m-%d')})")

        color = colors[i]
        label = f"week of {wk}"

        # 原始数据：细线、半透明，不显示在图例
        traces.append({
            "x": x, "y": y,
            "mode": "lines",
            "name": label,
            "legendgroup": label,
            "showlegend": False,
            "line": {"color": color, "width": 1, "shape": "hv", "dash": "dot"},
            "opacity": 0.35,
            "hoverinfo": "skip",
            "connectgaps": True,
        })

        # 平滑线：粗线、不透明，显示 hover
        ys = smooth(y)
        traces.append({
            "x": x, "y": ys, "text": text,
            "mode": "lines+markers",
            "name": label,
            "legendgroup": label,
            "showlegend": True,
            "line": {"color": color, "width": 2.5, "shape": "spline", "smoothing": 0.8},
            "marker": {"size": 3},
            "hovertemplate": "%{text}<extra></extra>",
            "connectgaps": True,
        })
    return traces


def x_tickvals_labels():
    vals, labels = [], []
    for d in range(7):
        for h in [0, 6, 12, 18]:
            vals.append(d * 1440 + h * 60)
            labels.append(f"{DAYS[d]}<br>{h:02d}:00" if h == 0 else f"{h:02d}:00")
    return vals, labels


def build_html(by_week):
    tv, tl  = x_tickvals_labels()
    updated = datetime.datetime.now(ZoneInfo("America/Vancouver")).strftime("%Y-%m-%d %H:%M")
    weeks   = sorted(by_week)
    total   = sum(len(v) for v in by_week.values())

    chart_blocks, plot_calls = "", ""
    for idx, (title, col) in enumerate(CHARTS):
        div_id = f"g{idx}"
        traces = make_traces(by_week, col)
        chart_blocks += f'<div class="chart"><div id="{div_id}" style="height:340px"></div></div>\n'
        plot_calls += f"""
Plotly.newPlot("{div_id}",
  {json.dumps(traces)},
  {{...base, title:{{text:{json.dumps(title)},font:{{color:"#ddd",size:13}}}}}},
  cfg);
"""

    return f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Poker Traffic Monitor</title>
<script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></script>
<style>
  body  {{ background:#111; color:#ccc; font-family:sans-serif; margin:0; padding:16px; }}
  h2    {{ margin:0 0 4px; color:#eee; font-size:1.1em; }}
  .sub  {{ font-size:.8em; color:#888; margin-bottom:16px; }}
  .chart{{ background:#1a1a1a; border-radius:8px; margin-bottom:24px; padding:8px; }}
</style>
</head>
<body>
<h2>Poker Room Traffic — Weekly Overlay</h2>
<div class="sub">
  Parq (Vancouver) · Wynn (Las Vegas) · Hustler (LA) ·
  横轴: 周一至周日 · 每周一条曲线 · 图例可点击开关 ·
  {len(weeks)} 周 / {total} 个数据点 · 最后更新: {updated} (Vancouver time)
</div>

{chart_blocks}

<script>
const TV = {json.dumps(tv)};
const TL = {json.dumps(tl)};
const xaxis = {{
  tickvals:TV, ticktext:TL,
  gridcolor:"#2a2a2a", tickfont:{{color:"#aaa",size:10}},
  range:[-60, 10140]
}};
const yaxis = {{gridcolor:"#2a2a2a", tickfont:{{color:"#aaa"}}, rangemode:"tozero"}};
const base = {{
  paper_bgcolor:"#1a1a1a", plot_bgcolor:"#1a1a1a",
  font:{{color:"#ccc"}}, xaxis, yaxis,
  legend:{{bgcolor:"#222", bordercolor:"#444", borderwidth:1}},
  margin:{{t:44,b:64,l:44,r:16}},
  hovermode:"closest",
}};
const cfg = {{responsive:true, displayModeBar:false}};

{plot_calls}
</script>
</body>
</html>"""


def main():
    if not os.path.exists(CSV_PATH):
        print(f"找不到 {CSV_PATH}")
        return
    by_week = load(CSV_PATH)
    html    = build_html(by_week)
    with open(HTML_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    weeks = sorted(by_week)
    total = sum(len(v) for v in by_week.values())
    print(f"chart.html 已更新 — {len(weeks)} 周({', '.join(weeks)}) / {total} 个数据点")


if __name__ == "__main__":
    main()
