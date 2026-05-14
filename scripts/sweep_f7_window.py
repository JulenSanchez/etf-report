#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
F7 参数扫描 — Step 1：f7_window 单因子扫描
其他参数固定：f7_t=7, f7_k=3.0, w7=0.15
"""
import subprocess, json, csv, time
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent  # .codebuddy/skills/etf-report
CONFIG = SKILL_DIR / "config" / "quant_universe.yaml"
BACKTEST = SKILL_DIR / "scripts" / "quant_backtest.py"
RESULTS = SKILL_DIR / "research" / "F7-optimization" / "03_f7window_sweep.csv"

def run_backtest(f7_window, f7_t=7, f7_k=3.0, w7=0.15):
    """通过临时修改 YAML 跑回测，返回结果 dict"""
    # 读 YAML
    import yaml
    with CONFIG.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    # 修改 daily_aggressive preset
    p = cfg["presets"]["daily_aggressive"]
    p["scoring"]["weights"]["log_return_deviation"] = w7
    p["scoring"]["sensitivity"]["f7_t"] = float(f7_t)
    p["scoring"]["sensitivity"]["f7_k"] = float(f7_k)
    p["factors"]["log_return_deviation"]["window_days"] = int(f7_window)
    # 写临时 YAML
    with CONFIG.open("w", encoding="utf-8") as f:
        yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    # 跑回测
    nav_out = SKILL_DIR / "research" / "F7-optimization" / f"nav_f7w{f7_window}.csv"
    cmd = [
        "python", "-u", str(BACKTEST),
        "--preset", "daily_aggressive",
        "--start", "2023-01-01",
        "--output", str(nav_out)
    ]
    # 写专用 log 文件，避免 capture_output 管道死锁
    log_path = SKILL_DIR / "research" / "F7-optimization" / f"nav_f7w{f7_window}_log.txt"
    with open(log_path, "w", encoding="utf-8") as lf:
        result = subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT, text=True, timeout=600)
    # 复制 NAV 副本到 research 目录（带参数后缀，方便后续对比）
    import shutil
    copy_dst = SKILL_DIR / "research" / "F7-optimization" / f"nav_f7w{f7_window}_bak.csv"
    if nav_out.exists():
        shutil.copy2(nav_out, copy_dst)
    # 从 log 文件中提取指标（避免管道死锁）
    log_path = SKILL_DIR / "research" / "F7-optimization" / f"nav_f7w{f7_window}_log.txt"
    if not log_path.exists():
        log_path = nav_out  # fallback：从 NAV CSV 附近找同名 log
    try:
        with open(log_path, "r", encoding="utf-8") as lf:
            output = lf.read()
    except Exception:
        output = result.stdout if hasattr(result, 'stdout') else ""
    metrics = {}
    for line in output.splitlines():
        if "总收益率:" in line: metrics["total_return"] = float(line.split(":")[1].strip().rstrip("%"))
        elif "年化收益率:" in line: metrics["annual_return"] = float(line.split(":")[1].strip().rstrip("%"))
        elif "最大回撤:" in line: metrics["max_drawdown"] = float(line.split(":")[1].strip().rstrip("%"))
        elif "夏普比率:" in line: metrics["sharpe"] = float(line.split(":")[1].strip())
        elif "索提诺比率:" in line: metrics["sortino"] = float(line.split(":")[1].strip())
    return metrics
    metrics = {}
    for line in result.stdout.splitlines():
        if "总收益率:" in line: metrics["total_return"] = float(line.split(":")[1].strip().rstrip("%"))
        elif "年化收益率:" in line: metrics["annual_return"] = float(line.split(":")[1].strip().rstrip("%"))
        elif "最大回撤:" in line: metrics["max_drawdown"] = float(line.split(":")[1].strip().rstrip("%"))
        elif "夏普比率:" in line: metrics["sharpe"] = float(line.split(":")[1].strip())
        elif "索提诺比率:" in line: metrics["sortino"] = float(line.split(":")[1].strip())
    return metrics

def main():
    windows = [5, 10, 15, 20]
    rows = []
    for w in windows:
        print(f"\n{'='*50}")
        print(f"Scanning f7_window = {w}")
        print(f"{'='*50}")
        t0 = time.time()
        m = run_backtest(f7_window=w)
        t1 = time.time()
        print(f"  Done in {t1-t0:.0f}s: {m}")
        rows.append({"f7_window": w, **m})
    # 保存 CSV
    if rows:
        with open(RESULTS, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        print(f"\nResults saved: {RESULTS}")
    # 打印对比
    print(f"\n{'='*60}")
    print(f"{'f7_window':<12} {'总收益':<12} {'年化':<10} {'最大回撤':<12} {'Sharpe':<8} {'Sortino':<8}")
    print("-" * 60)
    for r in rows:
        print(f"{r['f7_window']:<12} {r.get('total_return','?'):<12} {r.get('annual_return','?'):<10} {r.get('max_drawdown','?'):<12} {r.get('sharpe','?'):<8} {r.get('sortino','?'):<8}")

if __name__ == "__main__":
    main()
