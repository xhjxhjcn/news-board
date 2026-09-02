# 新闻资讯 · news.xhja.cn

徐宏江的小站新闻板块。第一个栏目：**《新闻联播》每日图文摘要**——每天一篇文章，收录当日联播每条新闻的标题、配图、导语，并附央视原视频链接。

## 工作原理

```
GitHub Actions（每天 21:00 / 22:00 北京时间）
        │
        ▼
scripts/fetch_news.py 抓取央视网 tv.cctv.com
        │  ├─ 当日索引页 → 新闻列表（标题/时长/配图）
        │  ├─ 每条详情页 → 导语（content_area 首段）
        │  └─ 配图下载到本地 images/
        ▼
生成 news/YYYY-MM-DD.html + 更新 news/index.json
        │
        ▼
git commit + push → EdgeOne Pages 自动部署
```

## 目录结构

```
├── index.html               # 列表页（读 news/index.json 渲染）
├── assets/style.css         # 样式（与 www.xhja.cn 同风格）
├── news/                    # 文章页 + 索引（脚本自动生成）
│   ├── index.json
│   └── 2026-09-01.html
├── images/                  # 配图（脚本自动下载）
│   └── 2026-09-01/
├── scripts/fetch_news.py    # 抓取脚本（纯标准库，零依赖）
└── .github/workflows/       # GitHub Actions 定时任务
```

## 本地使用

```bash
# 抓今天
python scripts/fetch_news.py

# 抓指定日期
python scripts/fetch_news.py --date 2026-09-01

# 回填最近 5 天
python scripts/fetch_news.py --days 5

# 重新生成已存在的日期
python scripts/fetch_news.py --date 2026-09-01 --force

# 本地预览（列表页需要 http 服务才能读 JSON）
python -m http.server 8080
```

脚本幂等：已存在的日期默认跳过；今日内容未上线（未播出）安静退出，退出码 0。

## 部署到线上（一次性配置）

1. **建 GitHub 仓库**：把本目录（新闻板块/）整个推成一个 GitHub 仓库（公开或私有均可）
2. **EdgeOne Pages 建项目**：控制台 → Pages → 创建项目 → 从 Git 导入 → 选该仓库
   - 构建命令：**无**（纯静态）
   - 输出目录：**根目录 /**
3. **绑域名**：项目设置 → 自定义域名 → 添加 `news.xhja.cn`（若 xhja.cn 的 DNS 已在 EdgeOne，会自动加解析）
4. **检查 Actions 权限**：仓库 Settings → Actions → General → Workflow permissions → 选 **Read and write permissions**（否则 bot 推不了代码）
5. 手动跑一次验证：仓库 Actions 页 → daily-news → Run workflow → 留空抓今天（或填 `days` 回填）

配置完成后**不再需要任何人工操作**：每天 21:00 左右自动生成当天文章并上线。

## 备注

- 内容来源：央视网《新闻联播》，版权归原作者；每条摘要均附原文链接，页脚有来源声明，仅作个人学习用途
- GitHub 定时任务可能有几分钟延迟，属正常现象；若仓库 60 天无活动会暂停定时（每天自动 commit 不会触发此情况）
- 未来扩展：列表页已预留结构，可再加其他栏目（如人民日报摘要、行业资讯）
