# -*- coding: utf-8 -*-
"""REQ-158 Step C 单测：editorial_fetcher 的解析、主题过滤、去重、聚合。"""
import json
from unittest.mock import patch


# ---------- 新浪个股新闻解析 ----------
def test_sina_stock_news_parse_datelist(load_module):
    module = load_module("editorial_fetcher")
    # 模拟新浪个股页 HTML（含 datelist）
    fake_html = """
    <html><body>
    <div class="datelist"><ul>
        2026-04-20 10:23 · <a href="https://finance.sina.com.cn/r/1">宁德时代一季报业绩靓丽</a>
        2026-04-19 15:05 · <a href="https://finance.sina.com.cn/r/2">宁德时代布局上游资源</a>
        2026-04-18 09:10 · <a href="https://finance.sina.com.cn/r/3">宁德时代股东询价转让</a>
    </ul></div>
    </body></html>
    """
    with patch.object(module, "http_get", return_value=fake_html):
        src = module.SinaStockNewsSource("sz300750", "宁德时代", {}, top_n=40)
        items = src.fetch()
    assert len(items) == 3
    assert items[0].title == "宁德时代一季报业绩靓丽"
    assert items[0].url == "https://finance.sina.com.cn/r/1"
    assert items[0].date == "2026-04-20 10:23"
    assert items[0].source == "sina_stock:sz300750:宁德时代"


def test_sina_stock_news_respects_top_n(load_module):
    module = load_module("editorial_fetcher")
    rows = "\n".join(
        f'2026-04-{20 - i:02d} 10:00 · <a href="/url/{i}">标题 {i}</a>'
        for i in range(10)
    )
    html = f'<div class="datelist"><ul>{rows}</ul></div>'
    with patch.object(module, "http_get", return_value=html):
        src = module.SinaStockNewsSource("sz300750", "宁德时代", {}, top_n=3)
        items = src.fetch()
    assert len(items) == 3


def test_sina_stock_news_handles_empty_html(load_module):
    module = load_module("editorial_fetcher")
    # datelist 不存在
    with patch.object(module, "http_get", return_value="<html><body>nothing</body></html>"):
        src = module.SinaStockNewsSource("sz300750", "宁德时代", {})
        assert src.fetch() == []

    # http_get 返回 None（HTTP 失败）
    with patch.object(module, "http_get", return_value=None):
        src = module.SinaStockNewsSource("sz300750", "宁德时代", {})
        assert src.fetch() == []


def test_sina_stock_news_supports_hk_symbol(load_module):
    """港股代码（hk06160）应同一 parser 可用。"""
    module = load_module("editorial_fetcher")
    html = (
        '<div class="datelist"><ul>'
        '2026-04-20 10:00 · <a href="https://finance.sina.com.cn/hk/1">百济神州创新药获批</a>'
        '</ul></div>'
    )
    with patch.object(module, "http_get", return_value=html):
        src = module.SinaStockNewsSource("hk06160", "百济神州", {})
        items = src.fetch()
    assert len(items) == 1
    assert "百济神州" in items[0].title
    assert items[0].source == "sina_stock:hk06160:百济神州"


# ---------- 新浪滚动 JSON 解析 ----------
def test_sina_roll_json_parse(load_module):
    module = load_module("editorial_fetcher")
    fake_json = json.dumps({
        "result": {
            "data": [
                {"title": "美联储维持利率不变",
                 "url": "https://finance.sina.com.cn/x/1",
                 "ctime": "1776688919", "media_name": "环球市场"},
                {"title": "降息预期推迟至9月",
                 "url": "https://finance.sina.com.cn/x/2",
                 "ctime": "1776688000", "media_name": "新华财经"},
            ]
        }
    })
    with patch.object(module, "http_get", return_value=fake_json):
        src = module.SinaRollJsonSource(lid=2517, name="行业研究", headers={}, keep_top=10)
        items = src.fetch()
    assert len(items) == 2
    assert items[0].title == "美联储维持利率不变"
    # ctime 应被转成时间字符串
    assert items[0].date.startswith("20")  # 类似 2026-...
    assert items[0].source == "sina_roll:lid=2517:行业研究"


