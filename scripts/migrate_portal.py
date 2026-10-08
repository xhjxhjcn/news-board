# -*- coding: utf-8 -*-
"""把存量页面迁移到门户版（顶栏 / 页脚 / 首页两栏布局）。

幂等：第二遍运行「改写 0 个」。默认预演，加 --apply 才写盘。

顶底栏：按 site-top / site-footer 注释块整段替换，兼容旧格式
        （<header class="site-header"> / <header class="topbar"> 等）。
首页：   从现有 index.html 里提取焦点卡 / 行情 / 栏目，重组成两栏门户布局，
        不联网重抓数据，正文内容一字不改。
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from site_frame import render_header, render_footer, CLOCK_SCRIPT, SITE_NAV  # noqa: E402

CLOCK_MARK = "var WEEK = ['日', '一', '二', '三', '四', '五', '六'];"
STATS_LINE = '<script defer src="https://api.xhja.cn/stats.js?site=news"></script>'

# --- 顶栏：三种历史格式，任一命中即整段替换 ---
TOP_PATTERNS = [
    # 新版：靠 site-top:begin / end 注释锚定，不能只匹配到第一个 </div>
    re.compile(r'[ \t]*<div class="site-top">\s*<!-- site-top:begin -->.*?'
               r'<!-- site-top:end -->\s*</div>\n?', re.S),
    re.compile(r'[ \t]*<header class="site-header">.*?</header>\n?', re.S),
    re.compile(r'[ \t]*<header class="topbar">.*?</header>\n?', re.S),
]
# --- 页脚：同样兼容旧格式 ---
FOOT_PATTERNS = [
    re.compile(r'[ \t]*<footer class="site-footer">.*?</footer>\n?', re.S),
    re.compile(r'[ \t]*<footer class="(?:page-footer|zc-footer)">.*?</footer>\n?', re.S),
]
FOOTER_NOTE_RE = re.compile(r'<div class="footer-note">(.*?)</div>', re.S)
# footer-gen 历史上有 div / span 两种写法，且内容里可能嵌 <span>（如列表页的
# <span id="latest-date">），所以 span 版用单行贪婪取到最后一个 </span>。
GEN_PATTERNS = [
    re.compile(r'<div class="footer-gen">(.*?)</div>', re.S),
    re.compile(r'<span class="footer-gen">(.*)</span>'),
]


def extract_gen(text):
    for pat in GEN_PATTERNS:
        m = pat.search(text)
        if m:
            return m.group(1).strip()
    return ''


CRUMB_RE = re.compile(r'[ \t]*<nav class="crumb">.*?</nav>\n?', re.S)
HERO_DATE_RE = re.compile(r'<div class="hero-date">(.*?)</div>', re.S)
MAIN_OPEN_RE = re.compile(r'(<main\b[^>]*>\n)')


def cur_of(rel):
    return 'xwlb' if rel.startswith('xwlb/') else 'home'


def add_crumb(text, rel):
    """文章页 / 列表页加面包屑（门户标配）。首页有频道头图，不加。"""
    if rel == 'index.html' or CRUMB_RE.search(text):
        return text
    if 'article-hero' in text:                      # 文章页：首页 › 新闻联播 › 日期
        m = HERO_DATE_RE.search(text)
        # 三级：首页 › 新闻联播 › 当日
        parts = ['<a href="/">首页</a>',
                 '<a href="/xwlb/">新闻联播</a>']
        if m:
            parts.append('<span class="cur">%s</span>' % m.group(1).strip())
    elif 'id="featured"' in text:                   # 列表页：首页 › 新闻联播（当前）
        parts = ['<a href="/">首页</a>', '<span class="cur">新闻联播</span>']
    else:
        return text
    sep = '<span class="crumb-sep">›</span>'
    crumb = '        <nav class="crumb">%s</nav>\n' % sep.join(parts)
    return MAIN_OPEN_RE.sub(lambda m: m.group(1) + crumb, text, count=1)


def migrate_frame(text, rel, is_index=False):
    """换顶底栏 + 补时钟脚本。返回 None 表示无变化。"""
    orig = text
    cur = cur_of(rel)

    # 1) 顶栏
    for pat in TOP_PATTERNS:
        new_text, n = pat.subn(lambda m: render_header(cur) + '\n', text, count=1)
        if n:
            text = new_text
            break

    # 2) 页脚（先留住原来的声明文字与生成时间）
    note, gen = '', ''
    m = FOOTER_NOTE_RE.search(text)
    if m:
        note = m.group(1).strip()
    gen = extract_gen(text)
    for pat in FOOT_PATTERNS:
        new_text, n = pat.subn(
            lambda m: render_footer(note=note) + '\n', text, count=1)
        if n:
            text = new_text
            break

    # 3) 面包屑（文章页 / 列表页）
    text = add_crumb(text, rel)

    # 4) 时钟脚本（放在统计脚本之前）
    if CLOCK_MARK not in text:
        if STATS_LINE in text:
            text = text.replace(STATS_LINE,
                                '<script>%s</script>\n    %s' % (CLOCK_SCRIPT, STATS_LINE), 1)
        else:
            text = text.replace('</body>',
                                '    <script>%s</script>\n</body>' % CLOCK_SCRIPT, 1)

    return None if text == orig else text


# ---------- 首页两栏改造 ----------
HERO_RE = re.compile(r'[ \t]*<section class="zc-hero">.*?</section>\n?', re.S)
# ⚠ 焦点卡 / 行情条内部都嵌着 <div>，不能用「非贪婪到第一个 </div>」——
#   会只截到卡片开头，丢掉闭合标签，把后面的内容全吞进这个块里。
FOCUS_OLD_RE = re.compile(r'[ \t]*<a class="xwlb-card"[^>]*>.*?</a>\n?', re.S)
FOCUS_NEW_RE = re.compile(r'[ \t]*<a class="focus"[^>]*>.*?</a>\n?', re.S)
FOCUS_EMPTY_RE = re.compile(
    r'[ \t]*<div class="(?:xwlb-card|focus) empty">.*?</div>\n?', re.S)
# 行情条：取到「换行 + 缩进 + </div>」（容器自身的闭合），而不是第一个 </div>
STRIP_RE = re.compile(
    r'<div class="qz-(?:grid|strip)">\s*(.*?)\n[ \t]*</div>', re.S)
SEC_RE = re.compile(r'[ \t]*<section class="sec">.*?</section>\n?', re.S)
QZ_ITEM_RE = re.compile(
    r'<div class="qz-item (up|down|flat)"><span class="qz-name">(.*?)</span>'
    r'<span class="qz-val">(.*?)</span><span class="qz-chg">(.*?)</span></div>', re.S)
OLD_TITLE_RE = re.compile(r'[ \t]*<h2 class="section-title">[^<]*</h2>\n?')
ITEM_RE = re.compile(
    r'<article class="item"><div class="item-head">'
    r'<span class="item-time">(.*?)</span>(.*?)</div>', re.S)
TITLE_A_RE = re.compile(r'<a class="item-title" href="(.*?)"(.*?)>(.*?)</a>', re.S)


def build_focus(old_card):
    """把旧 xwlb-card 转成门户焦点卡；已经是新版就原样返回。"""
    if 'class="focus' in old_card:
        return old_card
    cover = re.search(r'<img class="xwlb-cover" src="([^"]*)"', old_card)
    date = re.search(r'<span class="xwlb-date">(.*?) · (.*?)</span>', old_card)
    titles = re.findall(r'<li>(.*?)</li>', old_card, re.S)
    more = re.search(r'<span class="xwlb-more">共 (\d+) 条', old_card)
    href = re.search(r'href="([^"]*)"', old_card)
    if not (titles or more):
        print('  ! 焦点卡内容提取为空，检查正则是否截断了卡片')
    img = ('<img src="%s" alt="新闻联播" loading="lazy">' % cover.group(1)) if cover else ''
    return (
        '<a class="focus" href="%s">'
        '<div class="focus-cover">%s<span class="focus-badge">头条</span></div>'
        '<div class="focus-body">'
        '<div class="focus-head"><span>%s · %s</span><span>央视网</span></div>'
        '<h2>《新闻联播》主要内容</h2>'
        '<ul class="focus-list">%s</ul>'
        '<span class="focus-more">共 %s 条 · 阅读全文 →</span>'
        '</div></a>'
        % (href.group(1) if href else '/xwlb/',
           img,
           date.group(1) if date else '', date.group(2) if date else '',
           ''.join('<li>%s</li>' % t for t in titles[:4]),
           more.group(1) if more else '0')
    )


def build_side_quotes(strip_html):
    rows = []
    for cls, name, val, chg in QZ_ITEM_RE.findall(strip_html):
        rows.append(
            '<div class="side-quote"><span class="sq-name">%s</span>'
            '<span class="sq-val">%s</span>'
            '<span class="sq-chg %s">%s</span></div>' % (name, val, cls, chg))
    return '\n'.join(rows)


def build_hot(sections_html, limit=10):
    """从栏目区块里挑热点：带「重要」标签的优先，其余按出现顺序补。"""
    picked, seen = [], set()
    for m in ITEM_RE.finditer(sections_html):
        head = m.group(2)
        title_m = TITLE_A_RE.search(head)
        if not title_m:
            continue
        title = title_m.group(3)
        if title in seen:
            continue
        seen.add(title)
        picked.append((1 if 'tag-hot' in head else 0, title_m.group(1), title))
    picked.sort(key=lambda x: -x[0])
    out = []
    for i, (_w, href, title) in enumerate(picked[:limit], 1):
        cls = ' class="rank-item top"' if i <= 3 else ' class="rank-item"'
        out.append('<a%s href="%s" target="_blank" rel="noopener">'
                   '<span class="rank-no">%d</span>'
                   '<span class="rank-text">%s</span></a>' % (cls, href, i, title))
    return '\n'.join(out)


def build_site_links():
    return ''.join('<a href="%s" target="_blank" rel="noopener">%s</a>'
                   % (h, n) for n, h, ext in SITE_NAV if ext)


def migrate_index(text):
    """首页：zc-wrap → portal 两栏。返回 None 表示无变化。"""
    orig = text
    if 'class="portal"' in text:
        return None  # 已是新版

    hero_m = HERO_RE.search(text)
    focus_m = (FOCUS_NEW_RE.search(text)
               or FOCUS_OLD_RE.search(text)
               or FOCUS_EMPTY_RE.search(text))
    strip_m = STRIP_RE.search(text)
    if not (hero_m and strip_m and focus_m):
        print('  ! 首页结构不符预期（hero=%s focus=%s strip=%s），跳过布局改造'
              % (bool(hero_m), bool(focus_m), bool(strip_m)))
        return None

    sections = '\n'.join(m.group(0).rstrip() for m in SEC_RE.finditer(text))
    hero = hero_m.group(0).rstrip()
    focus = build_focus(focus_m.group(0)) if focus_m else ''
    strip = strip_m.group(1)
    hot = build_hot(sections)
    side_q = build_side_quotes(strip)
    links = build_site_links()

    body = (
        '    <main class="portal">\n'
        '        <div class="portal-main">\n'
        '%s\n\n'
        '%s\n\n'
        '            <div class="qz-strip">\n%s\n            </div>\n\n'
        '%s\n'
        '        </div>\n\n'
        '        <aside class="portal-side">\n'
        '            <div class="side-card">\n'
        '                <div class="side-title">🔥 热点排行</div>\n'
        '                <div class="rank-list">\n%s\n                </div>\n'
        '            </div>\n\n'
        '            <div class="side-card">\n'
        '                <div class="side-title">📊 外盘速览</div>\n%s\n'
        '            </div>\n\n'
        '            <div class="side-card">\n'
        '                <div class="side-title">🧭 兄弟站点</div>\n'
        '                <div class="side-links">\n%s\n                </div>\n'
        '            </div>\n'
        '        </aside>\n'
        '    </main>'
        % (hero, focus, strip, sections, hot, side_q, links)
    )

    # 整段替换 <main class="zc-wrap">...</main>
    main_re = re.compile(r'[ \t]*<main class="zc-wrap">.*?</main>\n?', re.S)
    text, n = main_re.subn(lambda m: body + '\n', text, count=1)
    if not n:
        print('  ! 没找到 <main class="zc-wrap">，跳过布局改造')
        return None

    # 去掉旧「隔夜外盘」小标题（新布局里行情条自带语义）
    text = OLD_TITLE_RE.sub('', text)

    return None if text == orig else text


def main():
    apply = '--apply' in sys.argv
    files = [ROOT / 'index.html'] + sorted((ROOT / 'xwlb').glob('*.html'))
    changed = 0
    for p in files:
        rel = p.relative_to(ROOT).as_posix()
        text = p.read_text(encoding='utf-8')
        out = migrate_frame(text, rel)
        if rel == 'index.html':
            out2 = migrate_index(out if out else text)
            out = out2 if out2 else out
        if out is None:
            continue
        changed += 1
        print('  改写 %s' % rel)
        if apply:
            p.write_text(out, encoding='utf-8')
    print('共 %d 个文件%s' % (changed, '（已写入）' if apply else '（预演，加 --apply 写盘）'))


if __name__ == '__main__':
    main()
