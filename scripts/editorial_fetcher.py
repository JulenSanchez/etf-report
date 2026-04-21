#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
REQ-158 Step C：editorial 抓取核心

抽象 Source 接口 + 两个具体实现 + 聚合器。
抓取完立刻调 compliance_filter.filter_batch，审计落盘。
产物：editorial_content 字段（yaml 结构），交给 Step D 写入 editorial_content.yaml。

用法：
    # CLI（手动）：
    python scripts/editorial_fetcher.py               # 抓全部（6 只 ETF + 3 张宏观卡）
    python scripts/editorial_fetcher.py --etf 159566  # 只抓单只 ETF
    python scripts/editorial_fetcher.py --dry-run     # 不写文件，只打印结果

    # 模块调用（供 update_report.py Step 3 使用）：
    from editorial_fetcher import fetch_all_editorial
    result = fetch_all_editorial(sources_path=..., rules_path=...)

设计：
  1. 每条 ETF 迭代其 top_stocks，抓新浪个股新闻页，解析 <div class="datelist">
  2. 每张宏观卡抓新浪滚动 lid json
  3. 所有原始条目统一跑 require/exclude 主题过滤 → 合规过滤 → 去重 → 截断 keep_n
  4. 抓取失败不中断（逐条 try/except），整体失败才返回 None
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import yaml
from bs4 import BeautifulSoup

# 本地导入
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
from compliance_filter import filter_batch, load_rules, write_audit  # noqa: E402

SKILL_DIR = os.path.dirname(SCRIPT_DIR)
DEFAULT_SOURCES_PATH = os.path.join(SKILL_DIR, "config", "editorial_sources.yaml")
DEFAULT_RULES_PATH = os.path.join(SKILL_DIR, "config", "compliance_rules.yaml")


# ============================================================
# HTTP 辅助
# ============================================================
def http_get(url: str, headers: Dict[str, str], timeout: int = 10,
             encodings: Tuple[str, ...] = ("utf-8", "gbk", "gb18030")) -> Optional[str]:
    """GET 并按编码候选尝试解码，失败返回 None（不抛）。"""
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except Exception:
        return None
    for enc in encodings:
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


# ============================================================
# Source 抽象
# ============================================================
@dataclass
class RawItem:
    title: str
    url: str = ""
    date: str = ""
    source: str = ""

    def to_dict(self) -> Dict:
        return {"title": self.title, "url": self.url, "date": self.date, "source": self.source}


class Source:
    """抽象源。子类实现 fetch() 返回 List[RawItem]."""
    def fetch(self) -> List[RawItem]:
        raise NotImplementedError


# ============================================================
# Source 实现 1：新浪个股新闻页
# ============================================================
class SinaStockNewsSource(Source):
    """
    新浪 vCB_AllNewsStock.php 页面（A 股 sh/sz、港股 hk 皆可）
    结构：<div class="datelist"><ul>...<a>标题</a>...</ul></div>
    新浪该页用 GBK 编码。
    """
    URL_TPL = "https://vip.stock.finance.sina.com.cn/corp/view/vCB_AllNewsStock.php?symbol={symbol}"

    def __init__(self, symbol: str, stock_name: str, headers: Dict[str, str],
                 timeout: int = 10, top_n: int = 40):
        self.symbol = symbol
        self.stock_name = stock_name
        self.headers = headers
        self.timeout = timeout
        self.top_n = top_n

    def fetch(self) -> List[RawItem]:
        url = self.URL_TPL.format(symbol=self.symbol)
        html = http_get(url, self.headers, timeout=self.timeout,
                        encodings=("gbk", "gb18030", "utf-8"))
        if not html:
            return []
        soup = BeautifulSoup(html, "html.parser")
        datelist = soup.select_one("div.datelist ul")
        if not datelist:
            return []

        items: List[RawItem] = []
        # 新浪 datelist ul 结构为 "日期 · <a>标题</a>"，日期和链接交错出现在文本里
        # 最稳妥：取所有 <a>，父节点文本里找 YYYY-MM-DD 时间戳
        ul_text = datelist.get_text("\n", strip=False)
        # 按行切，每行形如 "2026-04-20 10:23 <a>标题</a>" 但 BS4 没 <a> 文本，
        # 所以改用 regex 直接匹配 HTML
        html_str = str(datelist)
        # pattern: (date) ... <a href="URL">TITLE</a>
        pattern = re.compile(
            r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})[^\n<]*'
            r'<a\s+[^>]*href="([^"]+)"[^>]*>([^<]+)</a>',
            re.DOTALL,
        )
        for m in pattern.finditer(html_str):
            date_s, link, title = m.group(1), m.group(2), m.group(3)
            items.append(RawItem(
                title=title.strip(),
                url=link.strip(),
                date=date_s.strip(),
                source=f"sina_stock:{self.symbol}:{self.stock_name}",
            ))
            if len(items) >= self.top_n:
                break
        return items


