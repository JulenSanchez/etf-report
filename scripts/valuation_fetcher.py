#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
估值数据拉取 + HTML DOM 注入 (REQ-170 Step 4)

职责：
1. 从 csindex 拉取 4 支 ETF 跟踪指数的当期 PE（有覆盖的）
2. 调用 valuation_engine 计算百分位 + 判词 + 置信度
3. 把结果注入 index.html 对应的 valuation-block DOM 节点
4. 顺带把拉到的 PE/PB 追加到 data/valuation_history/<etf>.csv（为方法 B' 未来演化储粮）

路线 γ：页面只展百分位 + 判词 + 角标，不展 PE/PB 原始数字。
完整方法论见 docs/VALUATION_METHODOLOGY.md

使用方式：
    # 作为模块被 update_report 调用
    from valuation_fetcher import run_valuation_update
    run_valuation_update(html_file="index.html")

    # 独立 CLI 调试
    python scripts/valuation_fetcher.py
"""

from __future__ import annotations

import csv
import re
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# 本脚本所在目录加入 sys.path，便于 logger / valuation_engine 相对导入
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from logger import Logger  # noqa: E402
from valuation_engine import ValuationEngine  # noqa: E402
from etf_pb_calculator import get_etf_current_pb  # noqa: E402
from etf_pb_calculator import get_etf_current_pb  # noqa: E402

logger = Logger(name="valuation_fetcher", file_output=False)

SKILL_ROOT = _SCRIPT_DIR.parent
DEFAULT_HTML_FILE = SKILL_ROOT / "index.html"
DEFAULT_HISTORY_DIR = SKILL_ROOT / "data" / "valuation_history"


# ============================================================
# 数据源层：csindex 拉取
# ============================================================
def fetch_csindex_current_pe(index_code: str) -> Optional[Dict[str, float]]:
    """
    从 AkShare csindex 接口拉取指数当前 PE/股息率。
    返回 {"date": "YYYY-MM-DD", "pe_ttm": float, "dividend_yield": float} 或 None。

    注：AkShare 该接口只返回最近 20 个交易日，取最新一条。
    """
    try:
        import akshare as ak
    except ImportError:
        logger.warn("akshare 未安装，跳过 csindex 拉取", {"index_code": index_code})
        return None

    try:
        df = ak.stock_zh_index_value_csindex(symbol=index_code)
    except Exception as exc:  # noqa: BLE001
        logger.warn("csindex 接口失败", {
            "index_code": index_code,
            "error": f"{type(exc).__name__}: {str(exc)[:120]}",
        })
        return None

    if df is None or len(df) == 0:
        return None

    latest = df.iloc[0]
    try:
        pe = float(latest.get("市盈率1", 0) or 0)
    except (TypeError, ValueError):
        pe = 0.0

    if pe <= 0:
        return None

    latest_date_raw = latest.get("日期")
    if isinstance(latest_date_raw, (date, datetime)):
        date_str = latest_date_raw.strftime("%Y-%m-%d")
    else:
        date_str = str(latest_date_raw)

    try:
        dy = float(latest.get("股息率1", 0) or 0)
    except (TypeError, ValueError):
        dy = 0.0

    return {
        "date": date_str,
        "pe_ttm": pe,
        "dividend_yield": dy,
    }


# ============================================================
# 历史序列增量累积（方法 B' 演化用）
# ============================================================
def append_history_row(
    etf_code: str,
    date_str: str,
    pe_ttm: Optional[float],
    pb: Optional[float],
    history_dir: Path = DEFAULT_HISTORY_DIR,
) -> None:
    """
    把一条观测值追加到 data/valuation_history/<etf>.csv，按日期去重。
    CSV 固定列：date, pe_ttm, pb
    """
    history_dir.mkdir(parents=True, exist_ok=True)
    csv_path = history_dir / f"{etf_code}.csv"

    existing_dates: set[str] = set()
    if csv_path.exists():
        with csv_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                existing_dates.add(row.get("date", ""))

    if date_str in existing_dates:
        return  # 已有该日期数据，跳过

    is_new_file = not csv_path.exists()
    with csv_path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        if is_new_file:
            writer.writerow(["date", "pe_ttm", "pb"])
        writer.writerow([
            date_str,
            f"{pe_ttm:.4f}" if pe_ttm is not None else "",
            f"{pb:.4f}" if pb is not None else "",
        ])


# ============================================================
# 评估流程：对全部已配置 ETF 跑一次（REQ-178: 6 → 18 支）
# ============================================================
def evaluate_all_etfs(engine: ValuationEngine) -> Dict[str, Dict]:
    """
    拉取 csindex 数据（仅对有 tracking_index_code 的支） + 调用引擎评估。

    返回 {etf_code: result_dict}
    """
    results: Dict[str, Dict] = {}

    for etf_code in engine.list_etfs():
        cfg = engine.get_etf_config(etf_code)
        if cfg is None:
            continue

        metric = cfg["primary_metric"]
        index_code = (cfg.get("tracking_index_code") or "").strip()
        data_source = cfg.get("data_source", "unknown")

        current_value: Optional[float] = None
        note_override: Optional[str] = None

        # ========================================
        # PB 主指标：优先走 REQ-172 X6 路径
        # （读本地 data/valuation_history/<etf>_pb.csv 的最新一行）
        # ========================================
        if metric == "pb":
            pb_data = get_etf_current_pb(etf_code)
            if pb_data:
                current_value = pb_data["pb"]
                logger.info("X6 加权 PB 读取完成", {
                    "etf": etf_code,
                    "date": pb_data.get("date"),
                    "pb": current_value,
                })
            else:
                note_override = (
                    "X6 加权 PB 历史暂未生成，请跑 "
                    "`python scripts/stock_bps_fetcher.py --etf "
                    f"{etf_code} --backfill` 一次性初始化"
                )
                logger.info("X6 PB 历史缺失", {"etf": etf_code})

        # ========================================
        # PE 主指标：沿用 csindex 实时拉取（含 csindex-proxy 代理指数路径）
        # ========================================
        elif data_source in ("csindex", "csindex-proxy") and index_code:
            fetched = fetch_csindex_current_pe(index_code)
            if fetched:
                current_value = fetched["pe_ttm"]
                # 把 PE 写入历史以备方法 B' 演化（PE 主指标专用的旧路径）
                append_history_row(
                    etf_code=etf_code,
                    date_str=fetched["date"],
                    pe_ttm=fetched["pe_ttm"],
                    pb=None,
                )
            logger.info("csindex 拉取完成", {
                "etf": etf_code,
                "index_code": index_code,
                "pe": fetched.get("pe_ttm") if fetched else None,
                "used_as_current": current_value is not None,
            })

        # ========================================
        # PE 主指标 hist-only：real-time API 不可用，从历史 CSV 读最新值
        # (REQ-178: 562500 机器人等 real-time 返回 404 的指数)
        # ========================================
        elif data_source == "csindex-hist-only" and metric == "pe_ttm":
            csv_path = DEFAULT_HISTORY_DIR / f"{etf_code}.csv"
            if csv_path.exists():
                try:
                    with csv_path.open("r", encoding="utf-8") as f:
                        lines = f.readlines()
                    # 取最后一行非空行
                    for line in reversed(lines):
                        parts = line.strip().split(",")
                        if len(parts) >= 2 and parts[1]:
                            try:
                                current_value = float(parts[1])
                                if current_value > 0:
                                    logger.info("hist-only PE 读取完成", {
                                        "etf": etf_code,
                                        "date": parts[0],
                                        "pe": current_value,
                                    })
                                    break
                            except ValueError:
                                continue
                except Exception as exc:  # noqa: BLE001
                    logger.warn("hist-only CSV 读取失败", {"etf": etf_code, "error": str(exc)[:80]})
            if current_value is None:
                logger.info("hist-only 无历史数据", {"etf": etf_code})

        else:
            logger.info("无实时数据源，使用纯锚点模式", {"etf": etf_code, "data_source": data_source})

        result = engine.evaluate(etf_code, current_value)
        if result is not None:
            if note_override and result.get("confidence") == "no-data":
                result["window_note"] = note_override
            results[etf_code] = result

    return results


# ============================================================
# HTML DOM 注入
# ============================================================
# valuation-block 的完整模板（有数据）
_VALUATION_BLOCK_WITH_DATA = """                <div class="valuation-block" id="valuation-block-{etf}">
                    <div class="valuation-header" id="valuation-header-{etf}">
                        <div class="valuation-title" id="valuation-title-{etf}">
                            <span>📐 估值水位</span>
                            <span class="valuation-info-icon" id="valuation-info-{etf}" tabindex="0" aria-label="估值说明">
                                ?
                                <span class="valuation-tooltip" id="valuation-tooltip-{etf}">
                                    <span class="valuation-tooltip-row"><span class="valuation-tooltip-key">指标</span><span>{metric_label}</span></span>
                                    <span class="valuation-tooltip-row"><span class="valuation-tooltip-key">参考指数</span><span>{tracking_index}</span></span>
                                    <span class="valuation-tooltip-row"><span class="valuation-tooltip-key">口径</span><span>{confidence_text}</span></span>
                                    <span class="valuation-tooltip-note">{window_note}</span>
                                </span>
                            </span>
                        </div>
                    </div>
                    <div class="valuation-bar-wrap" id="valuation-bar-wrap-{etf}" title="{window_note}">
                        <div class="valuation-bar-indicator" id="valuation-bar-indicator-{etf}" style="left: {pct}%;"></div>
                    </div>
                    <div class="valuation-bar-scale">
                        <span>0</span><span>20</span><span>40</span><span>60</span><span>80</span><span>100</span>
                    </div>
                    <div class="valuation-result" id="valuation-result-{etf}">
                        <div>
                            <span class="valuation-percentile-label">历史百分位</span>
                            <span class="valuation-percentile" id="valuation-percentile-{etf}">{pct}<span style="font-size:1rem;color:#6b7280;">%</span></span>
                        </div>
                        <span class="valuation-verdict-chip verdict-{verdict_color}" id="valuation-verdict-{etf}">{verdict_emoji} {verdict_label}</span>
                    </div>
                </div>"""

_VALUATION_BLOCK_NO_DATA = """                <div class="valuation-block" id="valuation-block-{etf}">
                    <div class="valuation-header" id="valuation-header-{etf}">
                        <div class="valuation-title" id="valuation-title-{etf}">
                            <span>📐 估值水位</span>
                            <span class="valuation-info-icon" id="valuation-info-{etf}" tabindex="0" aria-label="估值说明">
                                ?
                                <span class="valuation-tooltip" id="valuation-tooltip-{etf}">
                                    <span class="valuation-tooltip-row"><span class="valuation-tooltip-key">参考指数</span><span>{tracking_index}</span></span>
                                    <span class="valuation-tooltip-note">暂无实时估值数据源，本支 ETF 的估值水位将基于历史锚点模式离线研究后更新。</span>
                                </span>
                            </span>
                        </div>
                    </div>
                    <div class="valuation-no-data" id="valuation-no-data-{etf}">
                        {tracking_index} 暂无实时估值数据源 · 本支 ETF 的估值水位将基于历史锚点模式离线研究后更新
                    </div>
                </div>"""

_METRIC_LABEL = {"pe_ttm": "PE-TTM", "pb": "PB"}


def _render_block(etf: str, result: Dict) -> str:
    """根据评估结果渲染 valuation-block 的 HTML 片段"""
    if result["confidence"] == "no-data":
        return _VALUATION_BLOCK_NO_DATA.format(
            etf=etf,
            tracking_index=result.get("tracking_index", ""),
        )

    confidence = result["confidence"]
    sample_days = result.get("sample_days", 0)
    if confidence == "rule":
        confidence_text = "锚点估算"
    elif confidence == "blend":
        confidence_text = f"规则+历史 · {sample_days}天"
    else:
        confidence_text = f"历史百分位 · {sample_days}天"

    pct = result.get("percentile")
    pct_str = f"{pct:.1f}" if pct is not None else "—"

    verdict = result.get("verdict") or {}
    metric_label = _METRIC_LABEL.get(result.get("primary_metric", ""), result.get("primary_metric", ""))

    return _VALUATION_BLOCK_WITH_DATA.format(
        etf=etf,
        confidence_text=confidence_text,
        window_note=result.get("window_note", ""),
        pct=pct_str,
        verdict_color=verdict.get("color", "gray"),
        verdict_emoji=verdict.get("emoji", "⚪"),
        verdict_label=verdict.get("label", ""),
        metric_label=metric_label,
        tracking_index=result.get("tracking_index", ""),
    )


def inject_valuation_blocks(html_content: str, results: Dict[str, Dict]) -> Tuple[str, int]:
    """
    用新渲染的 valuation-block 替换 html_content 中对应的旧 block。

    返回 (新 html 内容, 替换成功的 ETF 数量)。
    """
    replaced = 0
    for etf, result in results.items():
        # 匹配：<div class="valuation-block" id="valuation-block-{etf}"> ... 最近的 </div>\n            </section>
        # 因为 block 本身是一个完整 <div>...</div>，用非贪婪匹配加末尾 sentinel
        # sentinel: 紧跟着的 "\n            </section>" 标记 fund-overview section 收尾
        pattern = re.compile(
            r'(                <div class="valuation-block" id="valuation-block-' + re.escape(etf) + r'">)'
            r'.*?'
            r'(\n            </section>)',
            re.DOTALL,
        )
        new_block = _render_block(etf, result)
        # 替换整段（保留末尾的 </section>）
        new_html, n = pattern.subn(new_block + r'\2', html_content, count=1)
        if n == 0:
            logger.warn("valuation-block 未在 HTML 中找到", {"etf": etf})
            continue
        html_content = new_html
        replaced += 1

    return html_content, replaced


# ============================================================
# 主入口：被 update_report 调用
# ============================================================
def run_valuation_update(html_file: Optional[Path] = None) -> bool:
    """
    估值更新主流程。

    1. 实例化 ValuationEngine（加载锚点）
    2. 对 6 支 ETF 分别拉取数据 / 评估
    3. 把结果注入指定 HTML 文件

    返回是否成功（只要 HTML 写回成功就返回 True，单支拉取失败不视为全局失败）。
    """
    html_path = Path(html_file) if html_file else DEFAULT_HTML_FILE
    if not html_path.exists():
        logger.error("HTML 文件不存在", {"path": str(html_path)})
        return False

    try:
        engine = ValuationEngine()
        results = evaluate_all_etfs(engine)
    except Exception as exc:  # noqa: BLE001
        logger.error("估值引擎/数据拉取异常", {"error": f"{type(exc).__name__}: {exc}"})
        return False

    if not results:
        logger.warn("估值评估无结果，跳过 HTML 注入")
        return False

    # 汇总统计
    summary = {}
    for etf, res in results.items():
        summary[etf] = {
            "confidence": res.get("confidence"),
            "percentile": res.get("percentile"),
            "verdict": (res.get("verdict") or {}).get("label"),
        }
    logger.info("估值评估完成", {"count": len(results), "summary": summary})

    # 注入
    html_content = html_path.read_text(encoding="utf-8")
    new_content, replaced = inject_valuation_blocks(html_content, results)
    if replaced == 0:
        logger.warn("未替换任何 valuation-block")
        return False

    html_path.write_text(new_content, encoding="utf-8")
    logger.info("HTML 估值 DOM 注入完成", {"replaced": replaced, "total": len(results)})
    return True


# ============================================================
# CLI
# ============================================================
def _cli_main() -> int:  # pragma: no cover
    import argparse
    import io

    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="ETF 估值数据拉取 + HTML 注入")
    parser.add_argument("--html", type=str, default=None, help="目标 HTML 路径")
    parser.add_argument("--dry-run", action="store_true", help="只算不写 HTML")
    args = parser.parse_args()

    if args.dry_run:
        engine = ValuationEngine()
        results = evaluate_all_etfs(engine)
        import json
        print(json.dumps(results, ensure_ascii=False, indent=2, default=str))
        return 0

    ok = run_valuation_update(args.html)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(_cli_main())
