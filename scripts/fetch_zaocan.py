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
from datetime import date, datetime
from pathlib import Path

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
        })
    return out


def fetch_cnstock_yaowen():
    """抓上证报·中国证券网首页要闻标题，返回 [{'title','tag','time'}, ...]"""
    url = 'https://www.cnstock.com/'
    data = http_get(url, referer='https://www.cnstock.com/')
    if not data:
        return []
    text = data.decode('utf-8', errors='replace')
    # 首页为 JS 渲染，尝试从内嵌 JSON 或结构化块提取；失败则返回空
    items = []
    # 简单回退：匹配常见标题块
    for m in re.finditer(r'<a[^>]*href="([^"]+)"[^>]*>([^<]{6,80})</a>', text):
        href, title = m.group(1), clean_html(m.group(2))
        if title and ('要闻' in title or '政策' in title or '公告' in title or len(title) >= 8):
            items.append({'title': title, 'url': href, 'time': ''})
    return items[:20]


def classify_news(items):
    """把快讯按栏目分拣：宏观/公告/板块/风险/其他。"""
    macro_kw = ['央行', '财政部', '国务院', '发改委', '证监会', '银保监', '统计局',
                'PMI', 'CPI', 'GDP', 'LPR', '逆回购', 'MLF', '降准', '降息',
                '政治局', '国常会', '商务部', '工信部', '住建部', '海关', '外汇']
    notice_kw = ['回购', '增持', '减持', '中标', '业绩', '净利', '营收', '重组',
                 '停牌', '复牌', '分红', '定增', '可转债', '拟募资', '收购', '并购']
    sector_kw = ['涨价', '供需', '景气', '排产', '扩产', '订单', '突破', '获批',
                 '中标', '创新', '放量', '满产', '紧缺', '缺口']
    risk_kw = ['退市', '处罚', '违规', '立案', '调查', '爆雷', '违约', '下调',
               '预警', '减持', '亏损', '预亏', 'ST']

    buckets = {'宏观要闻': [], '重磅公告': [], '板块异动': [], '风险提示': [], '其他快讯': []}
    for it in items:
        t = it['title'] + it['summary']
        if any(k in t for k in risk_kw):
            buckets['风险提示'].append(it)
        elif any(k in t for k in macro_kw):
            buckets['宏观要闻'].append(it)
        elif any(k in t for k in notice_kw):
            buckets['重磅公告'].append(it)
        elif any(k in t for k in sector_kw):
            buckets['板块异动'].append(it)
        else:
            buckets['其他快讯'].append(it)
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


