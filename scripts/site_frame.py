# -*- coding: utf-8 -*-
"""news.xhja.cn 全站统一的顶栏 / 页脚（2026-09-27 门户化改版）。

所有页面（早参主页 index.html、新闻联播列表 xwlb/index.html、文章页 xwlb/<date>.html）
都通过这里取顶栏与页脚 HTML，保证一处修改、全站生效。
顶底栏的样式在 assets/style.css 的「顶栏 / 页脚（门户统一）」段。

结构（仿门户站三段式）：

    .site-top  (position: fixed，整条吸顶)
      ├─ .topbar-mini   日期 / 快捷入口细条
      ├─ .site-header   logo + 站名 + 时钟
      └─ .channel-bar   频道导航条

用法（在页面模板里留出占位符）：

    from site_frame import render_header, render_footer, CLOCK_SCRIPT
    html = (PAGE_TEMPLATE
            .replace('__HEADER__', render_header('home'))
            .replace('__FOOTER__', render_footer('免责声明……'))
            .replace('__CLOCK_SCRIPT__', CLOCK_SCRIPT))

顶栏 / 页脚里的链接一律用站点绝对路径（/、/xwlb/、/assets/...），
这样 xwlb/ 子目录下的页面无需再区分 ../。

⚠ 顶底栏输出带 <!-- site-top:begin --> / <!-- site-top:end --> 注释包裹，
  迁移脚本靠这对标记整段替换，**不要删掉注释**，否则存量页面无法增量更新。
"""

BRAND = '行恒简安'
SLOGAN = '行恒致远 · 简安自得'
SITE_NAME = '今日新闻'
CONTACT = 'x@xhja.cn'
ICP = '浙ICP备2026078012号'

# (显示名, 链接, 是否站外) —— 频道条与页脚共用
SITE_NAV = (
    ('今日新闻', '/', False),
    ('新闻联播', '/xwlb/', False),
    ('今日热榜', 'https://hot.xhja.cn/', True),
    ('工具站', 'https://tools.xhja.cn/', True),
    ('主页', 'https://www.xhja.cn/', True),
)

# 顶部细条右侧的快捷入口（只放站外站，站内频道走频道条）
MINI_LINKS = (
    ('今日热榜', 'https://hot.xhja.cn/'),
    ('工具站', 'https://tools.xhja.cn/'),
    ('主页', 'https://www.xhja.cn/'),
)


# 调用方传的频道 key → 对应的 href（用于高亮判定）
CUR_HREF = {
    'home': '/',
    'xwlb': '/xwlb/',
}


def _channel_html(nav_tag):
    """频道条锚点，缩进 16 空格。cur 传 'home' / 'xwlb' 或直接传 href。"""
    cur_href = CUR_HREF.get(nav_tag, nav_tag)
    out = []
    for name, href, ext in SITE_NAV:
        cls = ' class="ch cur"' if href == cur_href else ' class="ch"'
        tgt = ' target="_blank" rel="noopener"' if ext else ''
        out.append('                <a%s href="%s"%s>%s</a>' % (cls, href, tgt, name))
    return '\n'.join(out)


def _mini_html():
    out = []
    for name, href in MINI_LINKS:
        out.append('<a href="%s" target="_blank" rel="noopener">%s</a>'
                   % (href, name))
    return '<span class="mini-sep"></span>'.join(out)


def _cols_html():
    """页脚三列链接矩阵。"""
    def col(title, items):
        inner = ''.join('\n                        <a href="%s"%s>%s</a>' % (h, t, n)
                        for n, h, t in items)
        return ('                <div class="fcol">\n'
                '                    <h4>%s</h4>%s\n'
                '                </div>' % (title, inner))

    inside = [it for it in SITE_NAV if not it[2]]
    outside = [it for it in SITE_NAV if it[2]]
    cols = [
        col('本站频道', [(n, h, '') for n, h, _ in inside]),
        col('兄弟站点', [(n, h, ' target="_blank" rel="noopener"') for n, h, _ in outside]),
        col('联系', [('📧 %s' % CONTACT, 'mailto:%s' % CONTACT, '')]),
    ]
    return '\n'.join(cols)