# ============================================================
# Source 实现 2：新浪滚动新闻 JSON
# ============================================================
class SinaRollJsonSource(Source):
    """
    feed.mix.sina.com.cn/api/roll/get?pageid=153&lid={lid}&num=N&page=1
    返回 {"result": {"data": [...]}}，每条含 title/url/ctime/media_name。
    """
    URL_TPL = (
        "https://feed.mix.sina.com.cn/api/roll/get?"
        "pageid=153&lid={lid}&k=&num={num}&page=1&_={ts}"
    )

    def __init__(self, lid: int, name: str, headers: Dict[str, str],
                 timeout: int = 10, keep_top: int = 30):
        self.lid = lid
        self.name = name
        self.headers = headers
        self.timeout = timeout
        self.keep_top = keep_top

    def fetch(self) -> List[RawItem]:
        url = self.URL_TPL.format(lid=self.lid, num=self.keep_top,
                                  ts=int(time.time() * 1000))
        text = http_get(url, self.headers, timeout=self.timeout)
        if not text:
            return []
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            m = re.search(r"\((\{.*\})\)", text, re.DOTALL)
            if not m:
                return []
            try:
                data = json.loads(m.group(1))
            except Exception:
                return []
        arr = (data.get("result") or {}).get("data") or []
        items: List[RawItem] = []
        for it in arr[: self.keep_top]:
            ctime_raw = it.get("ctime") or it.get("create_time") or ""
            # ctime 可能是 unix 时间戳（字符串）
            date_s = ""
            try:
                ts = int(str(ctime_raw))
                date_s = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
            except Exception:
                date_s = str(ctime_raw)[:16]
            items.append(RawItem(
                title=(it.get("title") or "").strip(),
                url=it.get("url") or "",
                date=date_s,
                source=f"sina_roll:lid={self.lid}:{self.name}",
            ))
        return items


# ============================================================
# Source 实现 3：富途港股个股新闻
# ============================================================
class FutuStockNewsSource(Source):
    """
    富途港股新闻页：https://www.futunn.com/stock/{code}-HK/news
    服务端渲染，.news-item 容器带时间 + 媒体 + 标题。
    """
    URL_TPL = "https://www.futunn.com/stock/{code}-HK/news"

    def __init__(self, code: str, stock_name: str, headers: Dict[str, str],
                 timeout: int = 10, top_n: int = 20):
        self.code = code
        self.stock_name = stock_name
        self.headers = headers
        self.timeout = timeout
        self.top_n = top_n

    def fetch(self) -> List[RawItem]:
        url = self.URL_TPL.format(code=self.code)
        # 富途需要标准浏览器 UA + 允许 Referer 为自己
        headers = dict(self.headers)
        headers.setdefault("Referer", "https://www.futunn.com/")
        html = http_get(url, headers, timeout=self.timeout)
        if not html:
            return []
        soup = BeautifulSoup(html, "html.parser")
        news_items = soup.select(".news-item")
        items: List[RawItem] = []
        for el in news_items[: self.top_n]:
            text = el.get_text(strip=True)
            if not text or len(text) < 6:
                continue
            # 文本结构常见："标题媒体名时间"；分离媒体和时间
            # 时间格式例："04/20 19:45" 或 "00:00" 或 "yyyy-MM-dd HH:mm"
            time_match = re.search(r'(\d{2}/\d{2}\s+\d{2}:\d{2}|\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}|\d{2}:\d{2})\s*$', text)
            date_s = time_match.group(1) if time_match else ""
            # 移除时间后缀，媒体名通常在最后几字（无统一分隔符，作为整体保留）
            title = text[: time_match.start()].rstrip() if time_match else text
            # 清理可能的多余空格/媒体名尾巴：富途把媒体名直接贴在标题后（无分隔），本实现
            # 不再尝试切分媒体名，保留整条作为 title，后续过滤仍按关键词走
            link = ""
            a = el.find("a", href=True)
            if a:
                link = a["href"]
                if link.startswith("/"):
                    link = "https://www.futunn.com" + link
            items.append(RawItem(
                title=title.strip(),
                url=link,
                date=date_s.strip(),
                source=f"futu_hk:{self.code}:{self.stock_name}",
            ))
        return items


