"""
monitor.py  —  抓多个场馆的实时牌局,写入宽表 CSV,并自动更新 chart.html。

场馆:
  Parq (Vancouver)   vid=9872
  Wynn (Las Vegas)   vid=9550
  Hustler (LA)       vid=9016

用法:
  本地循环:  python monitor.py --loop 600
  云端单次:  python monitor.py

环境变量:
  PA_COOKIE  登录后的整段 Cookie
"""

import csv, os, re, sys, time, datetime, subprocess
import requests
from bs4 import BeautifulSoup

CSV_PATH = "parq_traffic.csv"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "X-Requested-With": "XMLHttpRequest",
}

# 每个场馆的配置：(CSV列前缀, vid, Referer, NLH档位列表)
# 档位列表：(列名后缀, 匹配关键词)  —— 只保留 NLH
VENUES = [
    {
        "prefix":  "parq",
        "vid":     9872,
        "referer": "https://www.pokeratlas.com/poker-room/parq-vancouver/cash-games",
        "levels": [
            ("1/3",    "1 - $3 NLH"),
            ("1/3/6",  "1-$3-$6"),
            ("2/5/10", "2-$5-$10"),
        ],
    },
    {
        "prefix":  "wynn",
        "vid":     9550,
        "referer": "https://www.pokeratlas.com/poker-room/wynn-las-vegas/cash-games",
        "levels": [
            ("1/3",   "1/3 NL"),
            ("2/5",   "2/5 NL"),
            ("5/10",  "5/10 NL"),
            ("10/20", "10/20 NL"),
            ("20/40", "20/40 NL"),
        ],
    },
    {
        "prefix":  "hustler",
        "vid":     9016,
        "referer": "https://www.pokeratlas.com/poker-room/hustler-casino-gardena/cash-games",
        "levels": [
            ("1/3",     "NL $1/$3"),
            ("2/3",     "NL $2/$3"),
            ("2/5",     "NL $2/$5"),
            ("5/5",     "NL $5/$5"),
            ("5/5/10",  "NL $5/$5/$10"),
            ("10/20",   "NL $10/$20"),
        ],
    },
]


def _to_int(s):
    m = re.search(r"\d+", s or "")
    return int(m.group()) if m else 0


def fetch_html(vid, referer, retries=3, delay=5):
    url = f"https://www.pokeratlas.com/boxes/live_cash_games?from=main&vid={vid}"
    headers = dict(HEADERS)
    headers["Referer"] = referer
    cookie = os.getenv("PA_COOKIE")
    if cookie:
        headers["Cookie"] = cookie
    last_err = None
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=headers, timeout=20)
            r.raise_for_status()
            return r.text
        except Exception as e:
            last_err = e
            if attempt < retries - 1:
                time.sleep(delay)
    raise last_err


def parse(html):
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


def match_levels(games, levels):
    """返回 [(后缀, tables), ...]，顺序与 levels 一致。"""
    found = {}
    for name, t, _w in games:
        for suffix, frag in levels:
            if frag.lower() in name.lower():
                found[suffix] = t
                break
    return [(suffix, found.get(suffix, 0)) for suffix, _ in levels]


def csv_header():
    h = ["time", "weekday", "hour"]
    for v in VENUES:
        for suffix, _ in v["levels"]:
            h.append(f"{v['prefix']}_{suffix}")
    return h


def log_wide(ts, all_results):
    """all_results: [(prefix, [(suffix, tables), ...]), ...]"""
    new = not os.path.exists(CSV_PATH)
    with open(CSV_PATH, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(csv_header())
        row = [ts.isoformat(timespec="minutes"), ts.strftime("%a"), ts.hour]
        for _prefix, matched in all_results:
            for _suffix, t in matched:
                row.append(t)
        w.writerow(row)


def update_chart():
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
    all_results = []
    any_ok = False

    for v in VENUES:
        prefix = v["prefix"]
        try:
            html = fetch_html(v["vid"], v["referer"])
            games = parse(html)
            if not games:
                print(f"  [{prefix}] 0 个牌局 —— cookie 可能过期")
                matched = [(suffix, 0) for suffix, _ in v["levels"]]
            else:
                matched = match_levels(games, v["levels"])
                any_ok = True
        except Exception as e:
            print(f"  [{prefix}] 抓取失败: {e}")
            matched = [(suffix, 0) for suffix, _ in v["levels"]]
        all_results.append((prefix, matched))

    log_wide(ts, all_results)
    update_chart()

    # 打印汇总
    print(f"{ts:%Y-%m-%d %H:%M}")
    for prefix, matched in all_results:
        summary = "  ".join(f"{s}:{t}" for s, t in matched if t > 0)
        print(f"  [{prefix}] {summary or '(无开桌)'}")

    return any_ok


def main():
    interval = None
    if "--loop" in sys.argv:
        i = sys.argv.index("--loop")
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