def render_header(cur):
    """返回门户式顶栏 HTML。cur 为当前频道（'home' | 'xwlb'）。"""
    return (
        '<div class="site-top">\n'
        '<!-- site-top:begin -->\n'
        '    <div class="topbar-mini">\n'
        '        <div class="mini-inner">\n'
        '            <div class="mini-left">\n'
        '                <span class="mini-date" data-clock-ymd>--/--</span>\n'
        '                <span class="mini-week" data-clock-week>星期-</span>\n'
        '                <span class="mini-tip">每日 08:00 更新</span>\n'
        '            </div>\n'
        '            <div class="mini-right">%s</div>\n'
        '        </div>\n'
        '    </div>\n'
        '    <header class="site-header">\n'
        '        <div class="header-inner">\n'
        '            <a class="brand" href="/" aria-label="回到首页">\n'
        '                <img src="/assets/logo.png" alt="%s" class="brand-logo">\n'
        '                <div class="brand-text">\n'
        '                    <span class="brand-name">%s</span>\n'
        '                    <span class="brand-slogan">%s · %s</span>\n'
        '                </div>\n'
        '            </a>\n'
        '            <div class="header-actions">\n'
        '                <div class="clock">\n'
        '                    <div class="clock-main">\n'
        '                        <span class="clock-hm" data-clock-hm>--:--</span>\n'
        '                        <span class="clock-sec" data-clock-sec>--</span>\n'
        '                    </div>\n'
        '                </div>\n'
        '            </div>\n'
        '        </div>\n'
        '    </header>\n'
        '    <nav class="channel-bar">\n'
        '        <div class="channel-inner">\n'
        '%s\n'
        '        </div>\n'
        '    </nav>\n'
        '<!-- site-top:end -->\n'
        '</div>'
        % (_mini_html(), BRAND, BRAND, SITE_NAME, SLOGAN, _channel_html(cur))
    )


def render_footer(note='', generated=''):
    """返回门户式页脚 HTML。

    note      顶部免责 / 来源声明，原样插入（调用方自行保证 HTML 合法）
    generated 附加的生成时间一行（原样插入，可留空）
    """
    note_html = ''
    if note:
        note_html = '            <div class="footer-note">%s</div>\n' % note
    gen_html = ''
    if generated:
        gen_html = '                <span class="footer-gen">%s</span>' % generated

    return (
        '    <footer class="site-footer">\n'
        '<!-- site-footer:begin -->\n'
        '        <div class="footer-inner">\n'
        '            <div class="footer-top">\n'
        '                <div class="footer-brand">\n'
        '                    <img src="/assets/logo.png" alt="" class="footer-logo">\n'
        '                    <div>\n'
        '                        <div class="footer-name">%s</div>\n'
        '                        <div class="footer-slogan">%s</div>\n'
        '                    </div>\n'
        '                </div>\n'
        '                <div class="footer-cols">\n'
        '%s\n'
        '                </div>\n'
        '            </div>\n'
        '%s'
        '            <div class="footer-bottom">\n'
        '                <span class="footer-copy">© 2026 %s · All Rights Reserved</span>\n'
        '                <span class="footer-icp">\n'
        '                    <a href="https://beian.miit.gov.cn/" target="_blank" rel="noopener">'
        '%s</a>\n'
        '                </span>\n'
        '%s\n'
        '            </div>\n'
        '        </div>\n'
        '<!-- site-footer:end -->\n'
        '    </footer>'
        % (BRAND, SLOGAN, _cols_html(), note_html, BRAND, ICP, gen_html)
    )


# 顶栏时钟：只更新 DOM，页面无对应节点时静默跳过
CLOCK_SCRIPT = '''(function () {
  var WEEK = ['日', '一', '二', '三', '四', '五', '六'];
  function pad(n) { return n < 10 ? '0' + n : '' + n; }
  function tick() {
    var d = new Date();
    var s = [pad(d.getHours()) + ':' + pad(d.getMinutes()), pad(d.getSeconds()),
             (d.getMonth() + 1) + '/' + d.getDate(), '星期' + WEEK[d.getDay()]];
    var sel = ['[data-clock-hm]', '[data-clock-sec]',
               '[data-clock-ymd]', '[data-clock-week]'];
    for (var i = 0; i < sel.length; i++) {
      var el = document.querySelector(sel[i]);
      if (el && el.textContent !== s[i]) el.textContent = s[i];
    }
  }
  tick();
  setInterval(tick, 1000);
})();'''