def render_page(d, quotes, buckets, generated):
    ds = d.isoformat()
    date_cn = '%d 年 %d 月 %d 日' % (d.year, d.month, d.day)
    weekday = WEEKDAYS[d.weekday()]

    # 新闻联播入口卡片
    xwlb = load_xwlb_latest()
    if xwlb:
        cover = xwlb.get('cover', '')
        xwlb_date = xwlb.get('date', '')
        xwlb_weekday = xwlb.get('weekday', '')
        xwlb_count = xwlb.get('count', 0)
        titles = xwlb.get('titles', [])[:3]
        cover_html = ('<img class="xwlb-cover" src="%s" alt="%s 新闻联播" loading="lazy">'
                      % (htmllib.escape(cover), htmllib.escape(xwlb_date))) if cover else ''
        title_items = ''.join('<li>%s</li>' % htmllib.escape(t) for t in titles)
        xwlb_card = (
            '<a class="xwlb-card" href="/xwlb/%s.html">%s'
            '<div class="xwlb-body">'
            '<div class="xwlb-head"><span class="xwlb-tag">新闻联播</span>'
            '<span class="xwlb-date">%s · %s</span></div>'
            '<h3>《新闻联播》主要内容</h3>'
            '<ul class="xwlb-titles">%s</ul>'
            '<span class="xwlb-more">共 %d 条 · 阅读全文 →</span>'
            '</div></a>'
            % (htmllib.escape(xwlb_date), cover_html,
               htmllib.escape(xwlb_date), htmllib.escape(xwlb_weekday),
               title_items, xwlb_count))
    else:
        xwlb_card = '<div class="xwlb-card empty">新闻联播内容暂未更新，今晚播出后自动上线。</div>'

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
            '<div class="qz-item %s"><span class="qz-name">%s</span>'
            '<span class="qz-val">%s</span>'
            '<span class="qz-chg">%s</span></div>'
            % (cls, htmllib.escape(q['name']), val_str, pct_str))

    # 栏目
    sections = []
    order = [('宏观要闻', '🏛️'), ('重磅公告', '📋'), ('板块异动', '📈'),
             ('风险提示', '⚠️'), ('其他快讯', '📰')]
    for name, icon in order:
        items = buckets.get(name, [])
        if not items:
            continue
        cards = []
        for it in items[:12]:
            time_str = it.get('time', '')
            if time_str and len(time_str) >= 16:
                time_str = time_str[11:16]
            summary = it.get('summary', '')
            summary_html = ('<p class="item-summary">%s</p>' % htmllib.escape(summary)
                            if summary else '')
            tag = '<span class="tag-hot">重要</span>' if it.get('important') else ''
            cards.append(
                '<article class="item"><div class="item-head">'
                '<span class="item-time">%s</span>%s<span class="item-title">%s</span></div>%s</article>'
                % (htmllib.escape(time_str), tag,
                   htmllib.escape(it['title']), summary_html))
        sections.append(
            '<section class="sec"><h2 class="sec-title">%s %s <span class="sec-count">%d</span></h2>'
            '<div class="item-list">%s</div></section>'
            % (icon, name, len(items), '\n'.join(cards)))

    html = PAGE_TEMPLATE
    for token, value in [
        ('__TITLE__', '%s 早参 · 徐宏江的小站' % date_cn),
        ('__DATE_CN__', date_cn),
        ('__WEEKDAY__', weekday),
        ('__GENERATED__', generated),
        ('__XWLB_CARD__', xwlb_card),
        ('__QUOTES__', '\n'.join(quote_rows)),
        ('__SECTIONS__', '\n'.join(sections)),
    ]:
        html = html.replace(token, value)
    return html