# ============================================================
# Source 实现 4：华尔街见闻 快讯 API
# ============================================================
class WallStreetCnLivesSource(Source):
    """
    华尔街见闻 快讯 API：
    GET https://api-one.wallstcn.com/apiv1/content/lives?channel={channel}&client=pc&limit=N
    返回 {"code":20000,"data":{"items":[{content,title,display_time,...}]}}
    """
    URL_TPL = (
        "https://api-one.wallstcn.com/apiv1/content/lives?"
        "channel={channel}&client=pc&limit={limit}"
    )

    def __init__(self, channel: str, name: str, headers: Dict[str, str],
                 timeout: int = 10, limit: int = 30):
        self.channel = channel
        self.name = name
        self.headers = headers
        self.timeout = timeout
        self.limit = limit

    def fetch(self) -> List[RawItem]:
        url = self.URL_TPL.format(channel=self.channel, limit=self.limit)
        text = http_get(url, self.headers, timeout=self.timeout)
        if not text:
            return []
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return []
        if (data or {}).get("code") != 20000:
            return []
        arr = ((data.get("data") or {}).get("items") or [])
        items: List[RawItem] = []
        for it in arr:
            # 优先取 title（有编辑整理过的），否则取 content 前 80 字
            title = (it.get("title") or "").strip()
            if not title:
                content = (it.get("content_text") or it.get("content") or "").strip()
                # content 可能含 HTML，剥标签
                content = re.sub(r"<[^>]+>", "", content)
                title = content[:120]
            display_time = it.get("display_time")
            date_s = ""
            try:
                ts = int(display_time)
                date_s = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
            except Exception:
                date_s = str(display_time)[:16]
            items.append(RawItem(
                title=title,
                url=it.get("uri") or "",
                date=date_s,
                source=f"wscn_lives:{self.channel}:{self.name}",
            ))
        return items


# ============================================================
# Source 实现 5：东方财富关键词文章搜索
# ============================================================
class EastMoneyArticleSearchSource(Source):
    """
    东方财富综合搜索 JSONP：
    https://search-api-web.eastmoney.com/search/jsonp?cb=jQuery&param={"keyword":"...", "type":["article"], ...}
    仅提取 article 部分。
    """
    URL_BASE = "https://search-api-web.eastmoney.com/search/jsonp"

    def __init__(self, keyword: str, headers: Dict[str, str],
                 timeout: int = 10, limit: int = 20):
        self.keyword = keyword
        self.headers = headers
        self.timeout = timeout
        self.limit = limit

    def fetch(self) -> List[RawItem]:
        param = json.dumps({
            "uid": "",
            "keyword": self.keyword,
            "type": ["article"],
            "client": "web",
            "clientVersion": "curr",
            "pageIndex": 1,
            "pageSize": self.limit,
        }, ensure_ascii=False)
        url = f"{self.URL_BASE}?cb=jQuery&param={urllib.parse.quote(param)}"
        text = http_get(url, self.headers, timeout=self.timeout)
        if not text:
            return []
        # 去 jsonp 壳
        m = re.search(r"jQuery\((\{.*\})\)\s*;?\s*$", text, re.DOTALL)
        if not m:
            return []
        try:
            data = json.loads(m.group(1))
        except Exception:
            return []
        arr = ((data.get("result") or {}).get("article") or [])
        items: List[RawItem] = []
        for it in arr:
            # 东财 article 字段：title / url / showTime / mediaName
            items.append(RawItem(
                title=(it.get("title") or "").strip(),
                url=it.get("url") or "",
                date=(it.get("showTime") or "")[:16],
                source=f"em_article:keyword={self.keyword}",
            ))
        return items


