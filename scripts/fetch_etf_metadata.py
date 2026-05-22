#!/usr/bin/env python3
"""REQ-213: ETF metadata fetcher — AUM + top 10 holdings from East Money.

Output: data/quant/etf_metadata.json

Usage:
    python scripts/fetch_etf_metadata.py              # update all ETFs
    python scripts/fetch_etf_metadata.py --code 516150 # single ETF
"""
import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
import yaml

sys.stdout.reconfigure(encoding="utf-8")

SKILL_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = SKILL_DIR / "config" / "quant_universe.yaml"
OUTPUT_PATH = SKILL_DIR / "data" / "quant" / "etf_metadata.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://fundf10.eastmoney.com/",
}

# ── Holdings API ────────────────────────────────────────────
HOLDINGS_URL = "https://fundf10.eastmoney.com/FundArchivesDatas.aspx"
# params: type=jjcc&code={code}&topline=10


def fetch_holdings(code: str) -> list:
    """Fetch top 10 holdings. Returns [{code, name, weight_pct}, ...]."""
    params = {"type": "jjcc", "code": code, "topline": "10"}
    try:
        resp = requests.get(HOLDINGS_URL, params=params, headers=HEADERS, timeout=15)
        resp.encoding = "utf-8"
        text = resp.text
    except Exception as e:
        print(f"  [WARN] Holdings request failed: {e}")
        return []

    # Extract content string from var apidata={content:"...", ...}
    m = re.search(r'content:\s*"(.*?)",\s*arryear', text, re.DOTALL)
    if not m:
        print(f"  [WARN] content not found in apidata")
        return []

    content = m.group(1)
    holdings = []
    rows = re.findall(r"<tr>.*?</tr>", content, re.DOTALL)
    for row in rows:
        tds = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)
        if len(tds) < 7:
            continue
        try:
            stock_code = re.sub(r"<[^>]+>", "", tds[1]).strip()  # col 1 = stock code
            stock_name = re.sub(r"<[^>]+>", "", tds[2]).strip()  # col 2 = stock name
            weight_str = re.sub(r"<[^>]+>", "", tds[6]).strip().replace("%", "")
            weight = float(weight_str)
            holdings.append({"code": stock_code, "name": stock_name, "weight_pct": weight})
        except (ValueError, IndexError):
            continue
    return holdings


# ── AUM (fund size) API ─────────────────────────────────────
FUND_DETAIL_URL = "https://fundf10.eastmoney.com/jbgk_{code}.html"


def fetch_aum(code: str) -> float | None:
    """Fetch fund net asset size in 亿元. Returns float or None."""
    url = FUND_DETAIL_URL.format(code=code)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.encoding = "utf-8"
        text = resp.text
    except Exception as e:
        print(f"  [WARN] AUM request failed: {e}")
        return None

    # Pattern: 净资产规模 ... 82.12
    m = re.search(r"净资产规模.*?([0-9.]+)", text, re.DOTALL)
    if not m:
        print(f"  [WARN] AUM not found on page")
        return None
    return float(m.group(1))


# ── Listing date ────────────────────────────────────────────
def fetch_listing_date(code: str) -> str | None:
    """Fetch ETF listing date (成立日期). Returns YYYY-MM-DD or None."""
    url = FUND_DETAIL_URL.format(code=code)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.encoding = "utf-8"
        text = resp.text
    except Exception:
        return None
    m = re.search(r"成立日期[：:]\s*(\d{4}-\d{2}-\d{2})", text)
    if not m:
        m = re.search(r"成\s*立\s*日[：:]\s*(\d{4}-\d{2}-\d{2})", text)
    return m.group(1) if m else None


# ── Main ────────────────────────────────────────────────────


def load_universe():
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg.get("universe", [])


def load_existing():
    if OUTPUT_PATH.exists():
        with OUTPUT_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_metadata(data: dict):
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def fetch_one(etf: dict, existing: dict) -> dict:
    code = etf["code"]
    name = etf.get("name", code)
    market = etf.get("market", "")
    sector = etf.get("sector", "")

    entry = existing.get(code, {})
    entry["code"] = code
    entry["name"] = name
    entry["market"] = market
    entry["sector"] = sector

    print(f"  {code} {name} ...", end=" ", flush=True)

    # Only update if older than 30 days or missing
    last_update = entry.get("updated", "")
    if last_update:
        try:
            age = (datetime.now() - datetime.strptime(last_update, "%Y-%m-%d")).days
            if age < 30 and entry.get("aum_yi") and entry.get("top10"):
                print("(cached, {age}d old)".format(age=age))
                return entry
        except ValueError:
            pass

    aum = fetch_aum(code)
    holdings = fetch_holdings(code)
    listing_date = fetch_listing_date(code)

    entry["aum_yi"] = aum
    entry["top10"] = holdings
    entry["listing_date"] = listing_date
    entry["updated"] = datetime.now().strftime("%Y-%m-%d")

    status = []
    if aum is not None:
        status.append(f"{aum:.1f}亿")
    if listing_date:
        status.append(f"listed {listing_date}")
    status.append(f"{len(holdings)} holdings")
    print("OK | " + " | ".join(status))
    return entry


def main():
    parser = argparse.ArgumentParser(description="REQ-213: ETF metadata fetcher")
    parser.add_argument("--code", type=str, help="Single ETF code")
    args = parser.parse_args()

    universe = load_universe()
    if args.code:
        universe = [e for e in universe if e["code"] == args.code]
        if not universe:
            print(f"ETF {args.code} not in universe")
            return

    existing = load_existing()
    result = {}
    ok = fail = 0

    print(f"Fetching metadata for {len(universe)} ETFs...")
    for etf in universe:
        try:
            entry = fetch_one(etf, existing)
            result[etf["code"]] = entry
            ok += 1
            time.sleep(1.5)  # polite rate limit
        except Exception as e:
            print(f"FAIL: {e}")
            if etf["code"] in existing:
                result[etf["code"]] = existing[etf["code"]]
            fail += 1

    save_metadata(result)
    print(f"\nDone: {ok} OK, {fail} fail → {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
