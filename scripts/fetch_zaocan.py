#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
早参抓取脚本（零第三方依赖）
数据来源：
    - 新浪财经外盘指数（美股/商品期货/外汇/全球股指）
    - 东方财富 7x24 财经快讯（含摘要、关联板块、时间）
    - 上海证券报·中国证券网 早间要闻（宏观/政策/公司）

用法：
    python scripts/fetch_zaocan.py                # 生成今天的早参
    python scripts/fetch_zaocan.py --force        # 重新生成今天的早参

输出：
    index.html          早参页（即首页，今天）
    zaocan/index.json   早参数据（供后续读取）

说明：
    - 幂等：当天已生成则默认跳过，重复运行无副作用
    - 设计在每天早上 8:00（北京时间）由 GitHub Actions 触发
"""

import argparse
import html as htmllib
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from site_frame import (BRAND, CLOCK_SCRIPT,  # noqa: E402
                        render_footer, render_header)

ROOT = Path(__file__).resolve().parent.parent
ZAOCAN_DIR = ROOT / 'zaocan'
INDEX_JSON = ZAOCAN_DIR / 'index.json'
OUT_HTML = ROOT / 'index.html'   # 早参直接作为首页

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
      'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36')

# 新浪财经外盘代码表：代码 -> (显示名, 分组)
# gb_ = 美股/ETF, hf_ = 外盘商品期货, znb_ = 全球主要股指, fx_ = 外汇
SINA_QUOTES = [
    ('gb_dji', '道琼斯', '美股'),
    ('gb_ixic', '纳斯达克', '美股'),
    ('gb_inx', '标普500', '美股'),
    ('gb_yang', 'A50三倍做空', 'A股对冲'),
    ('hf_CL', 'NYMEX原油', '商品'),
    ('hf_GC', 'COMEX黄金', '商品'),
    ('fx_susdcny', '人民币兑美元', '外汇'),
    ('znb_NKY', '日经225', '亚太'),
]

WEEKDAYS = ['星期一', '星期二', '星期三', '星期四', '星期五', '星期六', '星期日']


def log(msg):
    print('[%s] %s' % (datetime.now().strftime('%H:%M:%S'), msg), flush=True)


def http_get(url, timeout=30, retries=3, referer=None):
    for i in range(retries):
        try:
            headers = {'User-Agent': UA}
            if referer:
                headers['Referer'] = referer
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            log('HTTP %s %s（第 %d 次）' % (e.code, url, i + 1))
        except Exception as e:
            log('请求失败 %s：%s（第 %d 次）' % (url, e, i + 1))
        time.sleep(2 * (i + 1))
    return None


def fetch_global_quotes():
    """抓外盘指数（新浪财经），返回 [{'name','value','chg','pct','group'}, ...]"""
    codes = ','.join(q[0] for q in SINA_QUOTES)
    url = 'https://hq.sinajs.cn/list=' + codes
    data = http_get(url, referer='https://finance.sina.com.cn/')
    if not data:
        return []
    text = data.decode('gbk', errors='replace')
    name_map = {q[0]: (q[1], q[2]) for q in SINA_QUOTES}
    out = []
    for m in re.finditer(r'hq_str_(\w+)="([^"]*)"', text):
        code = m.group(1)
        if code not in name_map:
            continue
        name, group = name_map[code]
        fields = m.group(2).split(',')
        if len(fields) < 4:
            continue
        value = None
        pct = None
        chg = None
        try:
            if code.startswith('gb_'):
                # gb: 名称,现价,涨跌幅,时间,涨跌额,...
                value = float(fields[1])
                pct = float(fields[2])
                chg = float(fields[4])
            elif code.startswith('hf_'):
                # hf: 现价,买价,卖价,最高,最低,时间,昨结算,开盘,...
                value = float(fields[0])
                pct = None
                chg = None
                if len(fields) >= 8 and fields[7]:
                    try:
                        prev = float(fields[7])
                        if prev:
                            chg = value - prev
                            pct = chg / prev * 100
                    except (ValueError, IndexError):
                        pass
            elif code.startswith('znb_'):
                # znb: 名称,现价,涨跌额,涨跌幅,时间,...
                value = float(fields[1])
                chg = float(fields[2])
                pct = float(fields[3])
            elif code.startswith('fx_'):
                # fx: 时间,现价,买价,卖价,成交量,昨收,开盘,最高,最低,名称,涨跌额,涨跌幅,...
                value = float(fields[1])
                chg = float(fields[10])
                pct = float(fields[11])
        except (ValueError, IndexError):
            pass
        out.append({'name': name, 'value': value, 'chg': chg, 'pct': pct, 'group': group})
    return out


def clean_html(t):
    t = re.sub(r'<[^>]+>', '', t)
    t = htmllib.unescape(t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def fetch_fast_news(page_size=50):
    """抓东方财富 7x24 财经快讯，返回 [{'time','title','summary','stockList'}, ...]"""
    url = ('https://np-listapi.eastmoney.com/comm/web/getFastNewsList'
           '?client=web&biz=web_724&fastColumn=102&sortEnd=&pageSize=%d'
           '&req_trace=%d' % (page_size, int(time.time() * 1000)))
    data = http_get(url, referer='https://kuaixun.eastmoney.com/')
    if not data:
        return []
    try:
        obj = json.loads(data.decode('utf-8', errors='replace'))
        items = obj['data']['fastNewsList']
    except Exception as e:
        log('解析快讯失败：%s' % e)
        return []
    out = []
    for it in items:
        out.append({
            'time': it.get('showTime', ''),
            'title': clean_html(it.get('title', '')),
            'summary': clean_html(it.get('summary', '')),
            'stocks': it.get('stockList') or [],
            'important': bool(it.get('titleColor')),
            'code': str(it.get('code', '')),
            'source': 'eastmoney',
        })
    return out


def fetch_cnstock_yaowen():
    """抓上证报·中国证券网首页要闻标题，返回 [{'title','url'}, ...]"""
    url = 'https://www.cnstock.com/'
    data = http_get(url, referer='https://www.cnstock.com/')
    if not data:
        return []
    text = data.decode('utf-8', errors='replace')
    items = []
    seen = set()
    # 文章结构形如 <a href="/commonDetail/784463" ...><div ...>标题</div></a>
    # 标题嵌在 <a> 内层的 <div> 文本节点，需跨标签匹配
    for m in re.finditer(
            r'<a[^>]*href="(/commonDetail/\d+)"[^>]*>(?:(?!</a>).)*?<div[^>]*>([^<]{6,80})</div>',
            text, re.S):
        href, title = m.group(1), clean_html(m.group(2))
        if not title or href in seen:
            continue
        seen.add(href)
        items.append({'title': title, 'url': 'https://www.cnstock.com' + href})
    return items[:20]


def fetch_stcn_yaowen():
    """抓证券时报首页要闻（服务端渲染，标题/链接可直接提取）。
    返回 [{'title','url'}, ...]，url 为文章详情页。"""
    url = 'https://www.stcn.com/'
    data = http_get(url, referer='https://www.stcn.com/')
    if not data:
        return []
    text = data.decode('utf-8', errors='replace')
    items = []
    seen = set()
    for m in re.finditer(r'<a[^>]*href="(/article/detail/\d+\.html)"[^>]*>([^<]{6,80})</a>', text):
        href, title = m.group(1), clean_html(m.group(2))
        if not title or href in seen:
            continue
        seen.add(href)
        items.append({'title': title, 'url': 'https://www.stcn.com' + href})
    return items[:30]


def filter_overnight(items, now=None):
    """时间窗口过滤：只保留隔夜消息（上一交易日收盘 → 今日 08:00）。

    早参目标是"开盘前速览"，只关心隔夜（A 股收盘后到今早开盘前）发生的事。
    东财快讯的 time 字段形如 '2026-09-01 21:35:12'。

    边界处理：
    - 周一（weekday=0）往前推到上周五 15:00，覆盖整个周末；
    - 其余工作日往前推到昨天 15:00。
    """
    now = now or datetime.now()
    today = now.date()
    wd = today.weekday()
    # 下界：上一个交易日收盘时间 15:00
    back_days = 3 if wd == 0 else 1  # 周一往前推 3 天到周五
    lo = datetime.combine(today - timedelta(days=back_days),
                          datetime.min.time()).replace(hour=15, minute=0)
    # 上界：今日 08:00（开盘前）
    hi = datetime.combine(today, datetime.min.time()).replace(hour=8, minute=0)
    out = []
    for it in items:
        ts = it.get('time', '')
        if not ts:
            # 无时间的（如 cnstock/stcn 首页要闻）不在此处过滤，单独处理
            out.append(it)
            continue
        try:
            t = datetime.strptime(ts[:19], '%Y-%m-%d %H:%M:%S')
        except ValueError:
            out.append(it)
            continue
        if lo <= t <= hi:
            out.append(it)
    return out


def _extract_entities(title):
    """提取标题里的"强实体"词，用于跨源匹配。

    强实体 = 公司/机构专名（含股份/科技/生物/医疗/电气/汽车/证券/银行/保险/
    能源/电子/半导体/材料 等后缀），或明确的主体名。
    这些词一旦跨源同时出现，几乎可以确定是同一事件，误匹配率低。
    （"央行/加息/出口"这类高频泛词不纳入，避免误匹配。）
    """
    pats = [
        r'[\u4e00-\u9fa5]{2,8}(?:股份|科技|生物|医疗|医药|电气|汽车|证券|银行|保险|能源|电子|半导体|材料|化工|钢|铝|锂|钴|地产|控股|集团|实业|重工)',
    ]
    ents = set()
    for p in pats:
        ents.update(re.findall(p, title))
    # 过滤掉明显不是实体的通用词
    drop = {'公司股份', '中国汽车', '本次股份', '这些股份', 'A股', '港股', '科技巨头',
            '科技公司', '半导体', '汽车板块', '新能源汽车'}
    ents -= drop
    return ents


def _tokenize(title):
    """提取标题里的核心片段，用于跨源标题包含匹配（辅助）。"""
    s = re.sub(r'[，。、；：！？（）\[\]【】“”"\'·\s]', '', title)
    s = re.sub(r'[0-9]{1,2}月[0-9]{1,2}日|[0-9:：]+', '', s)
    return s


def cross_source_score(items):
    """多源交叉验证：统计每条消息被几个信息源"共同报道"。

    策略：对东财快讯（源 A，主源）逐条与其他源（证券时报 B、上证报 C）的标题做
    实体匹配。被越多源报道的消息越重要，额外加权。
    匹配分两级：
      1) 强实体命中（公司/机构专名跨源同时出现）—— 高分，可信
      2) 标题包含（短标题互相包含）—— 中分
    返回 {index: extra_score} 映射。
    """
    src_a = [i for i in range(len(items)) if items[i].get('source') == 'eastmoney']
    src_b = [i for i in range(len(items)) if items[i].get('source') == 'stcn']
    src_c = [i for i in range(len(items)) if items[i].get('source') == 'cnstock']
    if not src_a or not (src_b or src_c):
        return {}

    # 预提取其他源的实体与 token
    other = []  # (index, entity_set, token)
    for i in src_b + src_c:
        ti = items[i]['title']
        other.append((i, _extract_entities(ti), _tokenize(ti)))

    extra = {}
    for i in src_a:
        ta = _tokenize(items[i]['title'])
        ea = _extract_entities(items[i]['title'])
        if not ta:
            continue
        hits = 0
        hit_via_entity = set()
        for _, eb, tb in other:
            matched = False
            # 1) 强实体命中
            if ea and eb and (ea & eb):
                matched = True
                hit_via_entity |= (ea & eb)
            # 2) 标题包含（辅助，需足够长避免误匹配）
            elif ta and tb and (len(ta) >= 6 and len(tb) >= 6) and (ta in tb or tb in ta):
                matched = True
            if matched:
                hits += 1
        if hits:
            # 每多一个源报道 +22 分
            extra[i] = 22 * hits
    return extra


# 标题党/纯感叹词：只删"突发/刚刚/大消息"这类纯情绪感叹词，
# 保留"重挫/暴跌/跳水/大涨"等事实性动词（它们承载了涨跌信息，删了标题就不通顺）
CLICKBAIT_WORDS = ['突发', '刚刚', '大消息', '重磅', '震惊', '沸腾', '炸锅',
                   '疯抢', '狂飙', '暴富', '一夜', '惊天', '罕见', '史无前例',
                   '注意了', '紧急', '速看', '一文', '猛料', '直线拉升']


def _clean_clickbait(title):
    """清洗标题党词与多余标点，返回更克制的标题。"""
    t = title
    for w in CLICKBAIT_WORDS:
        t = t.replace(w, '')
    # 去掉残留的孤立/连续标点与空格
    t = re.sub(r'[，、；：]{2,}', '，', t)
    t = re.sub(r'[！？]{2,}', '', t)
    t = re.sub(r'[，、；：]+\s*[！？]', '', t)
    t = re.sub(r'^[，、；：！？\s]+', '', t)
    t = re.sub(r'[，、；：！？\s]+$', '', t)
    t = re.sub(r'\s+', ' ', t)
    return t if t else title


def _core_words(title):
    """提取标题的核心实义词（中文 2-gram），用于同事件去重。

    用双字 n-gram 而非单字，保留"加息/日韩/股市/央行"等词的完整语义，
    避免单字切分导致语义丢失和误匹配。
    """
    t = _clean_clickbait(title)
    # 去数字/百分比
    t = re.sub(r'[0-9]+(?:\.\d+)?%?', '', t)
    # 只保留中文汉字
    t = re.sub(r'[^\u4e00-\u9fff]', '', t)
    # 常见停用字（单字，在 n-gram 前过滤意义不大，但去掉纯虚词组成的 gram）
    stop2 = {'一个', '进行', '以及', '这个', '我们', '他们', '表示', '认为', '公司',
             '集团', '股份', '有限', '对于', '关于', '通过', '其中', '目前', '已经',
             '预计', '相关', '上述', '分别', '继续', '出现', '发布', '公告', '显示',
             '市场', '股市', '今日', '昨日', '明日', '今年', '去年', '上半年', '下半年'}
    grams = set()
    for i in range(len(t) - 1):
        g = t[i:i + 2]
        if g in stop2:
            continue
        grams.add(g)
    return grams


# 事件主题词：同一栏目内，命中同一个"明确事件词"的多条消息视为同一事件的碎片报道，
# 只保留最高分一条。注意：只用"明确事件词"（加息/降息/降准这类），不用泛机构词
# （央行/证监会，因为同一机构一天可能有多件不同的事）。
THEME_EVENTS = ['加息', '降息', '降准', '美联储', '逆回购', 'MLF', 'LPR', '国债',
                '关税', '汇率', '油价', '金价', '退市', '立案', '爆雷', '违约']


def _dedup_similar(items, threshold=0.45):
    """同栏目内去重，分两层：
    1) 精确去重：核心词（2-gram）重叠度超过阈值，视为同一事件（如重复抓取）；
    2) 事件聚类：命中同一个"事件主题词"（如加息/降准），视为同一波行情的碎片报道。
    两层都只保留分数最高的一条。
    """
    if len(items) <= 1:
        return items
    items = sorted(items, key=lambda x: x.get('score', 0), reverse=True)
    kept = []
    used_theme = set()  # 已占用的事件主题词
    for it in items:
        # 第一层：精确 2-gram 重叠去重
        dup = False
        cw = _core_words(it['title'])
        for k in kept:
            kw = _core_words(k['title'])
            if not cw or not kw:
                continue
            inter = len(cw & kw)
            union = len(cw | kw)
            jac = inter / union if union else 0
            if jac >= threshold and inter >= 2:
                dup = True
                break
        if dup:
            continue
        # 第二层：事件主题词聚类
        theme = None
        for t in THEME_EVENTS:
            if t in it['title']:
                theme = t
                break
        if theme and theme in used_theme:
            continue  # 该主题已有更高分条目，丢弃碎片
        if theme:
            used_theme.add(theme)
        kept.append(it)
    return kept


def classify_news(items):
    """把快讯按栏目分拣，只保留重要消息（三重筛选：时间窗口 + 关键词加权 + 标红加分）。

    返回 dict：栏目名 -> [条目列表]，每个条目含 score 字段（用于排序）。
    不再产生"其他快讯"杂项栏——命中不了核心栏目的直接丢弃。
    """
    # 关键词分级（关键词 -> 栏目, 权重）
    # 权重越高越重要，命中即得分；强信号词额外大幅加分
    STRONG = ['降准', '降息', '加息', '重磅', '突发', '央行', '国务院', '政治局',
              '国常会', '证监会', '立案', '退市', '爆雷', '违约', '停牌', '复牌',
              '重组', '收购', '并购', '涨停', '跌停']
    RULES = [
        # (关键词, 栏目, 权重)
        ('央行', '宏观要闻', 30),
        ('降准', '宏观要闻', 40),
        ('降息', '宏观要闻', 40),
        ('加息', '宏观要闻', 35),
        ('MLF', '宏观要闻', 30),
        ('LPR', '宏观要闻', 30),
        ('逆回购', '宏观要闻', 28),
        ('财政部', '宏观要闻', 25),
        ('国务院', '宏观要闻', 32),
        ('政治局', '宏观要闻', 35),
        ('国常会', '宏观要闻', 33),
        ('发改委', '宏观要闻', 22),
        ('证监会', '宏观要闻', 30),
        ('银保监', '宏观要闻', 25),
        ('统计局', '宏观要闻', 20),
        ('PMI', '宏观要闻', 24),
        ('CPI', '宏观要闻', 24),
        ('GDP', '宏观要闻', 22),
        ('商务部', '宏观要闻', 18),
        ('工信部', '宏观要闻', 18),
        ('住建部', '宏观要闻', 18),
        ('海关', '宏观要闻', 15),
        ('外汇', '宏观要闻', 18),
        ('财政', '宏观要闻', 20),
        ('预算', '宏观要闻', 20),
        ('税收', '宏观要闻', 18),
        ('消费', '宏观要闻', 16),
        ('外贸', '宏观要闻', 16),
        ('进出口', '宏观要闻', 16),
        ('社融', '宏观要闻', 22),
        ('信贷', '宏观要闻', 18),
        ('利率', '宏观要闻', 20),
        ('国债', '宏观要闻', 20),
        ('汇率', '宏观要闻', 18),
        # 重磅公告
        ('停牌', '重磅公告', 32),
        ('复牌', '重磅公告', 32),
        ('重组', '重磅公告', 30),
        ('收购', '重磅公告', 26),
        ('并购', '重磅公告', 26),
        ('回购', '重磅公告', 22),
        ('增持', '重磅公告', 22),
        ('减持', '重磅公告', 24),
        ('中标', '重磅公告', 20),
        ('业绩', '重磅公告', 18),
        ('净利', '重磅公告', 18),
        ('定增', '重磅公告', 22),
        ('可转债', '重磅公告', 20),
        ('分红', '重磅公告', 18),
        # 板块异动
        ('涨价', '板块异动', 22),
        ('供需', '板块异动', 20),
        ('紧缺', '板块异动', 22),
        ('缺口', '板块异动', 20),
        ('扩产', '板块异动', 18),
        ('排产', '板块异动', 18),
        ('满产', '板块异动', 18),
        ('获批', '板块异动', 18),
        ('突破', '板块异动', 16),
        ('景气', '板块异动', 16),
        ('订单', '板块异动', 16),
        # 风险提示
        ('退市', '风险提示', 38),
        ('立案', '风险提示', 35),
        ('爆雷', '风险提示', 35),
        ('违约', '风险提示', 33),
        ('处罚', '风险提示', 30),
        ('违规', '风险提示', 28),
        ('调查', '风险提示', 28),
        ('下调', '风险提示', 20),
        ('预警', '风险提示', 20),
        ('亏损', '风险提示', 20),
        ('预亏', '风险提示', 22),
        ('ST', '风险提示', 24),
    ]

    buckets = {'宏观要闻': [], '重磅公告': [], '板块异动': [], '风险提示': []}

    # 多源交叉验证：被多个源共同报道的消息，大幅加分
    cross_extra = cross_source_score(items)

    for idx, it in enumerate(items):
        t = it['title'] + it['summary']
        best_cat = None
        best_score = 0
        # 关键词匹配，取最高分栏目
        for kw, cat, w in RULES:
            if kw in t:
                score = w
                if kw in STRONG:
                    score += 10  # 强信号词额外加分
                if score > best_score:
                    best_score = score
                    best_cat = cat
        if best_cat is None:
            continue  # 命中不了核心栏目的，丢弃（杂七杂八不放）
        # 东方财富编辑标红 = 重要，额外加分
        if it.get('important'):
            best_score += 15
        # 多源交叉验证加分（多个源都报道 = 更重要）
        if idx in cross_extra:
            best_score += cross_extra[idx]
            it['multi_source'] = cross_extra[idx] // 22  # 记录被几个额外源命中
        it['score'] = best_score
        buckets[best_cat].append(it)

    # 每个栏目按分数降序，同事件去重，再过滤低分 + 每栏最多 8 条
    for cat in buckets:
        buckets[cat].sort(key=lambda x: x.get('score', 0), reverse=True)
        # 同事件去重（同一波行情被多家/多篇报道，只留最高分一条）
        buckets[cat] = _dedup_similar(buckets[cat])
        # 过滤：分数太低的丢弃；每栏最多 8 条
        buckets[cat] = [x for x in buckets[cat] if x.get('score', 0) >= 18][:8]
        # 标题党清洗（仅影响展示，不影响排序）
        for x in buckets[cat]:
            x['title'] = _clean_clickbait(x['title'])
    return buckets


def load_xwlb_latest():
    """读取新闻联播索引，返回最新一条（用于首页入口卡片）。"""
    p = ROOT / 'xwlb' / 'index.json'
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding='utf-8'))
    except Exception:
        return None
    if not isinstance(data, list) or not data:
        return None
    return data[0]


def item_link(it):
    """按来源拼原文链接，返回 (url, target)。无链接时返回 ('', '')。"""
    code = it.get('code', '')
    source = it.get('source', '')
    if source == 'eastmoney' and code:
        return 'https://finance.eastmoney.com/a/%s.html' % htmllib.escape(code), \
            ' target="_blank" rel="noopener"'
    if source in ('cnstock', 'stcn') and code:
        return htmllib.escape(code), ' target="_blank" rel="noopener"'
    return '', ''


def render_page(d, quotes, buckets):
    ds = d.isoformat()
    date_cn = '%d 年 %d 月 %d 日' % (d.year, d.month, d.day)
    weekday = WEEKDAYS[d.weekday()]

    # 焦点头条（新闻联播）
    xwlb = load_xwlb_latest()
    xwlb_count = 0
    if xwlb:
        cover = xwlb.get('cover', '')
        xwlb_date = xwlb.get('date', '')
        xwlb_weekday = xwlb.get('weekday', '')
        xwlb_count = xwlb.get('count', 0)
        titles = xwlb.get('titles', [])[:3]
        cover_html = ('<img src="%s" alt="%s 新闻联播" loading="lazy">'
                      % (htmllib.escape(cover), htmllib.escape(xwlb_date))) if cover else ''
        title_items = ''.join('<li>%s</li>' % htmllib.escape(t) for t in titles)
        xwlb_card = (
            '<a class="lead" href="/xwlb/%s.html">'
            '<div class="lead-media">%s<span class="lead-tag">新闻联播</span></div>'
            '<div class="lead-body">'
            '<h2>《新闻联播》主要内容</h2>'
            '<ul class="lead-points">%s</ul>'
            '<div class="lead-foot"><span>%s · %s</span><span>央视网</span>'
            '<span class="more">共 %d 条 · 阅读全文 →</span></div>'
            '</div></a>'
            % (htmllib.escape(xwlb_date), cover_html,
               title_items, htmllib.escape(xwlb_date), htmllib.escape(xwlb_weekday),
               xwlb_count))
    else:
        xwlb_card = '<div class="lead lead-empty">新闻联播内容暂未更新，今晚播出后自动上线。</div>'

    # 外盘
    quote_rows = []
    for q in quotes:
        pct = q.get('pct')
        if pct is None:
            cls = 'flat'
            sign = ''
            pct_str = '--'
        else:
            pct = float(pct)
            cls = 'up' if pct > 0 else ('down' if pct < 0 else 'flat')
            sign = '+' if pct > 0 else ''
            pct_str = '%s%.2f%%' % (sign, pct)
        val = q.get('value')
        is_fx = q.get('group') == '外汇'
        if isinstance(val, (int, float)):
            val_str = ('%.4f' % val) if is_fx else ('%.2f' % val)
        else:
            val_str = '--'
        quote_rows.append(
            '<div class="tick"><span class="t-name">%s</span>'
            '<span class="t-val">%s</span>'
            '<span class="t-chg %s">%s</span></div>'
            % (htmllib.escape(q['name']), val_str, cls, pct_str))

    # 栏目
    sections = []
    order = [('宏观要闻', '🏛️'), ('重磅公告', '📋'), ('板块异动', '📈'),
             ('风险提示', '⚠️')]
    for name, icon in order:
        items = buckets.get(name, [])
        if not items:
            continue
        rows = []
        for it in items[:8]:
            time_str = it.get('time', '')
            if time_str and len(time_str) >= 16:
                time_str = time_str[11:16]
            link, target = item_link(it)
            time_html = ('<span class="it-time">%s</span>' % htmllib.escape(time_str)
                         if time_str else '')
            if link:
                rows.append('<li><a href="%s"%s>%s%s</a></li>'
                            % (link, target, time_html, htmllib.escape(it['title'])))
            else:
                rows.append('<li><span class="it-plain">%s%s</span></li>'
                            % (time_html, htmllib.escape(it['title'])))
        sections.append(
            '<section class="block"><h2 class="block-title">%s'
            '<span class="num">%d</span></h2>'
            '<ul class="feed">%s</ul></section>'
            % (name, len(items), '\n'.join(rows)))

    # 侧栏「热点排行」：重要的排前面，再按栏目顺序补齐，去重取 10 条
    pool = []
    for name, _icon in order:
        for it in buckets.get(name, []):
            pool.append((1 if it.get('important') else 0, it))
    pool.sort(key=lambda x: -x[0])
    hot, seen = [], set()
    for _w, it in pool:
        key = it.get('title', '')
        if key in seen:
            continue
        seen.add(key)
        hot.append(it)
        if len(hot) >= 10:
            break
    hot_rows = []
    for i, it in enumerate(hot, 1):
        link, target = item_link(it)
        cls = ' class="rank-item top"' if i <= 3 else ' class="rank-item"'
        text = '<span class="rank-text">%s</span>' % htmllib.escape(it['title'])
        if link:
            hot_rows.append('<a%s href="%s"%s><span class="rank-no">%02d</span>%s</a>'
                            % (cls, link, target, i, text))
        else:
            hot_rows.append('<div%s><span class="rank-no">%02d</span>%s</div>'
                            % (cls, i, text))

    # 侧栏「外盘速览」（竖排，与顶部行情条同源）
    side_rows = []
    for q in quotes[:8]:
        pct = q.get('pct')
        if pct is None:
            cls, pct_str = 'flat', '--'
        else:
            pct = float(pct)
            cls = 'up' if pct > 0 else ('down' if pct < 0 else 'flat')
            pct_str = '%s%.2f%%' % ('+' if pct > 0 else '', pct)
        val = q.get('value')
        is_fx = q.get('group') == '外汇'
        val_str = ('%.4f' % val if is_fx else '%.2f' % val) \
            if isinstance(val, (int, float)) else '--'
        side_rows.append(
            '<div class="side-quote"><span class="sq-name">%s</span>'
            '<span class="sq-val">%s</span>'
            '<span class="sq-chg %s">%s</span></div>'
            % (htmllib.escape(q['name']), val_str, cls, pct_str))

    html = PAGE_TEMPLATE
    for token, value in [
        ('__TITLE__', '%s 市场要闻 · %s' % (date_cn, BRAND)),
        ('__DATE_CN__', date_cn),
        ('__WEEKDAY__', weekday),
        ('__STAT_XWLB__', str(xwlb_count)),
        ('__STAT_MARKET__', str(sum(len(v) for v in buckets.values()))),
        ('__STAT_QUOTES__', str(len(quotes))),
        ('__HEADER__', render_header('home')),
        ('__FOOTER__', render_footer(
            note='数据来源：东方财富网、证券时报、上海证券报·中国证券网等公开信息，'
                 '版权归原作者所有，本页仅作个人投资参考，<strong>不构成任何投资建议</strong>。')),
        ('__CLOCK_SCRIPT__', CLOCK_SCRIPT),
        ('__FOCUS__', xwlb_card),
        ('__QUOTES__', '\n'.join(quote_rows)),
        ('__SECTIONS__', '\n'.join(sections)),
        ('__HOT_LIST__', '\n'.join(hot_rows)),
        ('__SIDE_QUOTES__', '\n'.join(side_rows)),
    ]:
        html = html.replace(token, value)
    return html


PAGE_TEMPLATE = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>__TITLE__</title>
    <meta name="description" content="__DATE_CN__ 市场要闻速览：宏观、公告与风险提示。">
    <link rel="stylesheet" href="assets/style.css">
</head>
<body>
__HEADER__

    <main class="portal">
        <div class="portal-main">
            <header class="page-head">
                <div class="ph-main">
                    <div class="page-kicker">__DATE_CN__ · __WEEKDAY__</div>
                    <h1>今日新闻</h1>
                </div>
                <div class="stat-row">
                    <div class="stat"><b>__STAT_XWLB__</b><span>联播条目</span></div>
                    <div class="stat"><b>__STAT_MARKET__</b><span>市场要闻</span></div>
                    <div class="stat"><b>__STAT_QUOTES__</b><span>外盘指标</span></div>
                </div>
            </header>

__FOCUS__

            <section class="ticker">
__QUOTES__
            </section>

__SECTIONS__
        </div>

        <aside class="portal-side">
            <div class="side-card">
                <div class="side-title">热点排行</div>
                <div class="rank-list">
__HOT_LIST__
                </div>
            </div>

            <div class="side-card">
                <div class="side-title">外盘速览</div>
__SIDE_QUOTES__
            </div>
        </aside>
    </main>

__FOOTER__
    <script>__CLOCK_SCRIPT__</script>
    <script defer src="https://api.xhja.cn/stats.js?site=news"></script>
</body>
</html>
'''


def update_index(d, quotes, buckets):
    ds = d.isoformat()
    summary = {}
    for name in buckets:
        summary[name] = len(buckets[name])
    entry = {
        'date': ds,
        'weekday': WEEKDAYS[d.weekday()],
        'quotes': quotes,
        'summary': summary,
        'url': 'index.html',
        'generated': datetime.now().strftime('%Y-%m-%d %H:%M'),
    }
    ZAOCAN_DIR.mkdir(parents=True, exist_ok=True)
    INDEX_JSON.write_text(json.dumps(entry, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description='早参抓取')
    parser.add_argument('--force', action='store_true', help='重新生成今天的早参')
    args = parser.parse_args()

    d = date.today()
    ds = d.isoformat()
    if OUT_HTML.exists() and not args.force:
        log('%s：早参已存在，跳过（--force 可重新生成）' % ds)
        return

    log('抓取隔夜外盘指数……')
    quotes = fetch_global_quotes()
    log('外盘拿到 %d 项' % len(quotes))

    log('抓取东方财富 7x24 财经快讯……')
    news = fetch_fast_news(60)
    log('快讯拿到 %d 条' % len(news))

    # 时间窗口过滤：只保留隔夜（昨 15:00 → 今 08:00）的快讯
    before = len(news)
    news = filter_overnight(news)
    log('隔夜时间窗口过滤后剩 %d 条（原 %d）' % (len(news), before))

    # 补充证券时报要闻（源 B）
    stcn = fetch_stcn_yaowen()
    if stcn:
        for s in stcn:
            news.append({'time': '', 'title': s['title'], 'summary': '',
                         'stocks': [], 'important': False,
                         'code': s['url'], 'source': 'stcn'})
        log('证券时报要闻补充 %d 条' % len(stcn))

    # 补充上证报要闻（源 C，可选，失败不阻塞）
    cnstock = fetch_cnstock_yaowen()
    if cnstock:
        for c in cnstock:
            url = c.get('url', '')
            if url.startswith('/'):
                url = 'https://www.cnstock.com' + url
            news.append({'time': '', 'title': c['title'], 'summary': '',
                         'stocks': [], 'important': False,
                         'code': url, 'source': 'cnstock'})
        log('上证报要闻补充 %d 条' % len(cnstock))

    buckets = classify_news(news)
    for name, items in buckets.items():
        log('  %s：%d 条' % (name, len(items)))

    html_text = render_page(d, quotes, buckets)
    ZAOCAN_DIR.mkdir(parents=True, exist_ok=True)
    OUT_HTML.write_text(html_text, encoding='utf-8')
    update_index(d, quotes, buckets)

    log('早参生成完成：%s（外盘 %d 项，快讯 %d 条）' % (OUT_HTML.name, len(quotes), len(news)))


if __name__ == '__main__':
    main()
