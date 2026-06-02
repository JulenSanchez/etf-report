#!/usr/bin/env python3
"""Pre-close push: fetch intraday, run backtest via Tuner API, push top-10 to WeChat via ServerChan."""
import sys, os, time, requests, yaml
from datetime import datetime, timedelta

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SKILL_DIR, "scripts"))
from trading_calendar import is_trading_day

TUNER_URL = "http://localhost:5179"
DEFAULT_PRESET = "preset3"

# ── Trading day check ──
if not is_trading_day():
    print("[SKIP] Not a trading day")
    sys.exit(0)

# ── Secrets ──
with open(os.path.join(SKILL_DIR, "config", "secrets.yaml"), "r", encoding="utf-8") as f:
    sec = yaml.safe_load(f) or {}
sendkey = sec.get("publish", {}).get("serverchan", {}).get("sendkey", "")
if not sendkey:
    print("[ERROR] ServerChan sendkey not configured"); sys.exit(1)

# ── ETF names ──
with open(os.path.join(SKILL_DIR, "config", "quant_universe.yaml"), "r", encoding="utf-8") as f:
    cfg = yaml.safe_load(f)
etf_names = {e["code"]: e.get("name", e["code"]) for e in cfg.get("universe", [])}
qdii_codes = {e["code"] for e in cfg.get("universe", []) if e.get("qdii")}

def short(code):
    return etf_names.get(code, code).replace("ETF", "")

# ── Tuner ──
now = datetime.now()
print(f"[{now:%H:%M:%S}] Tuner check...")
try:
    r = requests.get(f"{TUNER_URL}/api/data_status", timeout=5)
    if r.status_code != 200:
        print("[ERROR] Tuner not ready"); sys.exit(1)
except Exception as e:
    print(f"[ERROR] Tuner unreachable: {e}"); sys.exit(1)

# ── Refresh ──
print(f"[{datetime.now():%H:%M:%S}] Refresh...")
r = requests.post(f"{TUNER_URL}/api/refresh_data", timeout=60)
print(f"  {r.json().get('status', '?')}")

print(f"[{datetime.now():%H:%M:%S}] Wait 10s...")
time.sleep(10)

# ── Params (start fixed to May 1) ──
r = requests.get(f"{TUNER_URL}/api/presets", timeout=10)
p = r.json()[DEFAULT_PRESET]
end = now.strftime("%Y-%m-%d")
start = f"{now.year}-05-01"

params = {
    "w1": p.get("w1", 50), "w3": p.get("w3", 30), "w7": p.get("w7", 20),
    "conf_type": "ma_trend", "ma_trend_period": p.get("ma_trend_period", 26),
    "ma_bull_pos": p.get("ma_bull_pos", 1.0), "ma_bear_pos": p.get("ma_bear_pos", 0.3),
    "ma_direction_confirm": True, "max_holdings": p.get("max_holdings", 6),
    "disc_step": p.get("disc_step", 0.05), "concentration": p.get("concentration", 0.5),
    "c_sensitivity": p.get("c_sensitivity", 0.0), "rebalance_freq": "daily",
    "execution_timing": "same_close", "score_band": p.get("score_band", 3),
    "f1_sensitivity": p.get("f1_sensitivity", 8.0), "f3_sensitivity": p.get("f3_sensitivity", 1.0),
    "f7_t": p.get("f7_t", 15.0), "f7_k": p.get("f7_k", 3.5), "f7_window": p.get("f7_window", 20),
    "ema_period": p.get("ema_period", 5), "vol_window": p.get("vol_window", 20),
    "start_date": start, "end_date": end, "universe": "", "debug": False,
}

# ── Backtest ──
print(f"[{datetime.now():%H:%M:%S}] Backtest ({start}~{end})...")
r = requests.post(f"{TUNER_URL}/api/run", json=params, timeout=180)
result = r.json()
if "error" in result:
    print(f"[ERROR] {result['error']}"); sys.exit(1)

# ── Top-10 + actions ──
history = result["signalHistory"]
latest = history[-1]
detail = latest.get("detail", {})
positions = latest.get("positions", {})

# Previous positions for action delta
prev_positions = history[-2].get("positions", {}) if len(history) >= 2 else {}

rows = []
for c, d in detail.items():
    score = d.get("score", 0)
    pos = positions.get(c, 0) * 100
    prev = prev_positions.get(c, 0) * 100
    if pos < 0.5 and prev < 0.5:
        action = ""
    elif pos > 0.5 and prev < 0.5:
        action = "NEW"
    elif pos < 0.5 and prev > 0.5:
        action = "OUT"
    elif pos > prev + 0.5:
        action = f"+{(pos-prev):.1f}%"
    elif pos < prev - 0.5:
        action = f"-{(prev-pos):.1f}%"
    else:
        action = ""
    rows.append((c, score, pos, action))

rows.sort(key=lambda x: -x[1])
top10 = rows[:10]

# ── Build Markdown table ──
now = datetime.now()
session = "上午" if now.hour < 13 else "下午"
# Check for halted QDII ETFs
halted_codes = []
try:
    r_status = requests.get(f"{TUNER_URL}/api/data_status", timeout=5)
    if r_status.status_code == 200:
        halted_codes = r_status.json().get("haltedEtfs", [])
except Exception:
    pass

halt_note = ""
if halted_codes:
    names = [short(c) for c in halted_codes]
    halt_note = f" | ⚠️停牌: {', '.join(names)}"

md_lines = [
    f"策略: 赌徒  |  {now:%H:%M}{halt_note}",
    "",
    "| # | ETF | 得分 | 仓位 | 动作 |",
    "|---|-----|------|------|------|",
]
for i, (c, s, pct, act) in enumerate(top10, 1):
    ps = f"**{pct:.0f}%**" if pct > 0 else "-"
    md_lines.append(f"| {i} | {short(c)} | {s:.1f} | {ps} | {act} |")

content = "\n".join(md_lines)

title = f"{now:%m/%d} {session}收盘前 | 赌徒{halt_note}"
print(title)
print(content)

# ── Push ──
r = requests.post(f"https://sctapi.ftqq.com/{sendkey}.send",
                  data={"title": title, "desp": content}, timeout=10)
resp = r.json()
if resp.get("code") == 0:
    pushid = resp.get("data", {}).get("pushid", "?")
    print(f"\n[OK] Push sent (id={pushid})")
else:
    print(f"\n[ERROR] {resp}"); sys.exit(1)