def test_sina_roll_json_handles_jsonp_wrapper(load_module):
    module = load_module("editorial_fetcher")
    wrapped = 'callback({"result": {"data": [{"title": "test", "url": "u", "ctime": "1776688000"}]}})'
    with patch.object(module, "http_get", return_value=wrapped):
        src = module.SinaRollJsonSource(lid=1686, name="财经", headers={})
        items = src.fetch()
    assert len(items) == 1
    assert items[0].title == "test"


def test_sina_roll_json_handles_empty(load_module):
    module = load_module("editorial_fetcher")
    with patch.object(module, "http_get", return_value=None):
        src = module.SinaRollJsonSource(lid=1686, name="财经", headers={})
        assert src.fetch() == []

    with patch.object(module, "http_get", return_value="not json"):
        src = module.SinaRollJsonSource(lid=1686, name="财经", headers={})
        assert src.fetch() == []


# ---------- topic_filter ----------
def test_topic_filter_require_any(load_module):
    module = load_module("editorial_fetcher")
    items = [
        module.RawItem(title="宁德时代一季报"),
        module.RawItem(title="北京车展首发新车"),
        module.RawItem(title="比亚迪电池技术突破"),
    ]
    kept = module.topic_filter(items, require=["电池", "宁德"], exclude=["车展"])
    titles = [it.title for it in kept]
    assert "宁德时代一季报" in titles
    assert "比亚迪电池技术突破" in titles
    assert "北京车展首发新车" not in titles  # exclude 拦住


def test_topic_filter_empty_require_passes_all(load_module):
    module = load_module("editorial_fetcher")
    items = [module.RawItem(title="随便的标题")]
    kept = module.topic_filter(items, require=[], exclude=[])
    assert len(kept) == 1


def test_topic_filter_exclude_beats_require(load_module):
    """exclude 优先级高于 require：同时命中时 exclude 赢。"""
    module = load_module("editorial_fetcher")
    items = [
        module.RawItem(title="电池车展联合主题"),  # 同时含 "电池"（require）和 "车展"（exclude）
    ]
    kept = module.topic_filter(items, require=["电池"], exclude=["车展"])
    assert kept == []


def test_dedup_items_by_title(load_module):
    module = load_module("editorial_fetcher")
    items = [
        module.RawItem(title="宁德时代一季报", url="u1"),
        module.RawItem(title="宁德时代一季报", url="u2"),  # 重复
        module.RawItem(title="比亚迪电池", url="u3"),
    ]
    out = module.dedup_items(items)
    assert len(out) == 2
    assert out[0].url == "u1"  # 保留首次


