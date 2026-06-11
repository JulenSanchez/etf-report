"""
REQ-274: ETF pool auto-screening pipeline.
Usage: python scripts/scan_etf_universe.py [--debug] [--force-refresh]
  --debug: generate outputs/etf_screening_debug.xlsx
"""
import sys, json, re, time, os, argparse
from pathlib import Path
from collections import defaultdict
from datetime import datetime

SKILL_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = SKILL_DIR / "data" / "quant"
WORK_DIR = SKILL_DIR / "_working"
VOL_CACHE = WORK_DIR / ".etf_vol_cache.json"
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

df = ak.fund_name_em()
c_col, n_col, t_col = df.columns[0], df.columns[2], df.columns[3]
ETF_RE = re.compile(r'^(159\d{3}|5[1-9]\d{4})$')
df = df[df[c_col].apply(lambda c: bool(ETF_RE.match(str(c))))].copy()
df.columns = ['code','pinyin','name','type','pf']
print(f"  {len(df)} ETF-likes")

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
    WORK_DIR.mkdir(exist_ok=True)
    with open(VOL_CACHE, 'w') as f: json.dump(cache, f, ensure_ascii=False)
    print(f"  Cached {len(cache)} ETFs")

# Attach data
df['name_ex'] = df['code'].apply(lambda c: cache.get(c, {}).get('name_ex', ''))
df['vol'] = df['code'].apply(lambda c: cache.get(c, {}).get('vol', 0))
df['price'] = df['code'].apply(lambda c: cache.get(c, {}).get('price', 0))
df['amount'] = df['vol'] * df['price']
df['amount_yi'] = (df['amount'] / 1e8).round(2)

# ============================================================
# 3. Combined filter
# ============================================================
print("[3/4] Filtering...")
BAD_TYPES = ('固收','货币','债')  # type field contains these -> exclude

def passes_filter(r):
    if r['amount'] < 10_000_000: return False, 'amount<10M'
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

# Load holdings
with open(DATA_DIR / 'etf_metadata.json', 'r', encoding='utf-8') as f: meta = json.load(f)
def hs(code):
    m = meta.get(code, {})
    return {h['code'] for h in m.get('top10', []) if 'code' in h}
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
    ('QD-美国-生物', ['标普.*生物']),
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
    ('HK-互联网', ['港股.*互联网','港股通.*互联网','香港.*互联网','恒生.*互联网']),
    ('HK-消费', ['港股.*消费','香港.*消费','恒生.*消费','港股通.*消费']),
    ('HK-科技', ['港股.*科','香港.*科','恒生.*科','港股通.*科','港股通.*新经济']),
    ('HK-房地产', ['港股.*地产','香港.*地产','恒生.*地产']),
    ('HK-汽车', ['港股.*汽车','香港.*汽车']),
    ('HK-能源', ['港股.*能源','香港.*能源']),
    ('HK-高股息', ['港股.*高股息','港股通.*高股息','恒生.*高股息','港股.*高息','港股通.*高息']),
    ('HK-宽基', ['恒生ETF','恒生指数','港股通ETF','港股通指数','港股通.*50','港股通.*100','港股.*100','香港.*30','恒生']),
    # === A-share: industry sectors (specific sub-groups first) ===
    ('消费电子', ['消费电子','消电']),
    ('芯片', ['芯片','半导体','集成电路','电子']),
    ('医药-创新药', ['创新药','生物医药']),
    ('医药-中药', ['中药']),
    ('医药-器械', ['医械']),
    ('医药', ['医药','医疗','生物','疫苗']),
    ('金融-证券', ['证券','券商']), ('金融-银行', ['银行']),
    ('金融-保险', ['保险']), ('金融-非银', ['非银']),
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
    ('农业-种植', ['粮食','农牧','农业','农产品','现代农业']),
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
with open(SKILL_DIR / 'config/quant_universe.yaml', 'r', encoding='utf-8') as f:
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
df_filtered = df_filtered.sort_values('amount', ascending=False)
top1_per_cg = []
for cg, grp in df_filtered.groupby('cg'):
    top1_per_cg.append(grp.iloc[0].to_dict())
top1_per_cg.sort(key=lambda x: -x['amount'])

# ============================================================
# Step 4: Cross-group Jaccard PK
# For each pair of selected ETFs from different A-share groups:
#   if Jaccard(top10 holdings) > 0.7 AND same exchange → keep the higher-volume one
# QDII/HK/commodity groups are exempt (differentiation comes from index rules, not holdings)
# ============================================================
EXEMPT_PREFIXES = ('QD-', 'HK-')
EXEMPT_CGS = {'黄金', '豆粕', '油气'}