# ============================================================
# 主题过滤：require / exclude 关键词
# ============================================================
def topic_filter(items: List[RawItem], require: List[str],
                 exclude: List[str]) -> List[RawItem]:
    """require 命中任一即保留；exclude 命中任一即丢弃。
    require 为空视为"全通过"。
    """
    kept: List[RawItem] = []
    for it in items:
        title = it.title or ""
        # exclude 优先
        if any(kw and kw in title for kw in exclude):
            continue
        if require:
            if any(kw and kw in title for kw in require):
                kept.append(it)
        else:
            kept.append(it)
    return kept


def dedup_items(items: List[RawItem]) -> List[RawItem]:
    """按 title 去重（保留首次出现）。"""
    seen = set()
    out = []
    for it in items:
        key = (it.title or "").strip()
        if key and key not in seen:
            seen.add(key)
            out.append(it)
    return out


# ============================================================
# 聚合器
# ============================================================
@dataclass
class EditorialFetchResult:
    generated_at: str
    content_date: str
    etf_cards: Dict[str, Dict] = field(default_factory=dict)      # {code: {research_cards: [str, ...]}}
    macro_cards: Dict[str, Dict] = field(default_factory=dict)    # {card_id: {title, items: [...]}
    stats: Dict = field(default_factory=dict)                     # per-ETF / per-card 抓取统计

    def to_yaml_dict(self) -> Dict:
        """转换为写入 editorial_content.yaml 的结构。"""
        out = {
            "content_date": self.content_date,
            "etf_cards": {},
            "macro_cards": {},
        }
        for code, card in self.etf_cards.items():
            out["etf_cards"][code] = {
                "freshness_policy": "manual_daily",
                "research_cards": card.get("research_cards", []),
            }
        for card_id, card in self.macro_cards.items():
            out["macro_cards"][card_id] = {
                "title": card.get("title", ""),
                "freshness_policy": "manual_daily",
                "items": card.get("items", []),
            }
        return out


def _format_research_card(item: Dict) -> str:
    """把一条 raw/filtered item 格式化为 research_cards 文本（带 💡 前缀）。"""
    title = (item.get("title") or "").strip()
    # 如果被合规 flag 打了 [弱相关] 前缀，保留
    if title.startswith("[弱相关]"):
        return f"💡 {title}"
    return f"💡 {title}"


def _format_macro_item(item: Dict) -> str:
    """宏观卡条目格式（沿用原 YAML 里的 emoji + 文本，不带 💡）。"""
    return (item.get("title") or "").strip()


def fetch_for_etf(code: str, cfg: Dict, headers: Dict, rules: Dict,
                  fetcher_cfg: Dict) -> Tuple[List[Dict], Dict]:
    """抓一只 ETF 的全部源 → 主题过滤 → 合规过滤 → 返回 (final_items, per_etf_stats).

    支持三类源（均可选）：
      1. top_stocks：新浪个股新闻（默认主源，A 股 sh/sz、港股 hk 皆可）
      2. futu_hk_stocks：富途港股新闻（专治港股同质化，标题更多样）
      3. em_keywords：东方财富关键词文章搜索（扩召回，覆盖 BD 交易/跨国药企）
    """
    all_raw: List[RawItem] = []

    # 1. 新浪个股新闻
    for stock in cfg.get("top_stocks", []) or []:
        src = SinaStockNewsSource(
            symbol=stock["symbol"],
            stock_name=stock["stock_name"],
            headers=headers,
            timeout=fetcher_cfg.get("request_timeout", 10),
            top_n=fetcher_cfg.get("per_stock_top_n", 40),
        )
        raw = src.fetch()
        all_raw.extend(raw)
        time.sleep(fetcher_cfg.get("inter_request_delay", 0.3))

    # 2. 富途港股新闻（专门拉港股非 sina 的补充新闻）
    for stock in cfg.get("futu_hk_stocks", []) or []:
        src = FutuStockNewsSource(
            code=stock["code"],
            stock_name=stock["stock_name"],
            headers=headers,
            timeout=fetcher_cfg.get("request_timeout", 10),
            top_n=fetcher_cfg.get("per_stock_top_n", 20),
        )
        raw = src.fetch()
        all_raw.extend(raw)
        time.sleep(fetcher_cfg.get("inter_request_delay", 0.3))

    # 3. 东财关键词文章搜索（覆盖 BD/跨国药企等主题词）
    for keyword in cfg.get("em_keywords", []) or []:
        src = EastMoneyArticleSearchSource(
            keyword=keyword,
            headers=headers,
            timeout=fetcher_cfg.get("request_timeout", 10),
            limit=fetcher_cfg.get("em_search_limit", 15),
        )
        raw = src.fetch()
        all_raw.extend(raw)
        time.sleep(fetcher_cfg.get("inter_request_delay", 0.3))

    raw_count = len(all_raw)

    # 主题过滤
    topic_kept = topic_filter(
        all_raw,
        cfg.get("require_keywords", []) or [],
        cfg.get("exclude_keywords", []) or [],
    )
    topic_kept = dedup_items(topic_kept)
    topic_count = len(topic_kept)

    # 合规过滤
    compliance_input = [it.to_dict() for it in topic_kept]
    kept_compliance, blocked_compliance, comp_stats = filter_batch(compliance_input, rules)

    # 审计
    if blocked_compliance or kept_compliance:
        write_audit(
            blocked_compliance, kept_compliance, comp_stats,
            run_context={"trigger": "editorial_fetch", "etf": code},
            rules=rules,
        )

    # 截断到 per_etf_kept_n
    keep_n = fetcher_cfg.get("per_etf_kept_n", 6)
    final = kept_compliance[:keep_n]

    stats = {
        "raw_count": raw_count,
        "after_topic_filter": topic_count,
        "after_compliance": len(kept_compliance),
        "blocked": len(blocked_compliance),
        "final": len(final),
    }
    return final, stats