# ---------- fetch_for_etf 端到端（用 mock） ----------
def test_fetch_for_etf_end_to_end(tmp_path, monkeypatch, load_module):
    module = load_module("editorial_fetcher")

    # 让审计文件写到 tmp
    monkeypatch.setattr(module, "SKILL_DIR", str(tmp_path))

    # 给 compliance_filter 也指到 tmp
    from compliance_filter import load_rules  # type: ignore
    import compliance_filter  # type: ignore
    monkeypatch.setattr(compliance_filter, "SKILL_DIR", str(tmp_path))

    rules = module.load_rules()  # 用真实 rules

    # mock 三个 top_stocks 各返回一批
    def fake_fetch_factory(titles):
        def fake_fetch(self):
            return [module.RawItem(title=t, url=f"u_{t[:5]}",
                                   date="2026-04-20 10:00",
                                   source=f"sina_stock:{self.symbol}:{self.stock_name}")
                    for t in titles]
        return fake_fetch

    # 构造输入：
    #   stock A 返回 3 条：2 条命中主题、1 条不命中
    #   stock B 返回 2 条：1 条命中、1 条命中但含合规敏感词
    titles_A = ["宁德时代开矿布局", "某保证收益产品", "娱乐圈新闻（应被 exclude）"]
    titles_B = ["宁德时代电池业绩", "台独分子言论"]

    call_count = {"n": 0}
    batches = [titles_A, titles_B]

    def dispatch_fetch(self):
        idx = call_count["n"]
        call_count["n"] += 1
        if idx < len(batches):
            return [module.RawItem(title=t, url=f"u_{idx}_{i}",
                                   date="2026-04-20 10:00",
                                   source=f"sina_stock:{self.symbol}:{self.stock_name}")
                    for i, t in enumerate(batches[idx])]
        return []

    monkeypatch.setattr(module.SinaStockNewsSource, "fetch", dispatch_fetch)

    cfg = {
        "top_stocks": [
            {"symbol": "sz300750", "stock_name": "宁德时代"},
            {"symbol": "sz300014", "stock_name": "亿纬锂能"},
        ],
        "require_keywords": ["电池", "宁德"],
        "exclude_keywords": ["娱乐圈"],
    }
    fetcher_cfg = {"per_stock_top_n": 40, "per_etf_kept_n": 6, "inter_request_delay": 0,
                   "request_timeout": 10}

    final, stats = module.fetch_for_etf("159566", cfg, headers={}, rules=rules,
                                        fetcher_cfg=fetcher_cfg)

    # raw 共 5 条，exclude 掉 1 条娱乐圈 → topic 4 条
    # 其中"某保证收益"仅因含"宁德"才 True? 其实它不含 require 词，不会进 topic —— 等下
    # 实际 require=["电池","宁德"]：
    #   宁德时代开矿布局 → 含"宁德" → topic yes
    #   某保证收益产品 → 不含 → topic drop
    #   娱乐圈新闻 → exclude drop
    #   宁德时代电池业绩 → 含"电池/宁德" → topic yes
    #   台独分子言论 → 不含 require 词 → topic drop
    # topic 后剩 2 条（宁德开矿、宁德电池）
    # 合规过滤：都不违规，通过
    assert stats["raw_count"] == 5
    assert stats["after_topic_filter"] == 2
    assert stats["after_compliance"] == 2
    assert stats["blocked"] == 0
    assert stats["final"] == 2
    titles_final = [it["title"] for it in final]
    assert "宁德时代开矿布局" in titles_final
    assert "宁德时代电池业绩" in titles_final


# ---------- to_yaml_dict 结构校验 ----------
def test_fetch_result_to_yaml_dict(load_module):
    module = load_module("editorial_fetcher")
    r = module.EditorialFetchResult(
        generated_at="2026-04-20T10:00:00",
        content_date="2026-04-20",
    )
    r.etf_cards["513120"] = {"name": "港股创新药", "research_cards": ["💡 卡片1", "💡 卡片2"]}
    r.macro_cards["domestic-policy-card"] = {"title": "🇨🇳 国内政策", "items": ["条目A", "条目B"]}

    out = r.to_yaml_dict()
    assert out["content_date"] == "2026-04-20"
    assert out["etf_cards"]["513120"]["freshness_policy"] == "manual_daily"
    assert out["etf_cards"]["513120"]["research_cards"] == ["💡 卡片1", "💡 卡片2"]
    assert out["macro_cards"]["domestic-policy-card"]["freshness_policy"] == "manual_daily"
    assert out["macro_cards"]["domestic-policy-card"]["title"] == "🇨🇳 国内政策"
    assert out["macro_cards"]["domestic-policy-card"]["items"] == ["条目A", "条目B"]


