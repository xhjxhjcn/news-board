#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把仓库里已有页面的顶栏 / 页脚换成最新统一版（可重复执行）。

靠 <!-- site-top:begin/end -->、<!-- site-footer:begin/end --> 注释锚定，
只替换这两段内部的内容，不动正文与图片。
新建页面由 fetch_zaocan.py / fetch_news.py 直接产出同样的顶底栏。

用法：
    python scripts/migrate_frames.py           # 预演，只打印改动清单
    python scripts/migrate_frames.py --apply   # 真正写盘
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from site_frame import CLOCK_SCRIPT, render_footer, render_header  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
STATS_LINE = '<script defer src="https://api.xhja.cn/stats.js?site=news"></script>'

TOP_INNER_RE = re.compile(r'(<!-- site-top:begin -->)(.*?)(<!-- site-top:end -->)', re.S)
FOOT_INNER_RE = re.compile(r'(<!-- site-footer:begin -->)(.*?)(<!-- site-footer:end -->)', re.S)
FOOTER_NOTE_RE = re.compile(r'<div class="footer-note">(.*?)</div>', re.S)

# 2026-10-08 前的老时钟脚本（带「星期 / 日期」），只用来识别并整块换新
CLOCK_BLOCK_RE = re.compile(
    r"<script>\(function \(\) \{.*?var WEEK = \['日'.*?\}\)\(\);</script>", re.S)

# 更老的页面（顶底栏还没有注释锚点）——只在兼容分支用到
OLD_HEADER_RE = re.compile(r'[ \t]*<header class="topbar">.*?</header>\n?', re.S)
OLD_FOOTER_RE = re.compile(r'[ \t]*<footer class="(?:page-footer|zc-footer)">.*?</footer>\n?', re.S)

# 当前频道 key：首页是 home，xwlb/ 下都是 xwlb
CUR = {'index.html': 'home'}


def detect_cur(rel):
    if rel in CUR:
        return CUR[rel]
    return 'xwlb' if rel.startswith('xwlb/') else 'home'


def _inner(frame_html, tag):
    """取出 render_header / render_footer 输出里 begin 与 end 注释之间的内容。"""
    b = '<!-- %s:begin -->' % tag
    e = '<!-- %s:end -->' % tag
    return frame_html[frame_html.index(b) + len(b):frame_html.index(e)].strip('\n')


def migrate(text, cur):
    orig = text

    # 0) 更老的页面（还没有注释锚点）：先把整块换成新框架，再走下面的锚点替换
    if '<!-- site-top:begin -->' not in text:
        text = OLD_HEADER_RE.sub(lambda _: render_header(cur) + '\n', text, count=1)
    if '<!-- site-footer:begin -->' not in text:
        text = OLD_FOOTER_RE.sub(lambda _: render_footer() + '\n', text, count=1)

    # 1) 顶栏：锚点内整段替换（2026-10-08 起不再有顶部日期细条）
    inner = _inner(render_header(cur), 'site-top')
    text = TOP_INNER_RE.sub(
        lambda m: '%s\n%s\n%s' % (m.group(1), inner, m.group(3)), text, count=1)

    # 2) 页脚：锚点内整段替换，保留原有来源 / 免责声明
    m = FOOT_INNER_RE.search(text)
    if m:
        nb = FOOTER_NOTE_RE.search(m.group(2))
        finner = _inner(render_footer(nb.group(1).strip() if nb else ''), 'site-footer')
        text = FOOT_INNER_RE.sub(
            lambda mm: '%s\n%s\n%s' % (mm.group(1), finner, mm.group(3)), text, count=1)

    # 3) 时钟脚本：老版（带星期 / 日期）整块换成新版
    if "var WEEK = ['日'" in text:
        text = CLOCK_BLOCK_RE.sub(
            lambda _: '<script>%s</script>' % CLOCK_SCRIPT, text, count=1)

    # 4) 统计脚本兜底：老页面漏挂的统一补上
    if STATS_LINE not in text:
        text = text.replace('</body>', '    %s\n</body>' % STATS_LINE, 1)

    return None if text == orig else text


def main():
    apply = '--apply' in sys.argv
    pages = [ROOT / 'index.html'] + sorted((ROOT / 'xwlb').glob('*.html'))
    changed = skipped = 0
    for p in pages:
        rel = p.relative_to(ROOT).as_posix()
        raw = p.read_text(encoding='utf-8')
        out = migrate(raw, detect_cur(rel))
        if out is None or out == raw:
            skipped += 1
            continue
        changed += 1
        print(('[apply] ' if apply else '[dry]   ') + rel)
        if apply:
            p.write_text(out, encoding='utf-8', newline='\n')
    print('改写 %d 个，跳过 %d 个%s'
          % (changed, skipped, '（已写盘）' if apply else '（预演，未写盘）'))


if __name__ == '__main__':
    main()
