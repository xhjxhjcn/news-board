# -*- coding: utf-8 -*-
"""news.xhja.cn 全站统一的顶栏 / 页脚（2026-10-08 门户化改版）。

所有页面（早参主页 index.html、新闻联播列表 xwlb/index.html、文章页 xwlb/<date>.html）
都通过这里取顶栏与页脚 HTML，保证一处修改、全站生效。
顶底栏的样式在 assets/style.css 的「顶栏 / 页脚」段。

结构（2026-10-08 起去掉顶部日期细条，只留主栏 + 频道条）：

    .site-top  (position: fixed，整条吸顶)
      ├─ .site-header   logo + 站名 + 时钟
      └─ .channel-bar   频道导航条

页脚与 www.xhja.cn 主站同款：品牌居中 + 横向链接 + 声明 + 备案 + 联系 + 版权。

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

# (显示名, 链接, 是否站外) —— 频道条与页脚链接共用
SITE_NAV = (
    ('今日新闻', '/', False),
    ('新闻联播', '/xwlb/', False),
    ('今日热榜', 'https://hot.xhja.cn/', True),
    ('工具站', 'https://tools.xhja.cn/', True),
    ('主页', 'https://www.xhja.cn/', True),
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


def _links_html():
    """页脚横向链接（与频道条同源，一站一列排开）。"""
    out = []
    for name, href, ext in SITE_NAV:
        tgt = ' target="_blank" rel="noopener"' if ext else ''
        out.append('<a href="%s"%s>%s</a>' % (href, tgt, name))
    return ''.join(out)


def render_header(cur):
    """返回门户式顶栏 HTML（主栏 + 频道条）。cur 为 'home' | 'xwlb'。"""
    return (
        '<div class="site-top">\n'
        '<!-- site-top:begin -->\n'
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
        % (BRAND, BRAND, SITE_NAME, SLOGAN, _channel_html(cur))
    )


def render_footer(note=''):
    """返回与 www.xhja.cn 主站同款的居中简洁页脚。

    note  可选的来源 / 免责声明，原样插入（调用方自行保证 HTML 合法）。
          2026-10-08 起不再输出「本页由脚本自动生成于 …」那一行。
    """
    note_html = ''
    if note:
        note_html = '            <div class="footer-note">%s</div>\n' % note

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
        '%s'
        '            <div class="footer-beian">\n'
        '                <a href="https://beian.miit.gov.cn/" target="_blank" rel="noopener">'
        '%s</a>\n'
        '            </div>\n'
        '            <div class="xhja-mail"><a href="mailto:%s">📧 联系我：%s</a></div>\n'
        '            <div class="footer-copy">© 2026 %s · All Rights Reserved</div>\n'
        '        </div>\n'
        '<!-- site-footer:end -->\n'
        '    </footer>'
        % (BRAND, SLOGAN, _links_html(), note_html, ICP, CONTACT, CONTACT, BRAND)
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