kept = []
for s in top1_per_cg:
    cg = s['cg']
    # Exempt categories always pass
    if cg.startswith(EXEMPT_PREFIXES) or cg in EXEMPT_CGS:
        kept.append(s)
        continue

    # Check against all already-kept A-share ETFs
    eliminated = False
    for k in kept:
        kcg = k['cg']
        if kcg.startswith(EXEMPT_PREFIXES) or kcg in EXEMPT_CGS:
            continue
        if exch(s['code']) != exch(k['code']):
            continue
        sa, sb = hs(s['code']), hs(k['code'])
        if not sa or not sb:
            continue
        jac = len(sa & sb) / max(1, len(sa | sb))
        if jac > 0.7:
            # k was processed first (higher volume since sorted descending),
            # so k wins — eliminate s
            eliminated = True
            break
    if not eliminated:
        kept.append(s)

deduped = pd.DataFrame(kept) if kept else pd.DataFrame()
sel_codes = set(deduped['code']) if len(deduped) > 0 else set()

# Mark selection in the filtered dataframe
df_filtered['fg'] = df_filtered['cg']  # fine group = coarse group (no sub-group split)
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
print(f"  Step 4: {len(kept)} ETFs after cross-group PK (removed {len(top1_per_cg)-len(kept)} by holdings overlap)")
print(f"  Breakdown: QDII={n_qdii}, HK={n_hk}, Commodity={n_cmdty}, A-share={n_a}")
print(f"  Pool coverage: {len(overlap)}/{len(pool_codes)} ({len(overlap)/max(1,len(pool_codes))*100:.0f}%)")
if missing:
    print(f"  *** Not in pool: {sorted(missing)} ***")

