"""
make_chart.py  —  读取 parq_traffic.csv,生成 chart.html(两张重叠周期图)。

图表设计:
  - 两张图:上面 1/3 NLH、下面 1/3/6 NLH
  - 横轴:一周(Mon 00:00 → Sun 23:59),原始10分钟采样粒度
  - 每周一条曲线,不同颜色;图例可点击单独开关
  - 数据缺口(>20分钟无数据)自动断线,不连过去
  - Hover 显示:周几 HH:MM / 桌数 / 所属日期

用法:
  python make_chart.py                    # 读 parq_traffic.csv,生成 chart.html
  python make_chart.py path/to/data.csv   # 指定 CSV 路径
"""

import csv, sys, datetime, collections, json, os

CSV_PATH  = sys.argv[1] if len(sys.argv) > 1 else "parq_traffic.csv"
HTML_PATH = os.path.join(os.path.dirname(os.path.abspath(CSV_PATH)), "chart.html")

DAYS   = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
COLORS = ["#4e79a7","#f28e2b","#e15759","#76b7b2","#59a14f","#edc948","#b07aa1","#ff9da7"]


def week_monday(ts):
    return (ts - datetime.timedelta(
        days=ts.weekday(), hours=ts.hour,
        minutes=ts.minute, seconds=ts.second,
        microseconds=ts.microsecond
    )).strftime("%Y-%m-%d")


def minutes_in_week(ts):
    """0 = Mon 00:00, 最大 = Sun 23:59"""
    return ts.weekday() * 1440 + ts.hour * 60 + ts.minute


def load(path):
    """返回 {week_str: [(minutes_in_week, ts, t13, t136), ...]} 按时间排序"""
    by_week = collections.defaultdict(list)
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            t = row.get("time", "").strip()
            if not t: continue
            try:
                ts = datetime.datetime.fromisoformat(t)
            except ValueError:
                continue
            wk  = week_monday(ts)
            m   = minutes_in_week(ts)
            t13  = int(row.get("1/3 NLH tables") or 0)
            t136 = int(row.get("1/3/6 NLH tables") or 0)
            by_week[wk].append((m, ts, t13, t136))
    # 每周内按时间排序
    for wk in by_week:
        by_week[wk].sort(key=lambda r: r[0])
    return by_week


def make_traces(by_week, col):
    """
    col: 2=t13, 3=t136
    在 >GAP_MINUTES 的缺口处插 None 断线。
    x 用"分钟数"(0-10079),hover 里再格式化成 'Tue 14:30'。
    """
    traces = []
    for i, wk in enumerate(sorted(by_week)):
        pts = by_week[wk]
        x, y, text = [], [], []
        prev_m = None
        for m, ts, t13, t136 in pts:
            val = t13 if col == 2 else t136
            day = DAYS[m // 1440]
            hh  = (m % 1440) // 60
            mm  = m % 60
            x.append(m)
            y.append(val)
            text.append(f"{day} {hh:02d}:{mm:02d}<br>桌数: {val}<br>({ts.strftime('%Y-%m-%d')})")
            prev_m = m

        traces.append({
            "x": x, "y": y, "text": text,
            "mode": "lines+markers",
            "name": f"week of {wk}",
            "line": {"color": COLORS[i % len(COLORS)], "width": 1.5, "shape": "hv"},
            "marker": {"size": 3},
            "hovertemplate": "%{text}<extra></extra>",
            "hoveron": "points",
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
    tv, tl   = x_tickvals_labels()
    t13_tr   = make_traces(by_week, 2)
    t136_tr  = make_traces(by_week, 3)
    updated  = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    weeks    = sorted(by_week)
    total_pts = sum(len(v) for v in by_week.values())

    return f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Parq Traffic — Weekly Overlay</title>
<script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></script>
<style>
  body  {{ background:#111; color:#ccc; font-family:sans-serif; margin:0; padding:16px; }}
  h2    {{ margin:0 0 4px; color:#eee; font-size:1.1em; }}
  .sub  {{ font-size:.8em; color:#888; margin-bottom:16px; }}
  .chart{{ background:#1a1a1a; border-radius:8px; margin-bottom:24px; padding:8px; }}
</style>
</head>
<body>
<h2>Parq Casino — Table Count by Week</h2>
<div class="sub">
  横轴: 周一至周日 · 原始10分钟采样 · 断线=数据缺口 · 图例可点击开关 ·
  {len(weeks)} 周 / {total_pts} 个数据点 · 最后更新: {updated} (Vancouver time)
</div>

<div class="chart"><div id="g13"  style="height:380px"></div></div>
<div class="chart"><div id="g136" style="height:380px"></div></div>

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

Plotly.newPlot("g13",
  {json.dumps(t13_tr)},
  {{...base, title:{{text:"$1/$3 NLH — Tables running",font:{{color:"#ddd",size:13}}}}}},
  cfg);

Plotly.newPlot("g136",
  {json.dumps(t136_tr)},
  {{...base, title:{{text:"$1/$3/$6 NLH — Tables running",font:{{color:"#ddd",size:13}}}}}},
  cfg);
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
