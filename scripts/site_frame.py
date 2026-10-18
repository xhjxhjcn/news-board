# -*- coding: utf-8 -*-
"""news.xhja.cn 全站统一的顶栏 / 页脚（2026-10-18 与 www.xhja.cn 主页对齐）。

所有页面（早参主页 index.html、新闻联播列表 xwlb/index.html、文章页 xwlb/<date>.html）
都通过这里取顶栏与页脚 HTML，保证一处修改、全站生效。
顶底栏的样式在 assets/style.css 的「顶栏 / 页脚」段。

结构（2026-10-18 起去掉频道条，只留与主页同款的一条主栏）：

    .site-top
      └─ .site-header   fixed 吸顶：logo + 站名 + 时钟

去掉了两样东西（站长 2026-10-18 定）：
  · 频道条（今日新闻 / 新闻联播 / 今日热榜 / 工具站 / 主页）—— 整条不要；
  · 页脚里的兄弟站点链接 —— 只留本站两个频道。

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
CONTACT = 'x@xhja.cn'
ICP = '浙ICP备2026078012号'

# (显示名, 链接, 是否站外) —— 页脚链接；只保留本站频道，不再挂兄弟站点
SITE_NAV = (
    ('今日新闻', '/', False),
    ('新闻联播', '/xwlb/', False),
)

# 调用方传的频道 key → 对应的 href（保留给页面高亮用，顶栏已无频道条）
CUR_HREF = {
    'home': '/',
    'xwlb': '/xwlb/',
}


def _links_html():
    """页脚横向链接（只列本站频道）。"""
    out = []
    for name, href, ext in SITE_NAV:
        tgt = ' target="_blank" rel="noopener"' if ext else ''
        out.append('<a href="%s"%s>%s</a>' % (href, tgt, name))
    return ''.join(out)


def render_header(cur='home'):
    """返回与主页同款的顶栏 HTML（一条主栏，无频道条）。

    左上角品牌在**任何子页都回主站** xhja.cn，不回本站首页（站长 2026-10-18 定）。
    """
    return (
        '<div class="site-top">\n'
        '<!-- site-top:begin -->\n'
        '    <header class="site-header">\n'
        '        <div class="header-inner">\n'
        '            <a class="brand" href="https://xhja.cn/" aria-label="回到主页">\n'
        '                <img src="/assets/logo.png" alt="%s" class="brand-logo">\n'
        '                <div class="brand-text">\n'
        '                    <span class="brand-name">%s</span>\n'
        '                    <span class="brand-slogan">%s</span>\n'
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
        '<!-- site-top:end -->\n'
        '</div>'
        % (BRAND, BRAND, SLOGAN)
    )


def render_footer(note=''):
    """返回与 www.xhja.cn 主站完全一致的页脚（2026-10-18 站长定）。

    结构与主站一致：品牌行（logo + 名称 + slogan）/ 链接行 / 备案 / 版权。
    note 参数仅为兼容旧调用保留，不再输出。
    """
    return (
        '    <footer class="site-footer">\n'
        '<!-- site-footer:begin -->\n'
        '        <div class="footer-inner">\n'
        '            <div class="footer-brand">\n'
        '                <img src="/assets/logo.png" alt="" class="footer-logo">\n'
        '                <div>\n'
        '                    <div class="footer-name">%s</div>\n'
        '                    <div class="footer-slogan">%s</div>\n'
        '                </div>\n'
        '            </div>\n'
        '            <div class="footer-links">%s</div>\n'
        '            <div class="footer-beian">\n'
        '                <a href="https://beian.miit.gov.cn/" target="_blank" rel="noopener">%s</a>\n'
        '            </div>\n'
        '            <div class="footer-copy">© 2026 %s · All Rights Reserved</div>\n'
        '        </div>\n'
        '<!-- site-footer:end -->\n'
        '    </footer>'
        % (BRAND, SLOGAN, _links_html(), ICP, BRAND)
    )


# 顶栏时钟：只更新 DOM，页面无对应节点时静默跳过
CLOCK_SCRIPT = '''(function () {
  function pad(n) { return n < 10 ? '0' + n : '' + n; }
  function tick() {
    var d = new Date();
    var s = [pad(d.getHours()) + ':' + pad(d.getMinutes()), pad(d.getSeconds())];
    var sel = ['[data-clock-hm]', '[data-clock-sec]'];
    for (var i = 0; i < sel.length; i++) {
      var el = document.querySelector(sel[i]);
      if (el && el.textContent !== s[i]) el.textContent = s[i];
    }
  }
  tick();
  setInterval(tick, 1000);
})();'''