# ---------- Source 扩展：富途港股 ----------
def test_futu_stock_news_parse(load_module):
    module = load_module("editorial_fetcher")
    html = """
    <html><body>
      <div class="news-item"><a href="/news/123">某条新闻04/20 19:45</a></div>
      <div class="news-item"><a href="/news/124">另一条消息04/20 18:30</a></div>
      <div class="news-item"><a href="/news/125">短</a></div>  <!-- too short, skip -->
    </body></html>
    """
    with patch.object(module, "http_get", return_value=html):
        src = module.FutuStockNewsSource(
            code="01177", stock_name="中国生物制药",
            headers={"User-Agent": "x"}, top_n=10,
        )
        items = src.fetch()
    # 不含"短"（因 len < 6）
    assert len(items) == 2
    assert items[0].source == "futu_hk:01177:中国生物制药"
    assert "新闻" in items[0].title or "消息" in items[0].title
    # 时间后缀被切掉
    assert "04/20" not in items[0].title
    assert items[0].date == "04/20 19:45"
    # URL 拼接
    assert items[0].url.startswith("https://www.futunn.com/")


def test_futu_stock_news_handles_failures(load_module):
    module = load_module("editorial_fetcher")
    with patch.object(module, "http_get", return_value=None):
        src = module.FutuStockNewsSource("01177", "中国生物制药", {})
        assert src.fetch() == []
    with patch.object(module, "http_get", return_value="<html><body>no news</body></html>"):
        src = module.FutuStockNewsSource("01177", "中国生物制药", {})
        assert src.fetch() == []


# ---------- Source 扩展：华尔街见闻 ----------
def test_wscn_lives_parse(load_module):
    import json as _json
    module = load_module("editorial_fetcher")
    fake = _json.dumps({
        "code": 20000,
        "data": {
            "items": [
                {"title": "美联储维持利率不变",
                 "uri": "https://wallstreetcn.com/x/1",
                 "display_time": 1776688000},
                {"title": "",
                 "content_text": "央行公开市场操作 <b>逆回购</b> 5000亿",
                 "uri": "https://wallstreetcn.com/x/2",
                 "display_time": 1776687000},
            ]
        }
    })
    with patch.object(module, "http_get", return_value=fake):
        src = module.WallStreetCnLivesSource(
            channel="global-channel", name="全球", headers={"User-Agent": "x"},
        )
        items = src.fetch()
    assert len(items) == 2
    assert items[0].title == "美联储维持利率不变"
    assert items[0].source == "wscn_lives:global-channel:全球"
    # 第二条用 content_text 兜底，且 HTML 标签被剥
    assert "央行公开市场操作" in items[1].title
    assert "<b>" not in items[1].title


def test_wscn_lives_handles_non200_code(load_module):
    import json as _json
    module = load_module("editorial_fetcher")
    fake = _json.dumps({"code": 60324, "message": "invalid", "data": {}})
    with patch.object(module, "http_get", return_value=fake):
        src = module.WallStreetCnLivesSource(channel="global-channel", name="全球", headers={})
        assert src.fetch() == []


# ---------- Source 扩展：东财综合搜索 ----------
def test_em_article_search_parse(load_module):
    import json as _json
    module = load_module("editorial_fetcher")
    fake = 'jQuery(' + _json.dumps({
        "code": 0,
        "result": {
            "article": [
                {"title": "创新药BD交易创新高", "url": "https://x.com/1",
                 "showTime": "2026-04-20 10:30", "mediaName": "东方财富"},
                {"title": "礼来豪掷300亿", "url": "https://x.com/2",
                 "showTime": "2026-04-20 09:15"},
            ]
        }
    }) + ');'
    with patch.object(module, "http_get", return_value=fake):
        src = module.EastMoneyArticleSearchSource(
            keyword="创新药BD", headers={"User-Agent": "x"},
        )
        items = src.fetch()
    assert len(items) == 2
    assert items[0].title == "创新药BD交易创新高"
    assert items[0].date == "2026-04-20 10:30"
    assert items[0].source == "em_article:keyword=创新药BD"


def test_em_article_search_handles_malformed_response(load_module):
    module = load_module("editorial_fetcher")
    # 无 jQuery 壳
    with patch.object(module, "http_get", return_value="not jsonp"):
        src = module.EastMoneyArticleSearchSource(keyword="x", headers={})
        assert src.fetch() == []
    # 有壳但非 JSON
    with patch.object(module, "http_get", return_value="jQuery(not_json);"):
        src = module.EastMoneyArticleSearchSource(keyword="x", headers={})
        assert src.fetch() == []