PAGE_TEMPLATE = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>__TITLE__</title>
    <meta name="description" content="__DATE_CN__ 每日早参：隔夜外盘、宏观要闻、重磅公告、板块异动、风险提示，开盘前速览。">
    <link rel="stylesheet" href="assets/style.css">
    <style>
        :root { --up: #e5484d; --down: #0f9d58; }
        .zc-wrap { max-width: 760px; margin: 0 auto; padding: 0 16px 40px; }
        .zc-hero { margin: 16px 0 20px; padding: 22px 20px; border-radius: 16px;
            background: linear-gradient(135deg, #3b5bdb, #7048e8); color: #fff; }
        .zc-hero .date { font-size: 13px; opacity: .85; }
        .zc-hero h1 { font-size: 24px; margin: 6px 0 4px; }
        .zc-hero .tip { font-size: 13px; opacity: .85; }
        .xwlb-card { display: flex; gap: 14px; background: #fff; border: 1px solid #eee;
            border-radius: 14px; padding: 14px; margin: 0 0 20px; text-decoration: none;
            color: inherit; box-shadow: 0 1px 6px rgba(0,0,0,.05); transition: transform .15s; }
        .xwlb-card:hover { transform: translateY(-2px); }
        .xwlb-card.empty { display: block; color: #999; text-align: center; }
        .xwlb-cover { width: 120px; height: 78px; object-fit: cover; border-radius: 10px; flex-shrink: 0; }
        .xwlb-body { flex: 1; min-width: 0; }
        .xwlb-head { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
        .xwlb-tag { font-size: 11px; color: #fff; background: linear-gradient(135deg,#3b5bdb,#7048e8);
            border-radius: 4px; padding: 2px 7px; }
        .xwlb-date { font-size: 12px; color: #999; }
        .xwlb-body h3 { font-size: 16px; margin: 2px 0 6px; }
        .xwlb-titles { margin: 0; padding-left: 18px; font-size: 13px; color: #555; line-height: 1.6; }
        .xwlb-titles li { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .xwlb-more { font-size: 12px; color: #3b5bdb; margin-top: 6px; display: inline-block; }
        .qz-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 10px; margin: 16px 0 24px; }
        .qz-item { background: #fff; border: 1px solid #eee; border-radius: 12px; padding: 12px 14px;
            box-shadow: 0 1px 4px rgba(0,0,0,.04); }
        .qz-name { display: block; font-size: 12px; color: #888; }
        .qz-val { display: block; font-size: 18px; font-weight: 700; margin: 4px 0; }
        .qz-chg { font-size: 13px; font-weight: 600; }
        .qz-item.up .qz-chg { color: var(--up); }
        .qz-item.down .qz-chg { color: var(--down); }
        .qz-item.flat .qz-chg { color: #999; }
        .sec { margin: 20px 0; }
        .sec-title { font-size: 17px; margin: 0 0 10px; display: flex; align-items: center; gap: 6px; }
        .sec-count { font-size: 12px; color: #888; background: #f0f0f5; border-radius: 10px; padding: 2px 8px; }
        .item-list { display: flex; flex-direction: column; gap: 10px; }
        .item { background: #fff; border: 1px solid #eee; border-radius: 12px; padding: 12px 14px; box-shadow: 0 1px 4px rgba(0,0,0,.04); }
        .item-head { display: flex; align-items: baseline; gap: 8px; }
        .item-time { font-size: 12px; color: #aaa; flex-shrink: 0; }
        .item-title { font-size: 15px; font-weight: 600; line-height: 1.5; }
        .tag-hot { font-size: 11px; color: #fff; background: var(--up); border-radius: 4px; padding: 1px 5px; flex-shrink: 0; }
        .item-summary { font-size: 13px; color: #666; margin: 6px 0 0; line-height: 1.6; }
        .zc-footer { text-align: center; font-size: 12px; color: #999; margin-top: 30px; line-height: 1.8; }
        @media (prefers-color-scheme: dark) {
            .xwlb-card, .qz-item, .item { background: #1f2130; border-color: #2c2f42; }
            .xwlb-body h3, .qz-val, .item-title { color: #e8eaf2; }
            .xwlb-titles, .item-summary { color: #a6a9bd; }
            .xwlb-date, .qz-name { color: #8b8ea3; }
            .item-time { color: #6b6e80; }
            .sec-count { background: #2c2f42; color: #8b8ea3; }
        }
    </style>
</head>
<body>
    <header class="topbar">
        <div class="brand">
            <span class="brand-mark">
                <svg viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg">
                    <path d="M2 13 L8 2 L14 13" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                    <path d="M4.5 9.5 H11.5" stroke="#fff" stroke-width="1.6" stroke-linecap="round"/>
                </svg>
            </span>
            早参
            <span class="brand-sub">开盘前 · 每日速览</span>
        </div>
        <a class="home" href="https://www.xhja.cn/" target="_blank" rel="noopener">徐宏江的小站 ↗</a>
    </header>

    <main class="zc-wrap">
        <section class="zc-hero">
            <div class="date">__DATE_CN__ · __WEEKDAY__</div>
            <h1>今日早参</h1>
            <div class="tip">隔夜外盘 · 宏观要闻 · 重磅公告 · 板块异动 · 风险提示，开盘前 3 分钟速览</div>
        </section>

__XWLB_CARD__

        <h2 class="section-title">隔夜外盘</h2>
        <div class="qz-grid">
__QUOTES__
        </div>

__SECTIONS__

        <footer class="zc-footer">
            <p>数据来源：东方财富网、上海证券报·中国证券网等公开信息，版权归原作者所有，本页仅作个人投资参考，不构成任何投资建议。</p>
            <p>本页由脚本自动生成于 __GENERATED__ · 每日 08:00 更新 · <a href="/xwlb/">查看新闻联播</a></p>
        </footer>
    </main>
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

    # 补充上证报要闻（可选，失败不阻塞）
    cnstock = fetch_cnstock_yaowen()
    if cnstock:
        for c in cnstock:
            news.append({'time': '', 'title': c['title'], 'summary': '',
                         'stocks': [], 'important': False})
        log('上证报要闻补充 %d 条' % len(cnstock))

    buckets = classify_news(news)
    for name, items in buckets.items():
        log('  %s：%d 条' % (name, len(items)))

    generated = datetime.now().strftime('%Y-%m-%d %H:%M')
    html_text = render_page(d, quotes, buckets, generated)
    ZAOCAN_DIR.mkdir(parents=True, exist_ok=True)
    OUT_HTML.write_text(html_text, encoding='utf-8')
    update_index(d, quotes, buckets)

    log('早参生成完成：%s（外盘 %d 项，快讯 %d 条）' % (OUT_HTML.name, len(quotes), len(news)))


if __name__ == '__main__':
    main()
