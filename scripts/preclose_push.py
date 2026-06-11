#!/usr/bin/env python3
"""Pre-close push: auto-start Tuner → refresh intraday → backtest → push top-10 to WeChat via Server酱."""
import sys, os, time, subprocess, requests, yaml
from datetime import datetime

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(SKILL_DIR, "scripts"))
from trading_calendar import is_trading_day

TUNER_URL = "http://localhost:5179"
DEFAULT_PRESET = "preset3"
TUNER_STARTUP_TIMEOUT = 60  # max seconds to wait for Tuner

def log(msg):
    """Timestamped console output."""
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)

def _tuner_ready():
    """Check if Tuner is responding AND fully loaded (presets available)."""
    try:
        r = requests.get(f"{TUNER_URL}/api/presets", timeout=5)
        if r.status_code != 200:
            return False
        data = r.json()
        # Real presets (not _universe_options) must be present
        presets = [k for k in data.keys() if not k.startswith("_")]
        return len(presets) > 0
    except Exception:
        return False

def _ensure_tuner():
    """Ensure Tuner is running. Start it if not, wait for readiness."""
    if _tuner_ready():
        log("Tuner: already running")
        return True

    log("Tuner: not running — starting...")
    tuner_script = os.path.join(SKILL_DIR, "scripts", "quant_tuner.py")
    subprocess.Popen(
        ["python", tuner_script],
        cwd=SKILL_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )

    # Wait for Tuner to become ready
    waited = 0
    while waited < TUNER_STARTUP_TIMEOUT:
        time.sleep(2)
        waited += 2
        if _tuner_ready():
            log(f"Tuner: ready after {waited}s")
            return True
        if waited % 10 == 0:
            log(f"Tuner: waiting... ({waited}s)")

    log("ERROR: Tuner failed to start within 60s")
    return False

# ═══════════════════════════════════════════════════════════════
# Stage 0: Pre-flight checks
# ═══════════════════════════════════════════════════════════════
log("=" * 50)
log("Stage 0: Pre-flight checks")
now = datetime.now()

if not is_trading_day():
    log("SKIP: Not a trading day")
    sys.exit(0)
log(f"Trading day: YES ({now:%Y-%m-%d})")

with open(os.path.join(SKILL_DIR, "config", "secrets.yaml"), "r", encoding="utf-8") as f:
    sec = yaml.safe_load(f) or {}
sendkey = sec.get("publish", {}).get("serverchan", {}).get("sendkey", "")
if not sendkey:
    log("ERROR: Server酱 sendkey not configured in secrets.yaml")
    sys.exit(1)
log("Server酱 sendkey: configured")

# ═══════════════════════════════════════════════════════════════
# Stage 1: Ensure Tuner is running
# ═══════════════════════════════════════════════════════════════
log("=" * 50)
log("Stage 1: Ensure Tuner")
if not _ensure_tuner():
    sys.exit(1)

# ═══════════════════════════════════════════════════════════════
# Stage 2: Refresh intraday data
# ═══════════════════════════════════════════════════════════════
log("=" * 50)
log("Stage 2: Refresh intraday data")

r = requests.post(f"{TUNER_URL}/api/refresh_data", timeout=60)
status = r.json()
log(f"  Status: {status.get('status', '?')} | {status.get('count', 0)} ETFs")
halted = status.get("haltedCount", 0)
if halted:
    log(f"  Halted ETFs detected: {halted}")

# ═══════════════════════════════════════════════════════════════
# Stage 3: Load preset + build params
# ═══════════════════════════════════════════════════════════════
log("=" * 50)
log("Stage 3: Load preset params")

# ETF name map for display
with open(os.path.join(SKILL_DIR, "config", "quant_universe.yaml"), "r", encoding="utf-8") as f:
    cfg = yaml.safe_load(f)
etf_names = {e["code"]: e.get("name", e["code"]) for e in cfg.get("universe", [])}
qdii_codes = {e["code"] for e in cfg.get("universe", []) if e.get("qdii")}

def short(code):
    return etf_names.get(code, code).replace("ETF", "")

r = requests.get(f"{TUNER_URL}/api/presets", timeout=10)
presets = r.json()
available = [k for k in presets.keys() if not k.startswith("_")]
if DEFAULT_PRESET not in presets:
    log(f"ERROR: preset '{DEFAULT_PRESET}' not found in Tuner response")
    log(f"  Available presets: {available}")
    log(f"  Falling back to first available: {available[0] if available else 'NONE'}")
    if not available:
        log("FATAL: No presets available from Tuner")
        sys.exit(1)
    p = presets[available[0]]
else:
    p = presets[DEFAULT_PRESET]
end = now.strftime("%Y-%m-%d")
start = f"{now.year}-05-01"
log(f"  Preset: {DEFAULT_PRESET} | Window: {start} ~ {end}")

# Start from the full preset params (contract layer provides correct units + all keys).
# Only override fields that preclose specifically needs to change.
params = {k: v for k, v in p.items() if not k.startswith("_")}
params.update({
    "start_date": start,
    "end_date": end,
    "universe": "",
    "debug": False,
})

# ═══════════════════════════════════════════════════════════════
# Stage 4: Run backtest
# ═══════════════════════════════════════════════════════════════
log("=" * 50)
log("Stage 4: Run backtest")
log(f"  {start} ~ {end} ({DEFAULT_PRESET})")

r = requests.post(f"{TUNER_URL}/api/run", json=params, timeout=180)
result = r.json()
if "error" in result:
    log(f"ERROR: {result['error']}")
    sys.exit(1)

s = result["summary"]
log(f"  Total: {s['totalReturn']:+.1f}% | Annual: {s['annualReturn']:+.1f}% | Sharpe: {s['sharpe']:.2f}")
log(f"  WinRate: {s['winRate']}% | MDD: {s['maxDrawdown']:.1f}% | Elapsed: {s['elapsed']}s")

# ═══════════════════════════════════════════════════════════════
# Stage 5: Build signal table
# ═══════════════════════════════════════════════════════════════
log("=" * 50)
log("Stage 5: Build signal table")

history = result["signalHistory"]
latest = history[-1]
detail = latest.get("detail", {})
positions = latest.get("positions", {})
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

# ═══════════════════════════════════════════════════════════════
# Stage 6: Push to WeChat
# ═══════════════════════════════════════════════════════════════
log("=" * 50)
log("Stage 6: Push to WeChat")

now = datetime.now()
session = "上午" if now.hour < 13 else "下午"

# Halt check
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
    halt_note = f" | 停牌: {', '.join(names)}"

md_lines = [
    f"策略: 赌徒  |  {now:%H:%M}{halt_note}",
    "",
    "| # | ETF | 得分 | 仓位 | 动作 |",
    "|---|-----|------|------|------|",
]
for i, (c, s, pct, act) in enumerate(top10, 1):
    ps = f"**{pct:.0f}%**" if pct > 0 else "-"
    md_lines.append(f"| {i} | {short(c)} | {s:.1f} | {ps} | {act} |")

content_str = "\n".join(md_lines)
title = f"{now:%m/%d} {session}收盘前 | 赌徒{halt_note}"

print(title)
print(content_str)

r = requests.post(f"https://sctapi.ftqq.com/{sendkey}.send",
                  data={"title": title, "desp": content_str}, timeout=10)
resp = r.json()
if resp.get("code") == 0:
    pushid = resp.get("data", {}).get("pushid", "?")
    log(f"Push sent OK (id={pushid})")
else:
    log(f"ERROR: Push failed — {resp}")
    sys.exit(1)

log("=" * 50)
log("Done.")
