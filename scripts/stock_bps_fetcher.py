#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
stock_bps_fetcher.py — REQ-172 X6 离线工具

职责：
1. 拉取个股历史 PB/BPS 序列（AKShare stock_value_em，覆盖 2018 至今）
2. 存到 data/stock_bps/<code>.csv（字段：date, close, pb, bps）
3. 聚合成 ETF 加权 PB 历史序列 data/valuation_history/<etf>_pb.csv（字段：date, pb）

触发时机（v1 手动版）：
- 换 ETF 时：python stock_bps_fetcher.py --etf 512400
- 季报后手动刷新：python stock_bps_fetcher.py --all
- 一次性回填所有 ETF 历史：python stock_bps_fetcher.py --all --backfill

v2（REQ-161 周更基建就绪后）：由周/季度自动化接管，但脚本接口保持稳定。

注意：
- 只支持 A 股（sh/sz），港股（hk）不走 stock_value_em
- 513120 港创药 10 股全是港股，由调用方决定降级（跳过或用代理）
- 每次调用股级接口后 sleep 1 秒，避免触发限流
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from logger import Logger  # noqa: E402

logger = Logger(name="stock_bps_fetcher", file_output=False)

SKILL_ROOT = _SCRIPT_DIR.parent
DEFAULT_HOLDINGS_YAML = SKILL_ROOT / "config" / "holdings.yaml"
DEFAULT_STOCK_BPS_DIR = SKILL_ROOT / "data" / "stock_bps"
DEFAULT_VALUATION_HISTORY_DIR = SKILL_ROOT / "data" / "valuation_history"

SLEEP_BETWEEN_STOCKS = 1.0  # 秒，低频抓取，友好访问


# ============================================================
# 配置加载
# ============================================================
def load_holdings(holdings_path: Path = DEFAULT_HOLDINGS_YAML) -> Dict:
    """加载 holdings.yaml，返回 {etf_code: {name, components: [...]}}"""
    with holdings_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("holdings", {})


def get_a_share_components(holdings: Dict, etf_code: str) -> List[Dict]:
    """
    取某 ETF 的 A 股成分（过滤掉港股）。
    返回 [{name, code, market, ratio}, ...]
    """
    cfg = holdings.get(etf_code)
    if cfg is None:
        return []
    components = cfg.get("components") or []
    return [c for c in components if c.get("market") in ("sh", "sz")]


# ============================================================
# 数据源层：AKShare stock_value_em
# ============================================================
def fetch_stock_history(stock_code: str) -> Optional[List[Dict]]:
    """
    拉取个股 PE/PB/BPS 历史序列（基于 AKShare stock_value_em）。
    返回 [{date, close, pb, bps, pe_ttm}, ...] 按日期升序，或 None（接口失败）。

    BPS 反推公式：BPS = close / pb
    （口径：东财 stock_value_em 返回的市净率 = 股价 / 每股合并股东权益）
    """
    try:
        import akshare as ak
    except ImportError:
        logger.error("akshare 未安装，无法拉取", {"stock": stock_code})
        return None

    try:
        df = ak.stock_value_em(symbol=stock_code)
    except Exception as exc:  # noqa: BLE001
        logger.warn("stock_value_em 失败", {
            "stock": stock_code,
            "error": f"{type(exc).__name__}: {str(exc)[:120]}",
        })
        return None

    if df is None or len(df) == 0:
        return None

    records: List[Dict] = []
    for _, row in df.iterrows():
        try:
            pb = float(row.get("市净率") or 0)
            close = float(row.get("当日收盘价") or 0)
            if pb <= 0 or close <= 0:
                continue
            bps = close / pb
            pe = float(row.get("PE(TTM)") or 0) or None
        except (TypeError, ValueError):
            continue

        date_raw = row.get("数据日期")
        date_str = str(date_raw)

        records.append({
            "date": date_str,
            "close": close,
            "pb": pb,
            "bps": bps,
            "pe_ttm": pe,
        })

    # 按日期升序
    records.sort(key=lambda r: r["date"])
    return records


# ============================================================
# 个股 CSV 读写
# ============================================================
def _stock_csv_path(stock_code: str, base_dir: Path) -> Path:
    return base_dir / f"{stock_code}.csv"


def save_stock_history(stock_code: str, records: List[Dict],
                       base_dir: Path = DEFAULT_STOCK_BPS_DIR) -> Path:
    """把个股历史写入 data/stock_bps/<code>.csv（全量覆盖）"""
    base_dir.mkdir(parents=True, exist_ok=True)
    csv_path = _stock_csv_path(stock_code, base_dir)
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["date", "close", "pb", "bps", "pe_ttm"])
        writer.writeheader()
        for rec in records:
            writer.writerow({
                "date": rec["date"],
                "close": f"{rec['close']:.4f}",
                "pb": f"{rec['pb']:.4f}",
                "bps": f"{rec['bps']:.4f}",
                "pe_ttm": f"{rec['pe_ttm']:.4f}" if rec.get("pe_ttm") else "",
            })
    return csv_path


