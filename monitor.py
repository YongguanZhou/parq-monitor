"""
monitor.py  —  抓 Parq 实时牌局,写入宽表 CSV(纵向时间 / 横向各级别)。当前阶段:只记录,不报警。

用法:
  本地循环:  python monitor.py --loop 600     # 每600秒抓一次,Ctrl+C 停
  云端单次:  python monitor.py                 # 抓一次即退出,交给 GitHub Actions 定时

数据接口(页面 JS 实际请求的 dynamic-box;vid=9872=Parq):
  https://www.pokeratlas.com/boxes/live_cash_games?from=main&vid=9872

环境变量:
  PA_COOKIE  登录后的整段 Cookie(本地 PowerShell: $env:PA_COOKIE="...")

输出:parq_traffic.csv —— 每行一个时间点,每个级别两列(桌数 tables / 等位 wait)。
注意:若之前跑过旧版(长表),请先删掉旧的 parq_traffic.csv 再跑,避免表头不一致。

本地依赖: pip install requests beautifulsoup4
"""

import csv
import os
import re
import sys
import time
import datetime
import requests
from bs4 import BeautifulSoup

URL = "https://www.pokeratlas.com/boxes/live_cash_games?from=main&vid=9872"
CSV_PATH = "parq_traffic.csv"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://www.pokeratlas.com/poker-room/parq-vancouver/cash-games",
}

# 列的顺序 + 用来匹配网页里级别名字的唯一片段。
# 想加/减级别,改这里即可,CSV 表头会自动跟着变。
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


def fetch_html():
    headers = dict(HEADERS)
    cookie = os.getenv("PA_COOKIE")
    if cookie:
        headers["Cookie"] = cookie
    r = requests.get(URL, headers=headers, timeout=20)
    r.raise_for_status()
    return r.text


def parse(html):
    """-> list[(name, tables, waiting)]"""
    soup = BeautifulSoup(html, "html.parser")
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
    """把抓到的牌局按 LEVELS 顺序对齐 -> ([(label, tables, wait), ...], 未匹配的名字列表)"""
    found = {}
    matched = set()
    for name, t, w in games:
        for label, frag in LEVELS:
            if frag.lower() in name.lower():
                found[label] = (t, w)
                matched.add(name)
                break
    ordered = [(label, *found.get(label, (0, 0))) for label, _ in LEVELS]
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


def run_once():
    ts = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-7)))  # 温哥华本地时间
    try:
        html = fetch_html()
    except Exception as e:
        print(f"{ts:%H:%M} fetch 失败: {e}")
        return

    games = parse(html)
    if not games:
        print(f"{ts:%H:%M} 找到 0 个牌局 —— cookie 可能过期,重取一次。")
        return

    ordered, unmatched = match_levels(games)
    log_wide(ts, ordered)

    # 一行简洁汇总(不再重复打印)
    summary = "  ".join(f"{lbl} {t}/{w}" for lbl, t, w in ordered)
    print(f"{ts:%Y-%m-%d %H:%M}  {summary}")
    if unmatched:
        print(f"  ⚠ 出现未识别的级别(没记进对应列): {unmatched} —— 告诉我,我给 LEVELS 加一列。")


def main():
    interval = None
    if "--loop" in sys.argv:
        i = sys.argv.index("--loop")
        interval = int(sys.argv[i + 1]) if i + 1 < len(sys.argv) else 600

    if interval is None:
        run_once()
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
