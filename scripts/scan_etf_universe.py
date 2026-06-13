"""
REQ-274: ETF pool auto-screening pipeline.
Usage: python scripts/scan_etf_universe.py [--debug] [--force-refresh]
  --debug: generate outputs/etf_screening_debug.xlsx
"""
import sys, json, re, time, os, argparse
from pathlib import Path
from collections import defaultdict
from datetime import datetime

PROJECT_ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / "config").is_dir() and (parent / "scripts").is_dir())
DATA_DIR = PROJECT_ROOT / "data" / "quant"
SCREEN_DIR = PROJECT_ROOT / "data" / "screening"
VOL_CACHE = SCREEN_DIR / "step2_amount.json"
SINA_URL = "https://hq.sinajs.cn/list="
SINA_HDR = {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn/"}

parser = argparse.ArgumentParser()
parser.add_argument("--debug", action="store_true")
parser.add_argument("--force-refresh", action="store_true")
args = parser.parse_args()

# ============================================================
# 1. Load ETF universe
# ============================================================
print("[1/4] Loading ETF universe...")
import akshare as ak, pandas as pd, numpy as np, yaml, requests

# Load/cache listing dates (Sina K-line first bar date)
_LISTING_CACHE = SCREEN_DIR / 'step3_listing_dates.json'
_listing_dates = {}
if _LISTING_CACHE.exists():
    _listing_dates = json.load(open(_LISTING_CACHE, 'r', encoding='utf-8'))

df = ak.fund_name_em()
c_col, n_col, t_col = df.columns[0], df.columns[2], df.columns[3]
ETF_RE = re.compile(r'^(159\d{3}|5[1-9]\d{4})$')
df = df[df[c_col].apply(lambda c: bool(ETF_RE.match(str(c))))].copy()
df.columns = ['code','pinyin','name','type','pf']
print(f"  {len(df)} ETF-likes")

# Load AUM cache (fund size from 天天基金, cached 168h)
# Replaces throttled fund_etf_spot_em() (Eastmoney push2).
# Actual fetch deferred to after Step 2 — only for codes with trading volume.
_SPOT_CACHE = SCREEN_DIR / 'step3_aum.json'
s_code = '代码'
s_cap  = '流通市值'
_AUM_MAX_AGE = 168  # 1 week (fund size updates quarterly, not daily)
_spot_age_h = (time.time() - os.path.getmtime(_SPOT_CACHE)) / 3600 if _SPOT_CACHE.exists() else 999
spot = pd.DataFrame()
if _SPOT_CACHE.exists():
    try:
        spot = pd.read_json(_SPOT_CACHE)
        print(f"  Loaded {len(spot)} cached AUM records ({_spot_age_h:.0f}h old)")
    except Exception as e:
        print(f"  [WARN] Failed to load AUM cache: {e}")
        spot = pd.DataFrame()

# ============================================================
# 2. Fetch volume + exchange names from Sina
# ============================================================
print("[2/4] Volume data...")
now = datetime.now()
is_post = now.hour >= 15
cache = {}; fetch_needed = True
if VOL_CACHE.exists() and not args.force_refresh:
    with open(VOL_CACHE) as f: cache = json.load(f)
    age_h = (time.time() - os.path.getmtime(VOL_CACHE)) / 3600
    max_age = 24 if is_post else 4
    codes_all = set(df['code'])
    missing_n = sum(1 for c in codes_all if c not in cache)
    if age_h < max_age and missing_n < len(codes_all) * 0.3:
        fetch_needed = False
        print(f"  Using cache ({len(cache)} ETFs, {age_h:.1f}h old)")

if fetch_needed:
    print(f"  Fetching {len(df)} ETFs via Sina...")
    cache = {}
    codes_sorted = sorted(df['code'])
    market = {c: ('sh' if c.startswith(('51','56','58','52','50')) else 'sz') for c in codes_sorted}
    symbols = [f"{market[c]}{c}" for c in codes_sorted]
    n_total = (len(symbols) + 49) // 50
    for i in range(0, len(symbols), 50):
        batch = symbols[i:i+50]; bn = i // 50 + 1
        try:
            url = f"{SINA_URL}{','.join(batch)}"
            resp = requests.get(url, headers=SINA_HDR, timeout=10)
            resp.encoding = 'gbk'
            for line in resp.text.strip().split('\n'):
                if '=' not in line: continue
                sm = re.match(r'var hq_str_(sh|sz)(\d{6})', line)
                if not sm: continue
                code = sm.group(2)
                qm = re.search(r'"([^"]*)"', line)
                if not qm: continue
                parts = qm.group(1).split(',')
                if len(parts) < 10: continue
                cache[code] = {
                    'name_ex': parts[0],
                    'open': float(parts[1] or 0), 'prev_close': float(parts[2] or 0),
                    'price': float(parts[3] or 0), 'vol': int(float(parts[8] or 0)),
                }
        except Exception as e:
            print(f"  Batch {bn}/{n_total} error: {e}")
        if bn < n_total: time.sleep(1.5)
    SCREEN_DIR.mkdir(exist_ok=True)
    with open(VOL_CACHE, 'w') as f: json.dump(cache, f, ensure_ascii=False)
    print(f"  Cached {len(cache)} ETFs")

# Attach data
df['name_ex'] = df['code'].apply(lambda c: cache.get(c, {}).get('name_ex', ''))
df['vol'] = df['code'].apply(lambda c: cache.get(c, {}).get('vol', 0))
df['price'] = df['code'].apply(lambda c: cache.get(c, {}).get('price', 0))
df['amount'] = df['vol'] * df['price']
df['amount_yi'] = (df['amount'] / 1e8).round(2)

# Fill missing listing dates via code-prefix estimation (fallback until proper batch API found)
# TODO(REQ-278): replace with batch listing date API when available
def _est_listing_date(code):
    if code.startswith('159'):
        return '2020-06-01'  # ~2020 onwards
    elif code.startswith(('513','517','518')):
        return '2021-01-01'
    elif code.startswith(('510','512')):
        return '2014-01-01'  # oldest ETF series
    elif code.startswith(('588','562','563')):
        return '2022-06-01'
    elif code.startswith(('515','516','560','561')):
        return '2020-01-01'
    elif code.startswith('520'):
        return '2024-01-01'
    return '2020-01-01'

for _code in df['code']:
    if not _listing_dates.get(_code):
        _listing_dates[_code] = _est_listing_date(_code)
SCREEN_DIR.mkdir(exist_ok=True)
json.dump(dict(_listing_dates), open(_LISTING_CACHE, 'w'))
print(f"  Listing dates: {sum(1 for v in _listing_dates.values() if v)} ETFs (cached + estimated)")

# Merge AUM data (fund size from 天天基金)
# Fetch missing codes only if cache is stale and amount data available
_spot_map = {}
if len(spot) > 0:
    for _, r in spot.iterrows():
        try:
            sc = str(int(r[s_code])).zfill(6)
            _spot_map[sc] = float(r[s_cap]) / 1e8 if pd.notna(r[s_cap]) else 0
        except: pass

# Fetch missing AUM from 天天基金 (only for codes with meaningful amount)
# Pre-filter: only fetch for codes likely to pass the amount filter (>= 30M)
_missing = [c for c in df['code']
            if c not in _spot_map
            and c in cache
            and cache[c].get('vol', 0) * cache[c].get('price', 0) >= 30_000_000]
if _missing and (_spot_age_h > _AUM_MAX_AGE or args.force_refresh):
    print(f"  Fetching AUM for {len(_missing)} ETFs from 天天基金...")
    try:
        sys.path.insert(0, str(PROJECT_ROOT))
        from _working.fetch_aum_ttjj import fetch_batch as _ttjj_fetch
        _new_aum = _ttjj_fetch(_missing, delay=0.35)
        for k, v in _new_aum.items():
            _spot_map[k] = v
        # Save updated cache
        _rows = [{'代码': str(k).zfill(6), '流通市值': v * 1e8}
                 for k, v in _spot_map.items()]
        spot = pd.DataFrame(_rows)
        spot.to_json(_SPOT_CACHE, force_ascii=False)
        print(f"  Saved {len(_spot_map)} AUM records")
    except Exception as e:
        print(f"  [WARN] 天天基金 fetch failed: {e}")

if _spot_map:
    df['mcap_yi'] = df['code'].apply(lambda c: _spot_map.get(c, 0))
else:
    # Fallback: uniform amount proxy — no pool-specific data
    df['mcap_yi'] = df['amount_yi'] * 0.5

# Estimate daily_rows from listing date (metadata) or market cap proxy
df['list_date'] = df['code'].apply(lambda c: _listing_dates.get(c, ''))
from datetime import datetime as _dt
def _est_rows(ld):
    if ld:
        try:
            days = (_dt.now() - _dt.strptime(str(ld)[:10], '%Y-%m-%d')).days
            return max(int(days * 0.65), 1)
        except: pass
    return 0
df['daily_rows'] = df['list_date'].apply(_est_rows)

# ============================================================
# 3. Combined filter
# ============================================================
print("[3/4] Filtering...")
BAD_TYPES = ('固收','货币','债')  # type field contains these -> exclude

def passes_filter(r):
    if r['amount'] < 30_000_000: return False, 'amount<30M'
    ftype = str(r['type'])
    for kw in BAD_TYPES:
        if kw in ftype: return False, 'excluded: ' + kw
    return True, ''

reasons = []
keep_mask = []
for _, r in df.iterrows():
    ok, reason = passes_filter(r)
    reasons.append(reason)
    keep_mask.append(ok)

df['filter_reason'] = reasons
df['_keep'] = keep_mask
df_filtered = df[df['_keep']].copy()
df_filtered = df_filtered.drop(columns=['_keep'])
df = df.drop(columns=['_keep'])
print(f"  {len(df)} -> {len(df_filtered)} (removed {len(df)-len(df_filtered)})")

# ============================================================
# 4. Classification + Holdings dedup + Selection
# ============================================================
print("[4/4] Classifying & selecting...")

# Load holdings (independent cache, NOT pool data)
_HCACHE = SCREEN_DIR / 'step4_holdings.json'
holdings_data = json.load(open(_HCACHE, 'r', encoding='utf-8')) if _HCACHE.exists() else {}
def hs(code):
    top10 = holdings_data.get(code, [])
    return {h['code'] for h in top10 if 'code' in h}
def exch(code):
    return 'sh' if code.startswith(('51','56','58','52','50')) else 'sz'

# Name groups — must cover ALL ETFs, zero "其他"
# Ordering is critical: more specific patterns first, catchalls later.
# HK groups before A-share; 消费电子 before 电子; 金融科技 before 科技.
NAME_GROUPS = [
    # === QDII by country/region ===
    # US: sector keywords first, then broad-market catchall (treated like 宽基)
    ('QD-美国-科技', ['纳指科技','纳斯达克科技']),
    ('QD-美国-油气', ['标普.*油气','标普.*原油']),
    ('QD-美国-生物', ['标普.*生物','标普.*生科']),
    ('QD-美国-消费', ['标普.*消费']),
    ('QD-美国-宽基', ['纳指','标普','道琼斯','美国.*50','纳斯达克']),
    ('QD-日本', ['日经','东证']),
    ('QD-韩国', ['韩国','中韩']),
    ('QD-德国', ['德国']), ('QD-法国', ['法国']), ('QD-沙特', ['沙特']),
    ('QD-巴西', ['巴西']), ('QD-印度', ['印度']), ('QD-越南', ['越南']),
    ('QD-东南亚', ['东南亚']), ('QD-亚太', ['亚太']),
    ('QD-中概互联', ['中概.*互联','海外.*互联','中国互联']),
    # === HK by theme ===
    ('HK-医药', ['港股.*药','香港.*药','恒生.*药','恒生.*医','港股通.*药','港股通.*医']),
    ('HK-金融', ['港股.*券','香港.*券','港股.*非银','香港.*非银','港股.*金融','香港.*金融']),
    ('HK-银行', ['港股.*银行','香港.*银行','恒生.*银行']),
    ('HK-红利', ['港股红利','香港红利','恒生红利','港股通红利','港股通.*红利','恒生.*红利']),
    ('HK-红利低波', ['港股.*低波','香港.*低波','恒生.*低波']),
    ('HK-信息技术', ['港股.*信息','港股通.*信息','香港.*信息','恒生.*信息']),
    ('HK-互联网', ['港股.*互联网','港股通.*互联网','香港.*互联网','恒生.*互联网','中概.*互联','中国互联']),
    ('HK-消费', ['港股.*消费','香港.*消费','恒生.*消费','港股通.*消费']),
    ('HK-科技', ['港股.*科','香港.*科','恒生.*科','港股通.*科','港股通.*新经济']),
    ('HK-房地产', ['港股.*地产','香港.*地产','恒生.*地产']),
    ('HK-汽车', ['港股.*汽车','香港.*汽车']),
    ('HK-能源', ['港股.*能源','香港.*能源']),
    ('HK-高股息', ['港股.*高股息','港股通.*高股息','恒生.*高股息','港股.*高息','港股通.*高息']),
	    ('HK-国企', ['港股.*国企','恒生.*国企','港股通.*国企']),
    ('HK-宽基', ['恒生ETF','恒生指数','港股通ETF','港股通指数','港股通.*50','港股通.*100','港股.*100','香港.*30','恒生']),
    # === A-share: industry sectors (specific sub-groups first) ===
    ('消费电子', ['消费电子','消电']),
    ('芯片', ['芯片','半导体','集成电路','电子']),
    ('医药-创新药', ['创新药','生物医药']),
    ('医药-中药', ['中药']),
    ('医药-器械', ['医疗器械','医械','医疗设备']),
    ('医药', ['医药','医疗','生物','疫苗']),
    ('金融-保险', ['保险']), ('金融-证券', ['证券','券商']),
    ('金融-银行', ['银行']), ('金融-非银', ['非银']),
    ('金融科技', ['金融科技']),
    ('金融', ['金融']),  # broad financial catchall (after all specific subgroups)
    ('消费-酒', ['酒']),
    ('消费-食品', ['食品','饮料','国货']),
    ('消费', ['消费']),
    ('消费-家电', ['家电']), ('消费-旅游', ['旅游']),
    ('新能源-光伏', ['光伏']), ('新能源-电池', ['电池']),
    ('新能源-电力', ['电力']), ('新能源-电网', ['电网']),
    ('新能源-风电', ['风电']), ('新能源-储能', ['储能']),
    ('新能源', ['新能源']),
    ('军工', ['军工','国防','航空','通用航空']), ('传媒', ['传媒']), ('游戏', ['游戏']),
    ('煤炭', ['煤炭']), ('钢铁', ['钢铁']), ('化工', ['化工']),
    ('工业母机', ['工业母机','机床']),
    ('机械', ['机械','工程机械']), ('石油', ['石油','石化']),
    ('房地产', ['地产','房地产']),
    ('农业-养殖', ['养殖','畜牧']),
    ('农业-种植', ['粮食','种植','种业']),
    ('农业', ['农业','农牧','农产品','现代农业']),
    ('有色-稀土', ['稀土','稀有金属','稀金']),
    ('有色', ['有色','矿业','工业金属']),
    ('黄金', ['黄金','金ETF','上海金']), ('豆粕', ['豆粕']), ('油气', ['油气','原油']),
    ('通信', ['通信','5G','电信']),
    ('计算机AI', ['计算机','软件','大数据','云计算','数字经济','信创','人工智能','AI','科技','信息','VR']),
    ('汽车', ['汽车','新能源车','智能车','智能驾驶']),
    ('机器人', ['机器人']), ('基建建材', ['基建','建材']),
    ('电力公用', ['电力','公用事业']),
    ('物流运输', ['运输','物流']),
    ('环保碳中和', ['环保','碳中和','绿电']),
    ('卫星航天', ['卫星','航天']), ('船舶', ['船舶']),
    ('动漫游戏', ['动漫']), ('影视', ['影视']),
    ('新材料', ['新材料']),
    ('资源', ['资源','大宗商品']), ('能源', ['能源']),
    ('高端装备', ['高端装备','智能制造','战略新兴']),
    # === Financial / Style / Thematic (catchall order) ===
    ('红利', ['红利']),
    ('高股息', ['高股息','高息']),  # A-share high-dividend (HK version above)
    ('现金流', ['自由现金流','现金流']),
    ('央企国企', ['央企','国企','国企改革']),
    ('一带一路', ['一带一路']), ('专精特新', ['专精特新']),
    ('ESG', ['ESG','可持续发展','责任投资']), ('沪深港', ['沪深港']),
    ('教育', ['教育']), ('区域经济', ['经济圈','成渝','都市经济圈']),
    # === Style (very broad, must be AFTER all sector groups) ===
    ('风格', ['成长','价值','质量']),
    # === Broad-market (excluded except micro-cap 563300) ===
    ('宽基指数', ['沪深300','上证50','中证500','中证1000','中证2000','创业板',
                '科创50','科创100','科创200','深证100','深100','上证180','A50',
                'MSCI','中证100','A100','A500','深证50','上证综指','中证全指',
                '国证2000','科创综指','科创创业','上证指数','中小100','中证800',
                '双创50','创业大盘','TMT50','TMT','央企50','红利低波100',
                '深成','深证成指','深证基本面','基本面','纳斯达克','创50','国证','A股','科创增强','创新100']),
]

def classify(row):
    name = str(row['name']); code = str(row['code'])
    for grp, kws in NAME_GROUPS:
        for kw in kws:
            if re.search(kw, name):
                if grp == '宽基指数' and code == '563300':
                    return '微盘'
                return grp
    # Fallback: use type field (should be rare after comprehensive NAME_GROUPS)
    ftype = str(row['type'])
    return '其他-' + ftype.replace('型-','-')

df_filtered['cg'] = df_filtered.apply(classify, axis=1)
# Load pool codes early (needed for broad-market exemption)
with open(PROJECT_ROOT / 'config/quant_universe.yaml', 'r', encoding='utf-8') as f:
    cfg = yaml.safe_load(f)
pool_codes = {e['code'] for e in cfg['universe']}
# Remove broad-market ETFs (except pool ETFs and 微盘/563300)
# QD-美国-宽基 = US broad-market (纳指/标普/道琼斯) treated like A-share 宽基指数
BROAD_CGS = {'宽基指数', '风格', 'QD-美国-宽基'}
df_filtered['_is_broad'] = df_filtered['cg'].isin(BROAD_CGS) & (~df_filtered['code'].isin(pool_codes)) & (df_filtered['code'] != '563300')
n_broad = df_filtered['_is_broad'].sum()
df_filtered = df_filtered[~df_filtered['_is_broad']]

# Count unclassified
n_other = (df_filtered['cg'].str.startswith('其他-')).sum()
print(f"  Groups: {df_filtered['cg'].nunique()} (removed {n_broad} broad/style ETFs)")
if n_other == 0:
    print(f"  *** ZERO unclassified ETFs ***")
else:
    print(f"  *** WARNING: {n_other} unclassified ETFs remain ***")
    for _, r in df_filtered[df_filtered['cg'].str.startswith('其他-')].iterrows():
        print(f"    {r['code']} | {r['name']} | type={r['type']}")

# ============================================================
# Step 3: Top-1 per coarse group (by daily turnover)
# ============================================================
import math
def etf_score(amt_yi, rows, aum_yi=0.01):
    return (0.25 * math.log10(max(amt_yi, 0.01))
          + 0.45 * math.log10(max(rows, 1))
          + 0.30 * math.log10(max(aum_yi, 0.01)))

_aum_map = {}
for _code in df_filtered['code']:
    _aum = df_filtered[df_filtered['code'] == _code]['mcap_yi'].values[0]
    _aum_map[_code] = _aum if _aum > 0 else 0.01

df_filtered['log_score'] = df_filtered.apply(
    lambda r: etf_score(r['amount_yi'], r['daily_rows'], _aum_map.get(r['code'], 0.01)), axis=1)
df_filtered = df_filtered.sort_values('log_score', ascending=False)
top1_per_cg = []
for cg, grp in df_filtered.groupby('cg'):
    top1_per_cg.append(grp.iloc[0].to_dict())
top1_per_cg.sort(key=lambda x: -x['log_score'])

# ============================================================
# Step 4: Greedy overlap reduction
# Iteratively remove the ETF that shares the most duplicate stocks,
# until no stock appears in >= 7 selected ETFs.
# QDII/HK/commodity groups are exempt from elimination.
EXEMPT_PREFIXES = ('QD-',)
EXEMPT_CGS = {'黄金', '豆粕', '油气'}

# Separate exempt (always kept) from candidates (may be eliminated)
exempt = [s for s in top1_per_cg if s['cg'].startswith(EXEMPT_PREFIXES) or s['cg'] in EXEMPT_CGS]
candidates = [s for s in top1_per_cg if s not in exempt]

# Pre-load all A-share holdings
_cand_holdings = {}
for s in candidates:
    _h = hs(s['code'])
    if _h: _cand_holdings[s['code']] = _h

from collections import Counter
def _overlap_score(code, holdings_count):
    """Count how many of this ETF's holdings are duplicates (appear >=2 times)."""
    if code not in _cand_holdings: return 0
    return sum(1 for h in _cand_holdings[code] if h in holdings_count and holdings_count[h] >= 2)

# Build initial counts
holdings_count = Counter()
for s in exempt + candidates:
    if s['code'] in _cand_holdings:
        holdings_count.update(_cand_holdings[s['code']])

removed_pass1 = []  # bottom 1/2, overlap > 5 (O1)
removed_pass2 = []  # greedy, max_overlap >= 8 (O2)

# First pass: stricter overlap check on bottom 1/2 by log_score
if candidates:
    candidates.sort(key=lambda s: s.get('log_score', 0))  # low to high
    cutoff = len(candidates) // 2
    low_quartile = candidates[:cutoff]
    for s in low_quartile:
        if s not in candidates: continue
        if _overlap_score(s['code'], holdings_count) > 5:
            candidates.remove(s)
            removed_pass1.append(s['code'])
            holdings_count = Counter()
            for _s in exempt + candidates:
                if _s['code'] in _cand_holdings:
                    holdings_count.update(_cand_holdings[_s['code']])

# Second pass: greedy reduction on remaining candidates until max_overlap < 9
while True:
    scores = [(s, _overlap_score(s['code'], holdings_count)) for s in candidates]
    max_score = max(s[1] for s in scores) if scores else 0
    if max_score < 8:
        break
    worst = max(scores, key=lambda x: (x[1], -x[0].get('log_score', 0)))
    worst_etf = worst[0]
    candidates.remove(worst_etf)
    removed_pass2.append(worst_etf['code'])
    holdings_count = Counter()
    for s in exempt + candidates:
        if s['code'] in _cand_holdings:
            holdings_count.update(_cand_holdings[s['code']])

kept = exempt + candidates

# Print overlap statistics
if 'holdings_count' in dir():
    _dist = Counter()
    for _h, _c in holdings_count.items():
        if _c >= 2: _dist[_c] += 1
    print(f"  Overlap after reduction: {sum(_dist.values())} duplicate stocks across {len(kept)} ETFs")
    for _k in sorted(_dist.keys(), reverse=True):
        print(f"    overlap={_k}: {_dist[_k]} stocks")

deduped = pd.DataFrame(kept) if kept else pd.DataFrame()
sel_codes = set(deduped['code']) if len(deduped) > 0 else set()

# Mark selection in the filtered dataframe
df_filtered['fg'] = df_filtered['cg']
df_filtered['selected'] = df_filtered['code'].apply(lambda c: 'YES' if c in sel_codes else '')
df_filtered['in_pool'] = df_filtered['code'].apply(lambda c: 'YES' if c in pool_codes else '')
overlap = sel_codes & pool_codes
missing = pool_codes - sel_codes

# Count by category
n_qdii = sum(1 for s in kept if s['cg'].startswith('QD-'))
n_hk = sum(1 for s in kept if s['cg'].startswith('HK-'))
n_cmdty = sum(1 for s in kept if s['cg'] in EXEMPT_CGS)
n_a = len(kept) - n_qdii - n_hk - n_cmdty

print(f"  Step 3: {len(top1_per_cg)} ETFs (top-1 per coarse group)")
print(f"  Step 4: {len(kept)} ETFs after overlap reduction (①{len(removed_pass1)} + ②{len(removed_pass2)}, O1=5 O2=8)")
print(f"  Breakdown: QDII={n_qdii}, HK={n_hk}, Commodity={n_cmdty}, A-share={n_a}")
_new_codes_console = sel_codes - pool_codes
print(f"  差异: 重叠{len(overlap)} | 新增{len(_new_codes_console)} | 未入选{len(missing)}")
if missing:
    print(f"  未入选: {sorted(missing)}")
if _new_codes_console:
    _preview = sorted(_new_codes_console)[:12]
    print(f"  新增: {_preview}{'...' if len(_new_codes_console) > 12 else ''}")

# 5. Debug xlsx
# ============================================================
if args.debug:
    print("\n[DEBUG] Generating xlsx...")
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    OUTPUT = PROJECT_ROOT / "outputs" / "etf_screening_debug.xlsx"
    OUTPUT.parent.mkdir(exist_ok=True)
    wb = Workbook()
    wb.remove(wb.active)

    HDR_FILL = PatternFill(start_color="1F2937", end_color="1F2937", fill_type="solid")
    HDR_FONT = Font(name="Consolas", bold=True, color="FFFFFF", size=10)
    RULE_FILL = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid")
    RULE_FONT = Font(name="Consolas", size=9, color="92400E")
    PASS_FILL = PatternFill(start_color="D1FAE5", end_color="D1FAE5", fill_type="solid")
    FAIL_FILL = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")
    GRP_FILLS = [PatternFill(start_color=c, end_color=c, fill_type="solid") for c in
                 ['DBEAFE','EDE9FE','FCE7F3','E0E7FF','FEF3C7','D1FAE5','FEE2E2']]
    thin_border = Border(left=Side(style='thin', color='E5E7EB'),
                         right=Side(style='thin', color='E5E7EB'),
                         top=Side(style='thin', color='E5E7EB'),
                         bottom=Side(style='thin', color='E5E7EB'))

    def rule_row(ws, row, text, ncols):
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=ncols)
        c = ws.cell(row=row, column=1, value=text)
        c.fill = RULE_FILL; c.font = RULE_FONT; c.alignment = Alignment(wrap_text=True)
        for i in range(1, ncols+1): ws.cell(row=row, column=i).fill = RULE_FILL

    def hdr_row(ws, row, cols):
        for i, col in enumerate(cols, 1):
            c = ws.cell(row=row, column=i, value=col)
            c.fill = HDR_FILL; c.font = HDR_FONT; c.alignment = Alignment(horizontal='center')
            c.border = thin_border

    def write_rows(ws, start_row, df_data, cols, group_col=None):
        for idx, (_, r) in enumerate(df_data.iterrows()):
            row = start_row + idx
            for ci, col in enumerate(cols, 1):
                val = r.get(col, '');
                if isinstance(val, float): val = round(val, 2)
                c = ws.cell(row=row, column=ci, value=val)
                c.font = Font(name="Consolas", size=9); c.border = thin_border
            if group_col and group_col in r:
                ghash = hash(str(r[group_col])) % len(GRP_FILLS)
                for ci in range(1, len(cols)+1):
                    ws.cell(row=row, column=ci).fill = GRP_FILLS[ghash]

    # Sheet 1: Full universe
    ws1 = wb.create_sheet("1-全市场ETF")
    cols1 = ['code','name','type','amount_yi']
    rule_row(ws1, 1, '全市场 ETF (fund_name_em + Sina 成交数据). 按成交额降序.', len(cols1))
    hdr_row(ws1, 2, ['代码','名称','类型','成交额(亿)'])
    df1 = df.sort_values('amount', ascending=False)
    write_rows(ws1, 3, df1, cols1, group_col='type')
    for c, w in zip('ABCD', [10,32,24,14]): ws1.column_dimensions[c].width = w


    # Add broad_excluded to original df for Sheet 2
    BROAD_CGS_SET = {'宽基指数', '风格', 'QD-美国-宽基'}
    df['broad_excluded'] = df.apply(
        lambda r: 'YES' if (classify(r) in BROAD_CGS_SET and r['code'] != '563300' and r['code'] not in pool_codes) else '', axis=1
    )

    # Sheet 2: Combined filter (keep all rows, mark excluded in red)
    ws2 = wb.create_sheet("2-基础过滤")
    cols2 = ['code','name','type','amount_yi','filter_reason','broad_excluded']
    rule_row(ws2, 1, '基础过滤: 成交额<1000万 + 固收/货币/债券型 → filter_reason. 宽基/风格 → broad_excluded.', len(cols2))
    rule_row(ws2, 2, f'{len(df)} ETFs, 基础过滤剔除{len(df)-len(df_filtered)-n_broad}支, 宽基/风格排除{n_broad}支, 保留{len(df_filtered)}支', len(cols2))
    hdr_row(ws2, 3, ['代码','名称','类型','成交额(亿)','基础排除原因','宽基/风格排除'])
    for idx, (_, r) in enumerate(df.sort_values('amount', ascending=False).iterrows()):
        row = 4 + idx
        for ci, col in enumerate(cols2, 1):
            val = r.get(col, '');
            if isinstance(val, float): val = round(val, 2)
            c = ws2.cell(row=row, column=ci, value=val)
            c.font = Font(name="Consolas", size=9); c.border = thin_border
        if r['filter_reason']:
            for ci in range(1, len(cols2)+1):
                ws2.cell(row=row, column=ci).fill = FAIL_FILL
    for c, w in zip('ABCDEF', [10,32,24,14,28,16]): ws2.column_dimensions[c].width = w

    # Sheet 3: ALL ETFs per coarse group, sorted by score. Top-1 marked with ★.
    ws3 = wb.create_sheet("3-粗组排名")
    cols3 = ['code','name','type','amount_yi','daily_rows','aum_yi','log_score','cg','top1']
    rule_row(ws3, 1, 'Step 3: 加权得分 = 0.25×log10(成交额亿) + 0.45×log10(数据行数) + 0.30×log10(规模亿)。负分=低活跃/新上市/规模小。★ = 组内第1名。', len(cols3))
    rule_row(ws3, 2, f'筛选：成交额≥3000万 + 排除债/货币/固收类。{df_filtered["cg"].nunique()}个粗组, {len(df_filtered)}支ETF, 每组第1名共{len(top1_per_cg)}支进入Step4', len(cols3))
    hdr_row(ws3, 3, ['代码','名称','类型','成交额(亿)','数据量(行)','规模(流通市值亿)','加权得分','粗组','Top1'])
    df_cg_sorted = df_filtered.sort_values(['cg','log_score'], ascending=[True,False])
    cg_top_codes = {s['code'] for s in top1_per_cg}
    row_idx = 4
    for _, r in df_cg_sorted.iterrows():
        is_top1 = '★' if r['code'] in cg_top_codes else ''
        rows_val = r.get('daily_rows', 0)
        aum_val = round(_aum_map.get(r['code'],0), 2)
        vals = [r['code'], r['name'], r['type'], r['amount_yi'], rows_val,
                aum_val, round(r.get('log_score',0),3), r['cg'], is_top1]
        for ci, val in enumerate(vals, 1):
            if isinstance(val, float): val = round(val, 2)
            c = ws3.cell(row=row_idx, column=ci, value=val)
            c.font = Font(name="Consolas", size=9); c.border = thin_border
        if is_top1:
            for ci in range(1, len(cols3)+1):
                ws3.cell(row=row_idx, column=ci).fill = PatternFill(start_color='FEF3C7', end_color='FEF3C7', fill_type='solid')
        row_idx += 1
    for c, w in zip('ABCDEFGHI', [10,32,24,14,12,10,10,22,8]): ws3.column_dimensions[c].width = w

    # Sheet 4: Top-1 ETFs with Chinese holdings + Jaccard PK pairs
    ws4 = wb.create_sheet("4-成分股PK")
    # Pre-fetch missing A-share holdings before xlsx generation
    _missing = [s['code'] for s in top1_per_cg
                if not holdings_data.get(s['code'])
                and not (s['cg'].startswith('QD-') or s['cg'] in EXEMPT_CGS)]
    if _missing:
        print(f"  Fetching holdings for {len(_missing)} new A-share ETFs...")
        # Use a temp meta dict just for the fetch (not pool's etf_metadata.json)
        from fetch_etf_metadata import fetch_one
        _tmp_meta = {}
        for _code in _missing:
            try:
                _etf = {'code': _code, 'name': '', 'market': exch(_code), 'sector': ''}
                _result = fetch_one(_etf, _tmp_meta)
                holdings_data[_code] = _result.get('top10', [])
            except Exception as e:
                print(f'    {_code} FAIL: {e}')
        json.dump(holdings_data, open(_HCACHE, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
        print(f'    Saved holdings for {len(_missing)} new ETFs')

    def get_holding_names(etf_code):
        top10 = holdings_data.get(etf_code, [])
        return [h.get('name', h.get('code','')) for h in top10][:10]
    # Build PK data
    pk_pairs = []
    for i, s1 in enumerate(top1_per_cg):
        cg1 = s1['cg']
        if cg1.startswith(EXEMPT_PREFIXES) or cg1 in EXEMPT_CGS: continue
        for j, s2 in enumerate(top1_per_cg):
            if j <= i: continue
            cg2 = s2['cg']
            if cg2.startswith(EXEMPT_PREFIXES) or cg2 in EXEMPT_CGS: continue
            if exch(s1['code']) != exch(s2['code']): continue
            sa, sb = hs(s1['code']), hs(s2['code'])
            if not sa or not sb: continue
            jac = round(len(sa & sb) / max(1, len(sa | sb)), 3)
            if jac > 0.3:
                pk_pairs.append({'code1':s1['code'],'name1':s1['name'],'cg1':cg1,'amt1':s1['amount_yi'],
                    'code2':s2['code'],'name2':s2['name'],'cg2':cg2,'amt2':s2['amount_yi'],'jaccard':jac})

    # Sort: A-share first, then HK, then others (QDII/commodity)
    def _cat_order(cg):
        if cg.startswith('QD-') or cg in EXEMPT_CGS: return 2
        if cg.startswith('HK-'): return 1
        return 0
    top1_sorted = sorted(top1_per_cg, key=lambda s: (_cat_order(s['cg']), s['cg'], -s['amount_yi']))

    # Build eliminated set (for coloring exclusion)
    _kept_codes = {s['code'] for s in kept}
    _eliminated = {s['code']: 'YES' for s in top1_per_cg if s['code'] not in _kept_codes}

    # Find duplicate holdings across A-share + HK ETFs (exclude eliminated ones)
    ASHARE_HK = [s for s in top1_sorted if _cat_order(s['cg']) < 2 and s['code'] in _kept_codes]
    from collections import Counter
    _holdings_count = Counter()
    for s in ASHARE_HK:
        _is_hk = s['cg'].startswith('HK-')
        for h in get_holding_names(s['code']):
            if h:
                key = h + (' -H' if _is_hk else '')
                _holdings_count[key] += 1
    _dup_names = {h for h, c in _holdings_count.items() if c >= 2}
    _dup_colors = ['FFB3BA','FFDFBA','FFFFBA','BAFFC9','BAE1FF','E8BAFF','FFB3E0','B3FFE0',
                   'FFD700','FF8C69','87CEEB','98FB98','DDA0DD','F0E68C','87CEFA','FFA07A']
    _dup_sorted = sorted(_dup_names, key=lambda n: -_holdings_count[n])
    _dup_fills = {n: PatternFill(start_color=_dup_colors[i % 16], end_color=_dup_colors[i % 16], fill_type='solid')
                  for i, n in enumerate(_dup_sorted)}

    # Build removal order maps from both passes (emoji-prefixed)
    _removed_order = {}
    for _i, _code in enumerate(removed_pass1, 1):
        _removed_order[_code] = f'①{_i}'  # ①1, ①2...
    for _i, _code in enumerate(removed_pass2, 1):
        _removed_order[_code] = f'②{_i}'  # ②1, ②2...

    _total_removed = len(removed_pass1) + len(removed_pass2)

    # Build A-share internal ranking (non-exempt ETFs by log_score desc)
    _ashare_ranked = sorted(
        [s for s in top1_per_cg if _cat_order(s['cg']) < 2],  # A-share + HK only
        key=lambda s: -s.get('log_score', 0)
    )
    _ashare_rank = {s['code']: i+1 for i, s in enumerate(_ashare_ranked)}
    _ashare_cutoff = len(_ashare_ranked) // 2  # bottom 1/2 threshold

    # Main table with 排除(顺序) column
    HCOLS = ['持仓1','持仓2','持仓3','持仓4','持仓5','持仓6','持仓7','持仓8','持仓9','持仓10']
    cols4_header = ['代码','名称','粗组','成交额(亿)','得分','排名','排除'] + HCOLS
    _desc = f'Step 4: ①底1/2({_ashare_cutoff}支) O1>5→淘汰({len(removed_pass1)}支) ②贪心 O2>=8→淘汰({len(removed_pass2)}支). 结果: {len(_kept_codes)}/{len(top1_per_cg)} 入选.'
    rule_row(ws4, 1, _desc, len(cols4_header))
    rule_row(ws4, 2, f'排名=A股内部得分排名(1~{len(_ashare_ranked)}). ①N=第1步淘汰, ②N=第2步淘汰. 底1/2={_ashare_cutoff}名之后. 灰色=已淘汰.', len(cols4_header))
    hdr_row(ws4, 3, cols4_header)
    EXEMPT_BLUE = PatternFill(start_color='DBEAFE', end_color='DBEAFE', fill_type='solid')
    ELIM_FILL = PatternFill(start_color='C0C0C0', end_color='C0C0C0', fill_type='solid')
    for idx, s in enumerate(top1_sorted):
        row = 4 + idx
        rank_val = _ashare_rank.get(s['code'], '-')
        vals = [s['code'], s['name'], s['cg'], s['amount_yi'], round(s.get('log_score',0),3),
                rank_val, _removed_order.get(s['code'], '')]
        elim_label = vals[-1]  # elimination order, empty if kept
        hnames = get_holding_names(s['code'])
        is_hk = s['cg'].startswith('HK-')
        if is_hk:
            hnames = [h + ' -H' for h in hnames]  # suffix HK holdings
        if _cat_order(s['cg']) == 2:
            hnames = []  # QDII/commodity: no holdings display
        vals += hnames + ['']*(10-len(hnames))
        for ci, val in enumerate(vals, 1):
            if isinstance(val, float): val = round(val, 2)
            c = ws4.cell(row=row, column=ci, value=val)
            c.font = Font(name="Consolas", size=9); c.border = thin_border
        if elim_label:
            for ci in range(1, len(cols4_header)+1):
                ws4.cell(row=row, column=ci).fill = ELIM_FILL
        elif _cat_order(s['cg']) == 2:
            for ci in range(1, len(cols4_header)+1):
                ws4.cell(row=row, column=ci).fill = EXEMPT_BLUE
        elif not elim_label:
            # Color duplicate holdings (only for kept ETFs)
            for ci in range(6, len(cols4_header)+1):
                val = ws4.cell(row=row, column=ci).value
                if val in _dup_fills:
                    ws4.cell(row=row, column=ci).fill = _dup_fills[val]

    # Remove bottom PK pairs table — now just a summary line
    rule_row(ws4, 6 + len(top1_sorted), f'淘汰 {_total_removed} 支: ①底1/2(O1>5)={len(removed_pass1)}支 + ②贪心(O2>=8)={len(removed_pass2)}支. 灰色=已淘汰.', len(cols4_header))

    # PK pairs summary now inline in main table (see 排除 column)

    widths4 = [10,30,22,14,10,8,8] + [10]*10
    for i, w in enumerate(widths4): ws4.column_dimensions[get_column_letter(i+1)].width = w

    # Sheet 5: Full diff — selected + missing pool, with status labels
    ws5 = wb.create_sheet("5-差异对照")
    NEW_FILL  = PatternFill(start_color='D1FAE5', end_color='D1FAE5', fill_type='solid')  # green: new
    POOL_FILL = PatternFill(start_color='FFF3CD', end_color='FFF3CD', fill_type='solid')  # yellow: pool
    MISS_FILL = PatternFill(start_color='FEE2E2', end_color='FEE2E2', fill_type='solid')  # red: missing
    NEW_FONT  = Font(name='Consolas', size=9, bold=True, color='065F46')

    cols5 = ['code','name','type','amount_yi','cg','status']
    _new_codes = sel_codes - pool_codes
    n_new = len(_new_codes)

    # Build elimination info for recommendation logic
    _elim_info = {}
    for _e in removed_pass1:
        _elim_info[_e] = ('①', _ashare_rank.get(_e, 0))
    for _e in removed_pass2:
        _elim_info[_e] = ('②', _ashare_rank.get(_e, 0))

    def _recommend(status, code, amount_yi):
        """Generate acceptance recommendation (unified: 纳入=接受新增, 剔除=接受移除)."""
        amt = amount_yi if amount_yi else 0
        if status == '缺失':
            # Pool ETF not selected → recommend REMOVING it
            if amt < 0.3:
                return '强烈推荐接受', '剔除：成交量<30M不达标'
            info = _elim_info.get(code)
            if info:
                label, rank = info
                if label == '①':
                    return '推荐接受', f'剔除：底半区淘汰 rank={rank}'
                else:
                    return '中立', f'剔除：贪心削峰淘汰 rank={rank}'
            return '中立', '剔除：组内PK落选，需人工判断替代'
        elif status == '新增':
            # Not in pool but selected → recommend ADDING it
            if amt >= 5:
                return '强烈推荐接受', f'纳入：高流动性 {amt:.0f}亿'
            elif amt >= 1:
                return '推荐接受', f'纳入：流动性达标 {amt:.1f}亿'
            elif amt >= 0.5:
                return '中立', f'纳入：流动性偏低 {amt:.2f}亿'
            else:
                return '推荐不接受', f'纳入：流动性不足 {amt:.2f}亿'
        else:
            return '—', '已覆盖，无需操作'

    # Build combined list: selected ETFs first, then missing pool ETFs
    _combined = []
    for s in kept:
        entry = dict(s)
        entry['status'] = '新增' if s['code'] in _new_codes else '池内'
        rec, rec_reason = _recommend(entry['status'], s['code'], s.get('amount_yi', 0))
        entry['recommend'] = rec
        entry['rec_reason'] = rec_reason
        _combined.append(entry)
    # Add missing pool ETFs (not selected)
    for code in sorted(missing):
        _row = df[df['code'] == code]
        if len(_row) > 0:
            r = _row.iloc[0]
            rec, rec_reason = _recommend('缺失', code, r['amount_yi'])
            entry = {'code': code, 'name': r['name'], 'type': r['type'],
                     'amount_yi': r['amount_yi'], 'cg': classify(r), 'status': '缺失',
                     'recommend': rec, 'rec_reason': rec_reason}
            _combined.append(entry)

    _combined.sort(key=lambda s: ({'池内':0,'新增':1,'缺失':2}[s['status']], s['cg'], -s['amount_yi']))

    # Recommendation color map (unified: acceptance level)
    REC_FILLS = {
        '强烈推荐接受': PatternFill(start_color='065F46', end_color='065F46', fill_type='solid'),
        '推荐接受':     PatternFill(start_color='10B981', end_color='10B981', fill_type='solid'),
        '中立':         PatternFill(start_color='FCD34D', end_color='FCD34D', fill_type='solid'),
        '推荐不接受':   PatternFill(start_color='F97316', end_color='F97316', fill_type='solid'),
        '强烈不推荐接受': PatternFill(start_color='DC2626', end_color='DC2626', fill_type='solid'),
        '—':           None,
    }
    REC_FONTS = {
        '强烈推荐接受': Font(name='Consolas', size=9, bold=True, color='FFFFFF'),
        '推荐接受':     Font(name='Consolas', size=9, bold=True, color='FFFFFF'),
        '强烈不推荐接受': Font(name='Consolas', size=9, bold=True, color='FFFFFF'),
        '推荐不接受':   Font(name='Consolas', size=9, bold=True, color='FFFFFF'),
        '中立':         Font(name='Consolas', size=9, color='92400E'),
    }

    cols5 = ['code','name','type','amount_yi','cg','status','recommend']
    ncols5 = len(cols5)
    n_rec = {'强烈推荐接受':0,'推荐接受':0,'中立':0,'推荐不接受':0,'强烈不推荐接受':0}
    for s in _combined:
        r = s.get('recommend', '—')
        if r in n_rec: n_rec[r] += 1
    desc5 = f'差异对照: {len(kept)}入选 | 新增{n_new}(绿) | 已覆盖{len(overlap)}(黄) | 未入选{len(missing)}(红). 筛选=新基线. 接受度: ++{n_rec["强烈推荐接受"]} +{n_rec["推荐接受"]} ~{n_rec["中立"]} -{n_rec["推荐不接受"]}'
    rule_row(ws5, 1, desc5, ncols5)
    hdr_row(ws5, 3, ['代码','名称','类型','成交额(亿)','粗组','状态','接受建议'])

    for idx, s in enumerate(_combined):
        row = 4 + idx
        vals = [s['code'], s['name'], s.get('type',''), s['amount_yi'], s['cg'], s['status'], s.get('recommend','')]
        for ci, val in enumerate(vals, 1):
            if isinstance(val, float): val = round(val, 2)
            c = ws5.cell(row=row, column=ci, value=val)
            c.font = Font(name="Consolas", size=9); c.border = thin_border
        if s['status'] == '新增':
            for ci in range(1, ncols5+1):
                ws5.cell(row=row, column=ci).fill = NEW_FILL
            ws5.cell(row=row, column=1).font = NEW_FONT
        elif s['status'] == '池内':
            for ci in range(1, ncols5+1):
                ws5.cell(row=row, column=ci).fill = POOL_FILL
        elif s['status'] == '缺失':
            for ci in range(1, ncols5+1):
                ws5.cell(row=row, column=ci).fill = MISS_FILL
        # Color recommendation column
        rec = s.get('recommend', '')
        rec_fill = REC_FILLS.get(rec)
        rec_font = REC_FONTS.get(rec)
        if rec_fill:
            ws5.cell(row=row, column=7).fill = rec_fill
        if rec_font:
            ws5.cell(row=row, column=7).font = rec_font

    for c, w in zip('ABCDEFG', [10,30,24,14,22,10,18]): ws5.column_dimensions[c].width = w

    os.system('taskkill /f /im excel.exe 2>nul')
    import time; time.sleep(1)
    wb.save(str(OUTPUT))
    print(f"  Saved: {OUTPUT}")
    os.system(f'start excel "{OUTPUT}"')

