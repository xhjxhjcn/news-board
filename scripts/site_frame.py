# -*- coding: utf-8 -*-
"""news.xhja.cn 全站统一的顶栏 / 页脚（2026-09-27 与 www.xhja.cn 对齐）。

所有页面（早参主页 index.html、新闻联播列表 xwlb/index.html、文章页 xwlb/<date>.html）
都通过这里取顶栏与页脚 HTML，保证一处修改、全站生效。
顶底栏的样式在 assets/style.css 的「顶栏 / 页脚（统一）」段。

用法（在页面模板里留出占位符）：

    from site_frame import render_header, render_footer, CLOCK_SCRIPT
    html = (PAGE_TEMPLATE
            .replace('__HEADER__', render_header('home'))
            .replace('__FOOTER__', render_footer('免责声明……'))
            .replace('__CLOCK_SCRIPT__', CLOCK_SCRIPT))

顶栏 / 页脚里的链接一律用站点绝对路径（/、/xwlb/、/assets/...），
这样 xwlb/ 子目录下的页面无需再区分 ../。
"""

BRAND = '行恒简安'
SLOGAN = '行恒致远 · 简安自得'
CONTACT = 'x@xhja.cn'
ICP = '浙ICP备2026078012号'

# (显示名, 链接, 是否站外)
SITE_NAV = (
    ('今日新闻', '/', False),
    ('新闻联播', '/xwlb/', False),
    ('今日热榜', 'https://hot.xhja.cn/', True),
    ('工具站', 'https://tools.xhja.cn/', True),
    ('主页', 'https://www.xhja.cn/', True),
)

# 页脚用同一份站点互链（与顶栏保持一致），按首项对齐
FOOTER_LINKS = SITE_NAV


def _nav_html(nav_tag):
    """按 SITE_NAV 生成一段锚点，缩进 12 空格。"""
    out = []
    for name, href, ext in SITE_NAV:
        cls = ' class="cur"' if href == nav_tag else ''
        tgt = ' target="_blank" rel="noopener"' if ext else ''
        out.append('            <a href="%s"%s%s>%s</a>' % (href, cls, tgt, name))
    return '\n'.join(out)


def render_header(cur):
    """返回统一顶栏 HTML。cur 为当前页的导航 key（'home' | 'xwlb'）。"""
    nav = _nav_html(cur)

    return (
        '    <header class="site-header">\n'
        '        <div class="header-inner">\n'
        '            <a class="brand" href="/" aria-label="回到今日新闻">\n'
        '                <img src="/assets/logo.png" alt="%s" class="brand-logo">\n'
        '                <div class="brand-text">\n'
        '                    <span class="brand-name">%s</span>\n'
        '                    <span class="brand-slogan">%s</span>\n'
        '                </div>\n'
        '            </a>\n'
        '            <nav class="header-nav">\n%s\n            </nav>\n'
        '            <div class="header-actions">\n'
        '                <div class="clock">\n'
        '                    <div class="clock-main">\n'
        '                        <span class="clock-hm" data-clock-hm>--:--</span>\n'
        '                        <span class="clock-sec" data-clock-sec>--</span>\n'
        '                    </div>\n'
        '                    <span class="clock-divider" aria-hidden="true"></span>\n'
        '                    <div class="clock-meta">\n'
        '                        <span class="clock-ymd" data-clock-ymd>----/--</span>\n'
        '                    </div>\n'
        '                </div>\n'
        '            </div>\n'
        '        </div>\n'
        '    </header>'
        % (BRAND, BRAND, SLOGAN, nav)
    )


def render_footer(note='', generated=''):
    """返回统一页脚 HTML。

    note      顶部免责 / 来源声明，原样插入（调用方自行保证 HTML 合法）
    generated 附加的生成时间一行（原样插入，可留空）
    """
    links = _nav_html('')
    note_html = ''
    if note:
        note_html = '            <div class="footer-note">%s</div>\n' % note
    gen_html = ''
    if generated:
        gen_html = '            <div class="footer-gen">%s</div>\n' % generated

    return (
        '    <footer class="site-footer">\n'
        '        <div class="footer-inner">\n'
        '%s'
        '            <div class="footer-brand">\n'
        '                <img src="/assets/logo.png" alt="" class="footer-logo">\n'
        '                <div>\n'
        '                    <div class="footer-name">%s</div>\n'
        '                    <div class="footer-slogan">%s</div>\n'
        '                </div>\n'
        '            </div>\n'
        '            <div class="footer-links">\n%s\n            </div>\n'
        '            <div class="xhja-mail"><a href="mailto:%s">📧 联系我：%s</a></div>\n'
        '            <div class="footer-copy">© 2026 %s · All Rights Reserved</div>\n'
        '            <div class="xhja-icp">\n'
        '                <a href="https://beian.miit.gov.cn/" target="_blank" rel="noopener">'
        '浙ICP备2026078012号</a>\n'
        '            </div>\n'
        '%s'
        '        </div>\n'
        '    </footer>'
        % (note_html, BRAND, SLOGAN, links, CONTACT, CONTACT, BRAND, gen_html)
    )


# 顶栏时钟：只更新 DOM，页面无对应节点时静默跳过
CLOCK_SCRIPT = '''(function () {
  var WEEK = ['日', '一', '二', '三', '四', '五', '六'];
  function pad(n) { return n < 10 ? '0' + n : '' + n; }
  function tick() {
    var d = new Date();
    var s = [pad(d.getHours()) + ':' + pad(d.getMinutes()), pad(d.getSeconds()),
             (d.getMonth() + 1) + '/' + d.getDate() + ' 周' + WEEK[d.getDay()]];
    var sel = ['[data-clock-hm]', '[data-clock-sec]', '[data-clock-ymd]'];
    for (var i = 0; i < sel.length; i++) {
      var el = document.querySelector(sel[i]);
      if (el && el.textContent !== s[i]) el.textContent = s[i];
    }
  }
  tick();
  setInterval(tick, 1000);
})();'''