# ============================================================
# 5. Debug xlsx
# ============================================================
if args.debug:
    print("\n[DEBUG] Generating xlsx...")
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    OUTPUT = SKILL_DIR / "outputs" / "etf_screening_debug.xlsx"
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

    # Sheet 3: ALL ETFs per coarse group, sorted by volume. Top-1 marked with ★.
    ws3 = wb.create_sheet("3-粗组排名")
    cols3 = ['code','name','type','amount_yi','cg','top1']
    rule_row(ws3, 1, 'Step 3: 每个粗分组内按成交额排名。★ = 组内第1名(QDII/HK/商品豁免PK)。', len(cols3))
    rule_row(ws3, 2, f'{df_filtered["cg"].nunique()}个粗组, {len(df_filtered)}支ETF, 每组第1名共{len(top1_per_cg)}支进入Step4', len(cols3))
    hdr_row(ws3, 3, ['代码','名称','类型','成交额(亿)','粗组','Top1'])
    # Build rows: all ETFs sorted by cg then amount desc
    df_cg_sorted = df_filtered.sort_values(['cg','amount'], ascending=[True,False])
    # Determine top-1 per cg
    cg_top_codes = {s['code'] for s in top1_per_cg}
    row_idx = 4
    for _, r in df_cg_sorted.iterrows():
        is_top1 = '★' if r['code'] in cg_top_codes else ''
        vals = [r['code'], r['name'], r['type'], r['amount_yi'], r['cg'], is_top1]
        for ci, val in enumerate(vals, 1):
            if isinstance(val, float): val = round(val, 2)
            c = ws3.cell(row=row_idx, column=ci, value=val)
            c.font = Font(name="Consolas", size=9); c.border = thin_border
        if is_top1:
            for ci in range(1, len(cols3)+1):
                ws3.cell(row=row_idx, column=ci).fill = PatternFill(start_color='FEF3C7', end_color='FEF3C7', fill_type='solid')
        row_idx += 1
    for c, w in zip('ABCDEF', [10,32,24,14,22,8]): ws3.column_dimensions[c].width = w

    # Sheet 4: Top-1 ETFs with Chinese holdings + Jaccard PK pairs
    ws4 = wb.create_sheet("4-成分股PK")
    # Build holdings name mapping
    def get_holding_names(etf_code):
        m = meta.get(etf_code, {})
        return [h.get('name', h.get('code','')) for h in m.get('top10', [])][:10]
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

    # Show all top-1 ETFs first (with Chinese holdings), then PK pairs below
    HCOLS = [f'持仓{i+1}' for i in range(10)]
    cols4 = ['code','name','cg','amount_yi'] + HCOLS
    rule_row(ws4, 1, f'Step 3 入选的 {len(top1_per_cg)} 支ETF + 成分股(中文). 下方为Jaccard>0.3的跨组PK对.', len(cols4))
    hdr_row(ws4, 3, ['代码','名称','粗组','成交额(亿)'] + HCOLS)
    for idx, s in enumerate(top1_per_cg):
        row = 4 + idx
        vals = [s['code'], s['name'], s['cg'], s['amount_yi']]
        hnames = get_holding_names(s['code'])
        vals += hnames + ['']*(10-len(hnames))
        for ci, val in enumerate(vals, 1):
            if isinstance(val, float): val = round(val, 2)
            c = ws4.cell(row=row, column=ci, value=val)
            c.font = Font(name="Consolas", size=9); c.border = thin_border
        if s['cg'].startswith(EXEMPT_PREFIXES) or s['cg'] in EXEMPT_CGS:
            for ci in range(1, len(cols4)+1):
                ws4.cell(row=row, column=ci).fill = PatternFill(start_color='DBEAFE', end_color='DBEAFE', fill_type='solid')

    # PK pairs section
    pk_start = 4 + len(top1_per_cg) + 2
    if pk_pairs:
        rule_row(ws4, pk_start, f'Jaccard > 0.3 跨组对 ({len(pk_pairs)} pairs). 绿色=Jaccard>0.7(会触发淘汰)', len(cols4))
        hdr_row(ws4, pk_start+1, ['代码1','名称1','粗组1','成交额1','代码2','名称2','粗组2','成交额2','Jaccard'])
        pk_cols = ['code1','name1','cg1','amt1','code2','name2','cg2','amt2','jaccard']
        for idx, p in enumerate(sorted(pk_pairs, key=lambda x:-x['jaccard'])):
            row = pk_start + 2 + idx
            for ci, col in enumerate(pk_cols, 1):
                val = p[col]
                if isinstance(val, float): val = round(val, 2)
                c = ws4.cell(row=row, column=ci, value=val)
                c.font = Font(name="Consolas", size=9); c.border = thin_border
            if p['jaccard'] > 0.7:
                for ci in range(1, len(pk_cols)+1):
                    ws4.cell(row=row, column=ci).fill = PASS_FILL
    else:
        rule_row(ws4, pk_start, '无 Jaccard > 0.3 的跨组对。', len(cols4))

    widths4 = [10,30,20,14] + [10]*10
    for i, w in enumerate(widths4): ws4.column_dimensions[get_column_letter(i+1)].width = w    # Sheet 5: Final selection (clean, no holdings)
    ws5 = wb.create_sheet("5-最终入选")
    cols5 = ['code','name','type','amount_yi','cg','selected','in_pool']
    ncols = len(cols5)
    rule_row(ws5, 1, f'最终入选 {len(kept)} 支 (QDII={n_qdii}, HK={n_hk}, 商品={n_cmdty}, A股={n_a}). 池覆盖 {len(overlap)}/{len(pool_codes)} ({len(overlap)/max(1,len(pool_codes))*100:.0f}%).', ncols)
    rule_row(ws5, 2, '绿色=入选, 红色=池内但未入选.', ncols)
    hdr_row(ws5, 3, ['代码','名称','类型','成交额(亿)','粗组','选中','池内'])
    df_sel_sorted = df_filtered.sort_values(['selected','amount'], ascending=[False,False])
    for idx, (_, r) in enumerate(df_sel_sorted.iterrows()):
        row = 4 + idx
        for ci, col in enumerate(cols5, 1):
            val = r.get(col, '');
            if isinstance(val, float): val = round(val, 2)
            c = ws5.cell(row=row, column=ci, value=val)
            c.font = Font(name="Consolas", size=9); c.border = thin_border
        if r['selected'] == 'YES':
            for ci in range(1, ncols+1): ws5.cell(row=row, column=ci).fill = PASS_FILL
        if r['in_pool'] == 'YES' and r['selected'] != 'YES':
            for ci in range(1, ncols+1):
                ws5.cell(row=row, column=ci).fill = FAIL_FILL
    for c, w in zip('ABCDEFG', [10,32,24,14,22,8,8]): ws5.column_dimensions[c].width = w

    wb.save(str(OUTPUT))
    print(f"  Saved: {OUTPUT}")

