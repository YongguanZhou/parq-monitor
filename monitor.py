"""
monitor.py  —  抓 Parq 实时牌局,写入宽表 CSV,并自动更新 chart.html。

用法:
  本地循环:  python monitor.py --loop 600
  云端单次:  python monitor.py

环境变量:
  PA_COOKIE  登录后的整段 Cookie
"""

import csv, os, re, sys, time, datetime, subprocess
import requests
from bs4 import BeautifulSoup

URL      = "https://www.pokeratlas.com/boxes/live_cash_games?from=main&vid=9872"
CSV_PATH = "parq_traffic.csv"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://www.pokeratlas.com/poker-room/parq-vancouver/cash-games",
}

LEVELS = [
    ("1/3 NLH",    "1 - $3 NLH"),
    ("1/3/6 NLH",  "1-$3-$6"),
    ("2/5/10 NLH", "2-$5-$10"),
    ("2/5 PLO",    "PLO"),
    ("High Hand",  "High Hand"),
]


def _to_int(s):
    m = re.search(r"\d+", s or "")
    return int(m.group()) if m else 0


def fetch_html(retries=3, delay=5):
    headers = dict(HEADERS)
    cookie  = os.getenv("PA_COOKIE")
    if cookie:
        headers["Cookie"] = cookie
    last_err = None
    for attempt in range(retries):
        try:
            r = requests.get(URL, headers=headers, timeout=20)
            r.raise_for_status()
            return r.text
        except Exception as e:
            last_err = e
            if attempt < retries - 1:
                time.sleep(delay)
    raise last_err


def parse(html):
    soup  = BeautifulSoup(html, "html.parser")
    games = []
    for tr in soup.select("tr.live-cash-game"):
        tds = tr.find_all("td")
        if len(tds) < 3:
            continue
        games.append((tds[0].get_text(strip=True),
                      _to_int(tds[1].get_text()),
                      _to_int(tds[2].get_text())))
    return games


def match_levels(games):
    found, matched = {}, set()
    for name, t, w in games:
        for label, frag in LEVELS:
            if frag.lower() in name.lower():
                found[label] = (t, w)
                matched.add(name)
                break
    ordered   = [(label, *found.get(label, (0, 0))) for label, _ in LEVELS]
    unmatched = [n for (n, _, _) in games if n not in matched]
    return ordered, unmatched


def csv_header():
    h = ["time", "weekday", "hour"]
    for label, _ in LEVELS:
        h += [f"{label} tables", f"{label} wait"]
    return h


def log_wide(ts, ordered):
    new = not os.path.exists(CSV_PATH)
    with open(CSV_PATH, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(csv_header())
        row = [ts.isoformat(timespec="minutes"), ts.strftime("%a"), ts.hour]
        for _, t, wait in ordered:
            row += [t, wait]
        w.writerow(row)


def update_chart():
    """每次采集后重新生成 chart.html,供 GitHub Pages 展示。"""
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "make_chart.py")
    if os.path.exists(script):
        try:
            subprocess.run([sys.executable, script], check=True, timeout=30)
        except Exception as e:
            print(f"  [chart] 生成失败(不影响数据记录): {e}")
    else:
        print("  [chart] make_chart.py 不在同目录,跳过图表更新。")


def run_once():
    ts = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-7)))
    try:
        html = fetch_html()
    except Exception as e:
        print(f"{ts:%H:%M} 抓取失败(重试后仍失败): {e}")
        return False

    games = parse(html)
    if not games:
        print(f"{ts:%H:%M} 找到 0 个牌局 —— cookie 可能过期,请更新 PA_COOKIE。")
        return False

    ordered, unmatched = match_levels(games)
    log_wide(ts, ordered)
    update_chart()   # 采集完立刻更新图表

    summary = "  ".join(f"{lbl} {t}/{w}" for lbl, t, w in ordered)
    print(f"{ts:%Y-%m-%d %H:%M}  {summary}")
    if unmatched:
        print(f"  ⚠ 未识别级别: {unmatched}")
    return True


def main():
    interval = None
    if "--loop" in sys.argv:
        i        = sys.argv.index("--loop")
        interval = int(sys.argv[i + 1]) if i + 1 < len(sys.argv) else 600

    if interval is None:
        ok = run_once()
        if not ok:
            sys.exit(1)
        return

    print(f"本地循环模式:每 {interval} 秒抓一次,Ctrl+C 停。数据写入 {CSV_PATH}")
    try:
        while True:
            run_once()
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n已停止。")


if __name__ == "__main__":
    main()