# ---------- fetch_for_etf 支持多源类型 ----------
def test_fetch_for_etf_combines_multiple_sources(monkeypatch, load_module):
    """ETF 配置同时有 top_stocks + futu_hk_stocks + em_keywords 时，三源都应被调用并合并。"""
    module = load_module("editorial_fetcher")

    # 拦截三种 source 的 fetch
    sina_called = {"n": 0}
    futu_called = {"n": 0}
    em_called = {"n": 0}

    def sina_fetch(self):
        sina_called["n"] += 1
        return [module.RawItem(title=f"新浪港股-{self.symbol}-创新药获批", url="u",
                               date="2026-04-20", source=f"sina:{self.symbol}")]

    def futu_fetch(self):
        futu_called["n"] += 1
        return [module.RawItem(title=f"富途港股-{self.code}-BD 授权消息", url="u",
                               date="04/20 10:00", source=f"futu:{self.code}")]

    def em_fetch(self):
        em_called["n"] += 1
        return [module.RawItem(title=f"东财-{self.keyword}-礼来合作", url="u",
                               date="2026-04-20", source=f"em:{self.keyword}")]

    monkeypatch.setattr(module.SinaStockNewsSource, "fetch", sina_fetch)
    monkeypatch.setattr(module.FutuStockNewsSource, "fetch", futu_fetch)
    monkeypatch.setattr(module.EastMoneyArticleSearchSource, "fetch", em_fetch)

    cfg = {
        "top_stocks": [
            {"symbol": "hk01177", "stock_name": "中国生物制药"},
            {"symbol": "hk01093", "stock_name": "石药集团"},
        ],
        "futu_hk_stocks": [
            {"code": "01177", "stock_name": "中国生物制药"},
        ],
        "em_keywords": ["创新药BD", "礼来"],
        "require_keywords": ["创新药", "BD", "礼来"],
        "exclude_keywords": [],
    }
    fetcher_cfg = {"per_stock_top_n": 40, "per_etf_kept_n": 10,
                   "inter_request_delay": 0, "request_timeout": 10,
                   "em_search_limit": 15}

    rules = module.load_rules()
    final, stats = module.fetch_for_etf("513120", cfg, headers={}, rules=rules,
                                        fetcher_cfg=fetcher_cfg)
    # 两次新浪 + 一次富途 + 两次东财 = 5 次调用，每次 1 条 = 5 条 raw
    assert sina_called["n"] == 2
    assert futu_called["n"] == 1
    assert em_called["n"] == 2
    assert stats["raw_count"] == 5
    # 所有 title 都命中 require keywords
    assert stats["after_topic_filter"] == 5


# ---------- fetch_for_macro_card 支持 wscn_lives ----------
def test_fetch_for_macro_card_wscn_source(monkeypatch, load_module):
    module = load_module("editorial_fetcher")

    def wscn_fetch(self):
        return [module.RawItem(title=f"华尔街见闻-{self.channel}-美联储降息",
                               url="u", date="2026-04-20", source=f"wscn:{self.channel}")]

    monkeypatch.setattr(module.WallStreetCnLivesSource, "fetch", wscn_fetch)

    card_cfg = {
        "title": "🌐 国际",
        "sources": [
            {"type": "wscn_lives", "channel": "global-channel", "name": "全球", "keep_top": 30},
        ],
        "require_keywords": ["美联储", "降息"],
        "exclude_keywords": [],
        "keep_n": 4,
    }
    rules = module.load_rules()
    final, stats = module.fetch_for_macro_card(
        "global-news-card", card_cfg, headers={}, rules=rules,
        fetcher_cfg={"inter_request_delay": 0, "request_timeout": 10},
    )
    assert stats["raw_count"] == 1
    assert stats["final"] == 1
    assert "美联储" in final[0]["title"]