def fetch_for_macro_card(card_id: str, card_cfg: Dict, headers: Dict, rules: Dict,
                         fetcher_cfg: Dict) -> Tuple[List[Dict], Dict]:
    """抓一张宏观卡。支持 sina_roll_json 和 wscn_lives 两类源。"""
    all_raw: List[RawItem] = []
    for src_cfg in card_cfg.get("sources", []) or []:
        src_type = src_cfg.get("type")
        if src_type == "sina_roll_json":
            src = SinaRollJsonSource(
                lid=src_cfg["lid"],
                name=src_cfg.get("name", ""),
                headers=headers,
                timeout=fetcher_cfg.get("request_timeout", 10),
                keep_top=src_cfg.get("keep_top", 30),
            )
        elif src_type == "wscn_lives":
            src = WallStreetCnLivesSource(
                channel=src_cfg.get("channel", "global-channel"),
                name=src_cfg.get("name", ""),
                headers=headers,
                timeout=fetcher_cfg.get("request_timeout", 10),
                limit=src_cfg.get("keep_top", 30),
            )
        elif src_type == "em_article_search":
            # 允许宏观卡也用东财关键词搜索（如政策类关键词）
            src = EastMoneyArticleSearchSource(
                keyword=src_cfg.get("keyword", ""),
                headers=headers,
                timeout=fetcher_cfg.get("request_timeout", 10),
                limit=src_cfg.get("keep_top", 20),
            )
        else:
            continue
        raw = src.fetch()
        all_raw.extend(raw)
        time.sleep(fetcher_cfg.get("inter_request_delay", 0.3))

    raw_count = len(all_raw)
    topic_kept = topic_filter(
        all_raw,
        card_cfg.get("require_keywords", []) or [],
        card_cfg.get("exclude_keywords", []) or [],
    )
    topic_kept = dedup_items(topic_kept)

    compliance_input = [it.to_dict() for it in topic_kept]
    kept_compliance, blocked_compliance, comp_stats = filter_batch(compliance_input, rules)

    if blocked_compliance or kept_compliance:
        write_audit(
            blocked_compliance, kept_compliance, comp_stats,
            run_context={"trigger": "editorial_fetch", "macro_card": card_id},
            rules=rules,
        )

    keep_n = card_cfg.get("keep_n", 4)
    final = kept_compliance[:keep_n]

    stats = {
        "raw_count": raw_count,
        "after_topic_filter": len(topic_kept),
        "after_compliance": len(kept_compliance),
        "blocked": len(blocked_compliance),
        "final": len(final),
    }
    return final, stats