def load_stock_history(stock_code: str,
                       base_dir: Path = DEFAULT_STOCK_BPS_DIR) -> Optional[List[Dict]]:
    """从本地 CSV 加载个股历史，返回 [{date, close, pb, bps, pe_ttm}, ...] 或 None"""
    csv_path = _stock_csv_path(stock_code, base_dir)
    if not csv_path.exists():
        return None
    records: List[Dict] = []
    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                records.append({
                    "date": row["date"],
                    "close": float(row["close"]) if row.get("close") else 0.0,
                    "pb": float(row["pb"]) if row.get("pb") else 0.0,
                    "bps": float(row["bps"]) if row.get("bps") else 0.0,
                    "pe_ttm": float(row["pe_ttm"]) if row.get("pe_ttm") else None,
                })
            except (TypeError, ValueError):
                continue
    return records


def get_latest_bps(stock_code: str,
                   base_dir: Path = DEFAULT_STOCK_BPS_DIR) -> Optional[float]:
    """拿本地个股最新一天的 BPS（给日更价算 PB 用）"""
    records = load_stock_history(stock_code, base_dir)
    if not records:
        return None
    return records[-1]["bps"]


# ============================================================
# ETF 加权 PB 历史回填
# ============================================================
def compute_etf_pb_history(
    etf_code: str,
    components: List[Dict],
    stock_bps_dir: Path = DEFAULT_STOCK_BPS_DIR,
) -> List[Tuple[str, float]]:
    """
    根据各成分股的历史 PB 序列 + 权重，聚合成 ETF 加权 PB 历史。

    算法：取所有成分股都有数据的日期交集，每日按权重加权平均。
    权重：ratio / total_weight（权重归一化到成分股总和）

    返回 [(date, weighted_pb), ...] 按日期升序。
    """
    # 1. 加载所有成分股的历史
    stock_histories: Dict[str, Dict[str, float]] = {}  # {code: {date: pb}}
    valid_components: List[Dict] = []
    for comp in components:
        code = comp["code"]
        records = load_stock_history(code, stock_bps_dir)
        if not records:
            logger.warn("成分股历史缺失，跳过", {"etf": etf_code, "stock": code})
            continue
        stock_histories[code] = {r["date"]: r["pb"] for r in records}
        valid_components.append(comp)

    if not valid_components:
        return []

    # 2. 权重归一化
    total_ratio = sum(c["ratio"] for c in valid_components)
    if total_ratio <= 0:
        return []

    # 3. 日期交集
    date_sets = [set(h.keys()) for h in stock_histories.values()]
    common_dates = sorted(set.intersection(*date_sets))

    # 4. 每日加权
    result: List[Tuple[str, float]] = []
    for d in common_dates:
        weighted_pb = 0.0
        for comp in valid_components:
            pb = stock_histories[comp["code"]].get(d, 0.0)
            weighted_pb += pb * (comp["ratio"] / total_ratio)
        result.append((d, weighted_pb))

    return result


def save_etf_pb_history(
    etf_code: str,
    records: List[Tuple[str, float]],
    base_dir: Path = DEFAULT_VALUATION_HISTORY_DIR,
) -> Path:
    """
    把 ETF 加权 PB 历史写入 data/valuation_history/<etf>_pb.csv。
    字段：date, pb
    """
    base_dir.mkdir(parents=True, exist_ok=True)
    csv_path = base_dir / f"{etf_code}_pb.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "pb"])
        for d, pb in records:
            writer.writerow([d, f"{pb:.4f}"])
    return csv_path


def compute_etf_pb_today(
    components: List[Dict],
    today_closes: Dict[str, float],
    stock_bps_dir: Path = DEFAULT_STOCK_BPS_DIR,
) -> Optional[float]:
    """
    日更入口：ETF 当日加权 PB = sum(ratio * close_today / 最近一期BPS) / total_ratio

    参数：
      components - holdings 的 A 股成分列表
      today_closes - {stock_code: close_today} 当日收盘价（由调用方从 K 线提供）
      stock_bps_dir - 本地 BPS 目录

    返回加权 PB（或 None 如果所有成分股都拿不到）。
    """
    total_ratio = 0.0
    weighted_sum = 0.0
    for comp in components:
        code = comp["code"]
        ratio = comp["ratio"]
        bps = get_latest_bps(code, stock_bps_dir)
        close = today_closes.get(code)
        if bps is None or close is None or bps <= 0:
            continue
        pb = close / bps
        weighted_sum += pb * ratio
        total_ratio += ratio

    if total_ratio <= 0:
        return None
    return weighted_sum / total_ratio


