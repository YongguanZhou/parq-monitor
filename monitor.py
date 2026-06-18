"""
monitor.py  —  抓多个场馆的实时牌局,写入宽表 CSV,并自动更新 chart.html。

场馆:
  Parq (Vancouver)   vid=9872   —— 沿用原有列名,结构不变
  Wynn (Las Vegas)   vid=9550
  Hustler (LA)       vid=9016

CSV 列结构(35列,与历史数据兼容):
  原 13 列(Parq 三档 + PLO + High Hand,各 tables/wait)保持不变,
  之后追加 Wynn(5档) 和 Hustler(6档),每档 tables + wait。

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

# ---- Parq:沿用原有列名(顺序与历史 CSV 完全一致),保留 PLO / High Hand ----
PARQ_LEVELS = [
    ("1/3 NLH",    "1 - $3 NLH"),
    ("1/3/6 NLH",  "1-$3-$6"),
    ("2/5/10 NLH", "2-$5-$10"),
    ("2/5 PLO",    "PLO"),
    ("High Hand",  "High Hand"),
]

# ---- 新场馆:列名前缀 + NLH 档位(匹配关键词) ----
WYNN_LEVELS = [
    ("wynn_1/3",   "1/3 NL"),
    ("wynn_2/5",   "2/5 NL"),
    ("wynn_5/10",  "5/10 NL"),
    ("wynn_10/20", "10/20 NL"),
    ("wynn_20/40", "20/40 NL"),
]
HUSTLER_LEVELS = [
    ("hustler_1/3",    "NL $1/$3"),
    ("hustler_2/3",    "NL $2/$3"),
    ("hustler_2/5",    "NL $2/$5"),
    ("hustler_5/5",    "NL $5/$5"),
    ("hustler_5/5/10", "NL $5/$5/$10"),
    ("hustler_10/20",  "NL $10/$20"),
]

# 场馆配置：(vid, referer, levels)
VENUES = [
    (9872, "https://www.pokeratlas.com/poker-room/parq-vancouver/cash-games",        PARQ_LEVELS),
    (9550, "https://www.pokeratlas.com/poker-room/wynn-las-vegas/cash-games",         WYNN_LEVELS),
    (9016, "https://www.pokeratlas.com/poker-room/hustler-casino-gardena/cash-games", HUSTLER_LEVELS),
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
    """返回 [(label, tables, wait), ...]，顺序与 levels 一致；缺的填 0。"""
    found = {}
    for name, t, w in games:
        for label, frag in levels:
            if frag.lower() in name.lower():
                found[label] = (t, w)
                break
    return [(label, *found.get(label, (0, 0))) for label, _ in levels]


def csv_header():
    h = ["time", "weekday", "hour"]
    for _vid, _ref, levels in VENUES:
        for label, _ in levels:
            h += [f"{label} tables", f"{label} wait"]
    return h


def log_wide(ts, all_results):
    """all_results: [[(label, t, w), ...], ...]  顺序同 VENUES"""
    new = not os.path.exists(CSV_PATH)
    with open(CSV_PATH, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(csv_header())
        row = [ts.isoformat(timespec="minutes"), ts.strftime("%a"), ts.hour]
        for matched in all_results:
            for _label, t, wait in matched:
                row += [t, wait]
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

    for vid, referer, levels in VENUES:
        try:
            html  = fetch_html(vid, referer)
            games = parse(html)
            if not games:
                print(f"  [vid={vid}] 0 个牌局 —— cookie 可能过期")
                matched = [(label, 0, 0) for label, _ in levels]
            else:
                matched = match_levels(games, levels)
                any_ok = True
        except Exception as e:
            print(f"  [vid={vid}] 抓取失败: {e}")
            matched = [(label, 0, 0) for label, _ in levels]
        all_results.append(matched)

    log_wide(ts, all_results)
    update_chart()

    print(f"{ts:%Y-%m-%d %H:%M}")
    names = ["parq", "wynn", "hustler"]
    for nm, matched in zip(names, all_results):
        summary = "  ".join(f"{lbl}:{t}" for lbl, t, _w in matched if t > 0)
        print(f"  [{nm}] {summary or '(无开桌)'}")

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
