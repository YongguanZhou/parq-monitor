"""
make_chart.py  —  读取 parq_traffic.csv,生成 chart.html。

三组图表(每组一张):
  - Parq (Vancouver): 1/3 / 1/3/6 / 2/5/10
  - Wynn (Las Vegas): 1/3 / 2/5 / 5/10 / 10/20 / 20/40
  - Hustler (LA):     1/3 / 2/3 / 2/5 / 5/5 / 5/5/10 / 10/20

每张图:横轴=一周 Mon-Sun,每周一条曲线。

用法:
  python make_chart.py                    # 读 parq_traffic.csv
  python make_chart.py path/to/data.csv
"""

import csv, sys, datetime, collections, json, os
from zoneinfo import ZoneInfo

CSV_PATH  = sys.argv[1] if len(sys.argv) > 1 else "parq_traffic.csv"
HTML_PATH = os.path.join(os.path.dirname(os.path.abspath(CSV_PATH)), "chart.html")

DAYS   = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
COLORS = ["#4e79a7","#f28e2b","#e15759","#76b7b2","#59a14f","#edc948","#b07aa1","#ff9da7"]

# 每个场馆要画的图：(图标题, CSV列名)
CHARTS = [
    # Parq
    ("Parq $1/$3 NLH",       "parq_1/3"),
    ("Parq $1/$3/$6 NLH",    "parq_1/3/6"),
    ("Parq $2/$5/$10 NLH",   "parq_2/5/10"),
    # Wynn
    ("Wynn $1/$3 NLH",       "wynn_1/3"),
    ("Wynn $2/$5 NLH",       "wynn_2/5"),
    ("Wynn $5/$10 NLH",      "wynn_5/10"),
    ("Wynn $10/$20 NLH",     "wynn_10/20"),
    ("Wynn $20/$40 NLH",     "wynn_20/40"),
    # Hustler
    ("Hustler $1/$3 NLH",    "hustler_1/3"),
    ("Hustler $2/$3 NLH",    "hustler_2/3"),
    ("Hustler $2/$5 NLH",    "hustler_2/5"),
    ("Hustler $5/$5 NLH",    "hustler_5/5"),
    ("Hustler $5/$5/$10 NLH","hustler_5/5/10"),
    ("Hustler $10/$20 NLH",  "hustler_10/20"),
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
    """返回 {week_str: [(minutes_in_week, ts, {col: val, ...}), ...]}"""
    by_week = collections.defaultdict(list)
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        cols = reader.fieldnames or []
        for row in reader:
            t = row.get("time", "").strip()
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
                if col in ("time", "weekday", "hour"):
                    continue
                try:
                    data[col] = int(row.get(col) or 0)
                except ValueError:
                    data[col] = 0
            by_week[wk].append((m, ts, data))
    for wk in by_week:
        by_week[wk].sort(key=lambda r: r[0])
    return by_week


def make_traces(by_week, col):
    traces = []
    for i, wk in enumerate(sorted(by_week)):
        pts = by_week[wk]
        x, y, text = [], [], []
        for m, ts, data in pts:
            val = data.get(col, 0)
            day = DAYS[m // 1440]
            hh  = (m % 1440) // 60
            mm  = m % 60
            x.append(m)
            y.append(val)
            text.append(f"{day} {hh:02d}:{mm:02d}<br>桌数: {val}<br>({ts.strftime('%Y-%m-%d')})")
        traces.append({
            "x": x, "y": y, "text": text,
            "mode": "lines+markers",
            "name": f"week of {wk}",
            "line": {"color": COLORS[i % len(COLORS)], "width": 1.5, "shape": "hv"},
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

    # 只渲染有数据的列（列存在且至少有一个非0值）
    all_cols = set()
    for pts in by_week.values():
        for _, _, data in pts:
            all_cols.update(data.keys())

    chart_blocks = ""
    plot_calls   = ""
    for idx, (title, col) in enumerate(CHARTS):
        if col not in all_cols:
            continue
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
  场馆: Parq (Vancouver) · Wynn (Las Vegas) · Hustler (LA) ·
  横轴: 周一至周日 · 原始10分钟采样 · 图例可点击开关 ·
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