# ============================================================
# 主流程
# ============================================================
def fetch_etf_stocks(etf_code: str, holdings: Dict,
                     stock_bps_dir: Path = DEFAULT_STOCK_BPS_DIR,
                     skip_existing: bool = False) -> Tuple[int, int]:
    """
    拉取某 ETF 所有 A 股成分的历史 BPS/PB，写入本地 CSV。

    参数：
      skip_existing - True 则已有本地 CSV 的跳过（增量模式）

    返回 (成功数, 失败数)
    """
    components = get_a_share_components(holdings, etf_code)
    if not components:
        logger.warn("ETF 无 A 股成分，跳过", {"etf": etf_code})
        return (0, 0)

    logger.info("开始拉取 ETF 成分股", {
        "etf": etf_code,
        "a_share_count": len(components),
        "skip_existing": skip_existing,
    })

    ok, fail = 0, 0
    for i, comp in enumerate(components):
        code = comp["code"]
        csv_path = _stock_csv_path(code, stock_bps_dir)
        if skip_existing and csv_path.exists():
            logger.info("已存在，跳过", {"stock": code})
            ok += 1
            continue

        records = fetch_stock_history(code)
        if records is None or not records:
            logger.warn("股票拉取失败", {"stock": code, "name": comp.get("name")})
            fail += 1
            time.sleep(SLEEP_BETWEEN_STOCKS)
            continue
        save_stock_history(code, records, stock_bps_dir)
        logger.info("股票拉取完成", {
            "stock": code,
            "name": comp.get("name"),
            "rows": len(records),
            "latest_pb": records[-1]["pb"],
            "latest_bps": records[-1]["bps"],
        })
        ok += 1
        # 最后一支不 sleep
        if i < len(components) - 1:
            time.sleep(SLEEP_BETWEEN_STOCKS)

    return (ok, fail)


def backfill_etf_history(etf_code: str, holdings: Dict,
                         stock_bps_dir: Path = DEFAULT_STOCK_BPS_DIR,
                         history_dir: Path = DEFAULT_VALUATION_HISTORY_DIR) -> Optional[Path]:
    """聚合成分股历史 → ETF 加权 PB 历史 CSV"""
    components = get_a_share_components(holdings, etf_code)
    if not components:
        logger.warn("ETF 无 A 股成分，跳过回填", {"etf": etf_code})
        return None

    etf_history = compute_etf_pb_history(etf_code, components, stock_bps_dir)
    if not etf_history:
        logger.warn("ETF 加权 PB 历史为空", {"etf": etf_code})
        return None

    csv_path = save_etf_pb_history(etf_code, etf_history, history_dir)
    logger.info("ETF PB 历史回填完成", {
        "etf": etf_code,
        "rows": len(etf_history),
        "date_range": f"{etf_history[0][0]} ~ {etf_history[-1][0]}",
        "latest_pb": etf_history[-1][1],
        "path": str(csv_path.name),
    })
    return csv_path


# ============================================================
# CLI
# ============================================================
def _cli_main() -> int:  # pragma: no cover
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="REQ-172 X6：ETF 成分股 PB/BPS 历史拉取 + 加权回填"
    )
    parser.add_argument("--etf", type=str, default=None, help="指定 ETF 代码（如 512400）")
    parser.add_argument("--all", action="store_true", help="处理 holdings.yaml 里全部 ETF")
    parser.add_argument("--backfill", action="store_true",
                        help="拉取完成后聚合 ETF 加权 PB 历史")
    parser.add_argument("--skip-existing", action="store_true",
                        help="跳过已有本地 CSV 的股票（增量模式）")
    parser.add_argument("--only-backfill", action="store_true",
                        help="只做聚合，不拉取（假设个股 CSV 已就绪）")
    args = parser.parse_args()

    holdings = load_holdings()
    all_etfs = list(holdings.keys())

    if args.etf:
        targets = [args.etf]
    elif args.all:
        targets = all_etfs
    else:
        parser.error("请指定 --etf <CODE> 或 --all")
        return 2

    print(f"目标 ETF: {targets}")
    print(f"skip_existing={args.skip_existing}, backfill={args.backfill}, only_backfill={args.only_backfill}")
    print("=" * 60)

    total_ok, total_fail = 0, 0
    for etf in targets:
        if etf not in holdings:
            print(f"[SKIP] {etf} 不在 holdings.yaml")
            continue

        print(f"\n>>> {etf} {holdings[etf].get('name', '')}")

        if not args.only_backfill:
            ok, fail = fetch_etf_stocks(etf, holdings,
                                        skip_existing=args.skip_existing)
            total_ok += ok
            total_fail += fail
            print(f"    成分股拉取：OK={ok}, FAIL={fail}")

        if args.backfill or args.only_backfill:
            csv_path = backfill_etf_history(etf, holdings)
            if csv_path:
                print(f"    ETF PB 历史：{csv_path.name}")

    print("\n" + "=" * 60)
    print(f"总计：OK={total_ok}, FAIL={total_fail}")
    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(_cli_main())