def fetch_all_editorial(sources_path: str = DEFAULT_SOURCES_PATH,
                        rules_path: str = DEFAULT_RULES_PATH,
                        only_etf: Optional[str] = None,
                        only_macro: Optional[str] = None) -> EditorialFetchResult:
    """抓全部 ETF + 宏观卡，返回结构化结果。"""
    with open(sources_path, "r", encoding="utf-8") as f:
        sources_cfg = yaml.safe_load(f) or {}
    rules = load_rules(rules_path)

    fetcher_cfg = sources_cfg.get("fetcher") or {}
    headers = fetcher_cfg.get("http_headers") or {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://finance.sina.com.cn/",
    }

    today = datetime.now().strftime("%Y-%m-%d")
    result = EditorialFetchResult(
        generated_at=datetime.now().isoformat(timespec="seconds"),
        content_date=today,
    )

    # ETFs
    etfs_cfg = sources_cfg.get("etfs") or {}
    for code, cfg in etfs_cfg.items():
        if only_etf and code != only_etf:
            continue
        final_items, stats = fetch_for_etf(code, cfg, headers, rules, fetcher_cfg)
        result.etf_cards[code] = {
            "name": cfg.get("name", ""),
            "research_cards": [_format_research_card(it) for it in final_items],
        }
        result.stats[f"etf:{code}"] = stats

    # 宏观卡
    macro_cfg = sources_cfg.get("macro_cards") or {}
    for card_id, card_cfg in macro_cfg.items():
        if only_macro and card_id != only_macro:
            continue
        final_items, stats = fetch_for_macro_card(card_id, card_cfg, headers, rules, fetcher_cfg)
        result.macro_cards[card_id] = {
            "title": card_cfg.get("title", ""),
            "items": [_format_macro_item(it) for it in final_items],
        }
        result.stats[f"macro:{card_id}"] = stats

    return result


# ============================================================
# CLI
# ============================================================
def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="REQ-158 editorial 抓取器")
    parser.add_argument("--etf", help="只抓指定 ETF，如 159566")
    parser.add_argument("--macro", help="只抓指定宏观卡，如 domestic-policy-card")
    parser.add_argument("--dry-run", action="store_true",
                        help="不写 editorial_content.yaml，只打印结果")
    parser.add_argument("--sources", default=DEFAULT_SOURCES_PATH)
    parser.add_argument("--rules", default=DEFAULT_RULES_PATH)
    parser.add_argument("--output",
                        default=os.path.join(SKILL_DIR, "config", "editorial_content.yaml"),
                        help="写入目标（默认覆盖 editorial_content.yaml）")
    args = parser.parse_args()

    print(f"[editorial_fetcher] 开始抓取")
    print(f"  sources: {args.sources}")
    print(f"  rules:   {args.rules}")
    if args.etf: print(f"  只抓 ETF: {args.etf}")
    if args.macro: print(f"  只抓宏观卡: {args.macro}")

    result = fetch_all_editorial(
        sources_path=args.sources,
        rules_path=args.rules,
        only_etf=args.etf,
        only_macro=args.macro,
    )

    print("\n=== 抓取统计 ===")
    for key, stats in result.stats.items():
        print(f"  {key:40s}  raw={stats['raw_count']:3d}  topic→{stats['after_topic_filter']:3d}"
              f"  compl→{stats['after_compliance']:3d}  block={stats['blocked']}  final={stats['final']}")

    print("\n=== ETF 研究卡摘要 ===")
    for code, card in result.etf_cards.items():
        print(f"\n  {code} {card.get('name', '')}")
        for rc in card.get("research_cards", []):
            print(f"    - {rc[:100]}")

    print("\n=== 宏观卡摘要 ===")
    for card_id, card in result.macro_cards.items():
        print(f"\n  {card_id}  ({card.get('title', '')})")
        for it in card.get("items", []):
            print(f"    - {it[:100]}")

    if args.dry_run:
        print("\n[dry-run] 不写入文件")
        return

    # 写入 editorial_content.yaml（完整覆盖）
    yaml_dict = result.to_yaml_dict()
    with open(args.output, "w", encoding="utf-8") as f:
        yaml.safe_dump(yaml_dict, f, allow_unicode=True, sort_keys=False, width=1000)
    print(f"\n已写入：{args.output}")


if __name__ == "__main__":
    main()
