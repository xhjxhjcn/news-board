#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
新闻联播每日摘要抓取脚本（零第三方依赖）
数据来源：央视网 tv.cctv.com《新闻联播》官方页面

用法：
    python scripts/fetch_news.py                    # 抓今天（未上线则安静退出）
    python scripts/fetch_news.py --date 2026-09-01  # 抓指定日期
    python scripts/fetch_news.py --days 5           # 回填最近 5 天（含今天）
    python scripts/fetch_news.py --force            # 重新生成已存在的日期

输出：
    news/YYYY-MM-DD.html   当日文章页
    news/index.json        文章索引（日期倒序）
    images/YYYY-MM-DD/     当日配图（本地化存储）

说明：
    - 幂等：已存在的日期默认跳过，重复运行无副作用
    - 今日内容未上线（404）不算错误，退出码 0，方便定时任务重试
"""

import argparse
import html as htmllib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NEWS_DIR = ROOT / 'xwlb'
IMAGES_DIR = ROOT / 'images'
INDEX_JSON = NEWS_DIR / 'index.json'

DAY_PAGE = 'https://tv.cctv.com/lm/xwlb/day/{}.shtml'
HEADERS = {
    'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                   'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36'),
    'Referer': 'https://tv.cctv.com/lm/xwlb/',
}
WEEKDAYS = ['星期一', '星期二', '星期三', '星期四', '星期五', '星期六', '星期日']

LI_RE = re.compile(r'<li>(.*?)</li>', re.S)
A_RE = re.compile(
    r'<a\s+href="(https://tv\.cctv\.com/\d{4}/\d{2}/\d{2}/VIDE\w+\.shtml)"[^>]*?\stitle="([^"]*)"')
IMG_RE = re.compile(r'<img\s+src="([^"]+)"')
DUR_RE = re.compile(r'<span>(\d{2}:\d{2}(?::\d{2})?)</span>')
CONTENT_RE = re.compile(r'<div class="content_area"[^>]*>(.*?)</div>', re.S)
P_RE = re.compile(r'<p[^>]*>(.*?)</p>', re.S)
TAG_RE = re.compile(r'<[^>]+>')


def log(msg):
    print('[%s] %s' % (datetime.now().strftime('%H:%M:%S'), msg), flush=True)


def http_get(url, timeout=30, retries=3):
    """GET 一个 URL，返回 bytes；404 或重试耗尽返回 None。"""
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
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


def normalize_img(url):
    if not url:
        return ''
    if url.startswith('//'):
        url = 'https:' + url
    if '-180.jpg' in url:
        url = url.replace('-180.jpg', '-300.jpg')
    return url


def parse_day_page(text):
    """解析当日索引片段，返回 (新闻条目列表, 完整版封面图URL)。"""
    items = []
    cover_url = ''
    for li in LI_RE.findall(text):
        a = A_RE.search(li)
        if not a:
            continue
        url = a.group(1)
        title = htmllib.unescape(a.group(2)).strip()
        img = IMG_RE.search(li)
        dur = DUR_RE.search(li)
        img_url = normalize_img(img.group(1)) if img else ''
        duration = dur.group(1) if dur else ''

        if title.startswith('《新闻联播》'):
            # 40 分钟完整版，不算单条新闻，其截图留作封面
            if img_url:
                cover_url = img_url
            continue

        title = title.replace('[视频]', '').strip()
        if not title:
            continue
        items.append({
            'url': url,
            'title': title,
            'img': img_url,
            'duration': duration,
            'lead': '',
            'local_img': '',
        })
    return items, cover_url


def extract_lead(detail_html):
    """从详情页提取导语（content_area 第一段，最多两段，截断至 200 字）。"""
    m = CONTENT_RE.search(detail_html)
    if not m:
        return ''
    paras = []
    for p in P_RE.findall(m.group(1)):
        t = TAG_RE.sub('', p)
        t = htmllib.unescape(t)
        t = re.sub(r'\s+', ' ', t).strip()
        if t:
            paras.append(t)
    if not paras:
        return ''
    lead = paras[0]
    if len(lead) < 50 and len(paras) > 1:
        lead += paras[1]
    lead = re.sub(r'^央视网消息[（(]新闻联播[）)]\s*[：:]\s*', '', lead)
    lead = re.sub(r'^央视网消息\s*[：:]\s*', '', lead)
    lead = re.sub(r'^[（(]新闻联播[）)]\s*[：:]\s*', '', lead)
    if len(lead) > 200:
        cut = lead[:200]
        pos = cut.rfind('。')
        lead = (cut[:pos + 1] if pos > 80 else cut.rstrip('，,；; ')) + '……'
    return lead


def download_image(url, dest):
    data = http_get(url, timeout=30, retries=2)
    if not data or len(data) < 1024:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return True


def esc(s):
    return htmllib.escape(str(s or ''), quote=True)


def render_article(d, items, cover_local):
    """生成当日文章页 HTML。"""
    ds = d.isoformat()
    date_cn = '%d 年 %d 月 %d 日' % (d.year, d.month, d.day)
    weekday = WEEKDAYS[d.weekday()]
    generated = datetime.now().strftime('%Y-%m-%d %H:%M')

    hero_cover = ('<div class="hero-cover"><img src="../%s" alt="%s 新闻联播"></div>' % (cover_local, date_cn)
                  if cover_local else '')

    cards = []
    for i, it in enumerate(items, 1):
        media = ''
        if it.get('local_img'):
            media = ('<div class="news-media"><span class="news-no">%02d</span>'
                     '<img src="../%s" alt="%s" loading="lazy"></div>'
                     % (i, it['local_img'], esc(it['title'])))
        else:
            media = '<div class="news-media"><span class="news-no">%02d</span></div>' % i
        lead = it.get('lead') or ''
        lead_html = ('<p class="news-lead">%s</p>' % esc(lead)
                     if lead else '<p class="news-lead none">（本条为快讯，点击标题查看央视原视频内容）</p>')
        cards.append(
            '<article class="news-card">%s'
            '<div class="news-body">'
            '<h2 class="news-title"><a href="%s" target="_blank" rel="noopener">%s</a></h2>'
            '<div class="news-meta">%s<a href="%s" target="_blank" rel="noopener">查看央视原视频 ↗</a></div>'
            '%s'
            '</div></article>'
            % (media,
               esc(it['url']), esc(it['title']),
               ('<span class="dur">时长 %s</span>' % esc(it['duration'])) if it.get('duration') else '',
               esc(it['url']),
               lead_html))

    html = ARTICLE_TEMPLATE
    for token, value in [
        ('__TITLE__', '%s 新闻联播主要内容 · 徐宏江的小站' % date_cn),
        ('__DATE_CN__', date_cn),
        ('__WEEKDAY__', weekday),
        ('__COUNT__', str(len(items))),
        ('__HERO_COVER__', hero_cover),
        ('__ITEMS__', '\n'.join(cards)),
        ('__GENERATED__', generated),
    ]:
        html = html.replace(token, value)
    return html


ARTICLE_TEMPLATE = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>__TITLE__</title>
    <meta name="description" content="__DATE_CN__《新闻联播》主要内容图文摘要，共 __COUNT__ 条，来源央视网。">
    <link rel="stylesheet" href="../assets/style.css">
</head>
<body>
    <header class="topbar">
        <a class="back" href="/xwlb/">← 返回列表</a>
        <div class="brand">
            <span class="brand-mark">
                <svg viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg">
                    <rect x="1" y="3" width="14" height="10" rx="2"></rect>
                    <path d="M6 13h4v2H6z" opacity="0.7"></path>
                    <path d="M5 6.2v3.6l3.2-1.8z" fill="#fff"></path>
                </svg>
            </span>
            新闻资讯
        </div>
        <a class="home" href="https://www.xhja.cn/" target="_blank" rel="noopener">徐宏江的小站 ↗</a>
    </header>

    <main class="article-main">
        <section class="article-hero">
            <div class="hero-text">
                <div class="hero-date">__DATE_CN__ · __WEEKDAY__</div>
                <h1>《新闻联播》主要内容</h1>
                <div class="hero-meta">
                    <span class="pill">共 __COUNT__ 条</span>
                    <span class="pill ghost">图文摘要</span>
                    <span class="src">来源：央视网 tv.cctv.com</span>
                </div>
            </div>
            __HERO_COVER__
        </section>

        <section class="news-list">
__ITEMS__
        </section>

        <footer class="page-footer">
            <p>内容来源：央视网《新闻联播》，版权归原作者所有，本页仅作个人学习摘要，每条均附原文链接。</p>
            <p>本页面由脚本自动生成于 __GENERATED__ · <a href="/xwlb/">返回新闻列表</a></p>
        </footer>
    </main>
</body>
</html>
'''


def update_index(d, count, cover, items):
    """更新 news/index.json（按日期倒序，同日期去重）。"""
    if INDEX_JSON.exists():
        try:
            data = json.loads(INDEX_JSON.read_text(encoding='utf-8'))
        except Exception:
            data = []
    else:
        data = []
    if not isinstance(data, list):
        data = []

    ds = d.isoformat()
    entry = {
        'date': ds,
        'weekday': WEEKDAYS[d.weekday()],
        'count': count,
        'cover': ('/%s' % cover) if cover else '',
        'url': 'xwlb/%s.html' % ds,
        'titles': [it['title'] for it in items[:3]],
    }
    data = [e for e in data if e.get('date') != ds]
    data.append(entry)
    data.sort(key=lambda e: e.get('date', ''), reverse=True)

    NEWS_DIR.mkdir(parents=True, exist_ok=True)
    INDEX_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def process_day(d, force=False):
    ds = d.isoformat()
    out_html = NEWS_DIR / ('%s.html' % ds)

    if out_html.exists() and not force:
        return 'skip'

    day_data = http_get(DAY_PAGE.format(d.strftime('%Y%m%d')))
    if day_data is None:
        return 'not-available'
    text = day_data.decode('utf-8', errors='replace')
    items, cover_url = parse_day_page(text)
    if not items:
        return 'empty'

    log('%s：共解析 %d 条，开始抓取详情与图片……' % (ds, len(items)))
    day_dir = IMAGES_DIR / ds

    for i, it in enumerate(items, 1):
        detail = http_get(it['url'])
        if detail is not None:
            it['lead'] = extract_lead(detail.decode('utf-8', errors='replace'))
        if it['img']:
            dest = day_dir / ('img%02d.jpg' % i)
            if download_image(it['img'], dest):
                it['local_img'] = 'images/%s/img%02d.jpg' % (ds, i)
        time.sleep(0.3)

    cover_local = ''
    if cover_url:
        if download_image(cover_url, day_dir / 'cover.jpg'):
            cover_local = 'images/%s/cover.jpg' % ds
    if not cover_local:
        cover_local = next((it['local_img'] for it in items if it.get('local_img')), '')

    html_text = render_article(d, items, cover_local)
    NEWS_DIR.mkdir(parents=True, exist_ok=True)
    out_html.write_text(html_text, encoding='utf-8')

    update_index(d, len(items), cover_local, items)

    n_img = sum(1 for it in items if it.get('local_img'))
    n_lead = sum(1 for it in items if it.get('lead'))
    log('%s：完成，文章 %s（图片 %d/%d，导语 %d/%d）'
        % (ds, out_html.name, n_img, len(items), n_lead, len(items)))
    return 'ok'



def ci_commit_push(max_retries=10):
    """在 GitHub Actions 中抢先完成提交与推送（带重试）。

    背景：工作流里 fetch-zaocan 与 fetch-news 两个任务并行执行、各自推送 main，
    后推送的一方会被远端拒绝（! [rejected] main -> main），导致内容丢失、任务失败。
    这里先对齐远端最新提交再推送，被拒则退避重试；工作流的 "Commit and push" 步骤
    随后会发现工作区已干净而自动跳过。仅 CI 环境生效，本地运行不做任何 git 操作。
    """
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        return True
    branch = os.environ.get('GITHUB_REF_NAME') or 'main'

    def run(cmd):
        return subprocess.run(cmd, shell=True, capture_output=True, text=True)

    run('git config user.name "github-actions[bot]"')
    run('git config user.email "41898282+github-actions[bot]@users.noreply.github.com"')

    for attempt in range(1, max_retries + 1):
        # 先对齐远端最新（浅克隆下 reset --soft 也能工作，不依赖共同祖先）
        if run('git fetch --depth=100 origin %s' % branch).returncode != 0:
            run('git fetch origin %s' % branch)
        run('git reset --soft origin/%s' % branch)
        run('git add -A')
        if run('git diff --cached --quiet').returncode == 0:
            log('没有新内容，跳过提交')
            return True
        stamp = datetime.now().strftime('%Y-%m-%d')
        if run('git commit -m "news: 更新 %s"' % stamp).returncode != 0:
            log('提交失败')
            return False
        if run('git push origin HEAD:%s' % branch).returncode == 0:
            log('推送成功（第 %d 次尝试）' % attempt)
            return True
        log('推送被拒（远端已有新提交），第 %d 次重试……' % attempt)
        time.sleep(attempt * 5)

    log('重试 %d 次仍未推送成功' % max_retries)
    return False


def main():
    parser = argparse.ArgumentParser(description='新闻联播每日摘要抓取')
    parser.add_argument('--date', help='指定日期 YYYY-MM-DD（默认今天）')
    parser.add_argument('--days', type=int, default=0, help='回填最近 N 天（含今天）')
    parser.add_argument('--force', action='store_true', help='重新生成已存在的日期')
    args = parser.parse_args()

    if args.days > 0:
        today = date.today()
        days = [today - timedelta(days=n) for n in range(args.days - 1, -1, -1)]
    elif args.date:
        try:
            days = [datetime.strptime(args.date, '%Y-%m-%d').date()]
        except ValueError:
            print('日期格式错误，应为 YYYY-MM-DD', file=sys.stderr)
            sys.exit(2)
    else:
        days = [date.today()]

    results = {}
    for d in days:
        r = process_day(d, force=args.force)
        results[d.isoformat()] = r

    for ds, r in sorted(results.items()):
        if r == 'skip':
            log('%s：已存在，跳过（--force 可重新生成）' % ds)
        elif r == 'not-available':
            log('%s：当日内容未上线（未播出或已过期），跳过' % ds)
        elif r == 'empty':
            log('%s：页面无新闻条目，跳过' % ds)

    ok = sum(1 for r in results.values() if r == 'ok')
    log('本次运行结束：新生成 %d 篇，共处理 %d 天' % (ok, len(days)))

    # 抢先提交并推送，避免与并行任务争抢分支（失败则让任务显式失败，便于排查）
    if not ci_commit_push():
        sys.exit(1)


if __name__ == '__main__':
    main()
