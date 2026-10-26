# 开发计划：B站优质视频案例检索工具（第一版 / MVP）

> 依据：PRD.md（v1.1）｜本计划是可直接执行的实施文档，开发以本计划 + PRD 为准。
> 版本：v1.1（2026-09-21）
>
> 变更记录（v1.1）：按 PRD v1.1 新增"一键跳转 B站播放"交互（卡片角标 + 详情页按钮，新标签页跳转），不做站内播放。

---

## 1. 本机环境现状（已实际检查）

| 项 | 状态 |
| --- | --- |
| Python | ✅ 3.14.7（路径：`D:\Python\Python 3.14\python.exe`） |
| pip | ✅ 26.1.1 |
| Node.js | ✅ v22.23.2（本计划用不到） |
| Git | ✅ 2.55.0 |
| SQLite | ✅ Python 3.14 内置 sqlite3，无需单独安装 |

结论：环境齐备，无需额外安装语言环境；缺失的仅是 Python 第三方包（用 venv + pip 安装，见 P0）。

---

## 2. 技术选型

| 层 | 选型 | 理由 |
| --- | --- | --- |
| 后端框架 | Python + FastAPI + Uvicorn | 轻量、自带文档、异步支持，适合小工具 |
| HTTP 客户端 | httpx | 超时/重试控制方便 |
| 数据库 | SQLite（内置 sqlite3） | 单文件、零部署、符合 PRD 第 7 节备份恢复要求 |
| 前端 | Jinja2 服务端渲染 + 原生 JS（fetch） | 3 个页面，结构简单，不引入构建工具链 |
| 部署 | 本地 Uvicorn + 免费内网穿透 | 满足"公网链接随时访问" |

依赖清单（requirements.txt）：

```
fastapi
uvicorn
httpx
jinja2
python-multipart
pytest
```

---

## 3. 项目结构

```
D:\Sky Rain's Work\
├── PRD.md                     # 已有
├── DEV_PLAN.md                # 本文件
└── bili-case-tool\            # 新建项目根目录
    ├── requirements.txt
    ├── README.md              # 启动说明（含一键启动命令）
    ├── start.bat              # 一键启动本地服务（可双击）
    ├── start_tunnel.bat       # 一键启动内网穿透（部署阶段）
    ├── app\
    │   ├── __init__.py
    │   ├── main.py            # FastAPI 入口：挂路由、启动时建表
    │   ├── config.py          # 常量与配置（端口、缓存时长、频控参数）
    │   ├── database.py        # SQLite 连接管理 + 建表 DDL
    │   ├── bili\
    │   │   ├── __init__.py
    │   │   ├── client.py      # B站接口客户端（搜索 + 详情 + 频控 + 重试）
    │   │   └── wbi.py         # WBI 签名（预留，遇 412 启用）
    │   ├── services\
    │   │   ├── __init__.py
    │   │   ├── search.py      # 搜索编排：缓存判断 → 抓取 → 入库 → 排序
    │   │   ├── rank.py        # 质量分计算与排序
    │   │   └── favorite.py    # 收藏/备注读写
    │   ├── routes\
    │   │   ├── __init__.py
    │   │   ├── pages.py       # 三个页面路由
    │   │   ├── api.py         # JSON API
    │   │   └── backup.py      # 备份/恢复 API
    │   ├── templates\
    │   │   ├── base.html      # 母版（顶部导航 + 页脚）
    │   │   ├── index.html     # 首页
    │   │   ├── video.html     # 详情页
    │   │   └── favorites.html # 我的案例页
    │   └── static\
    │       ├── style.css
    │       └── app.js
    ├── data\                  # 运行时生成
    │   └── bili_case.db
    └── backups\               # 备份文件目录（导出时生成）
    └── tests\
        ├── test_rank.py
        ├── test_cache.py
        └── test_bili.py
```

---

## 4. 数据库设计（建表 DDL）

```sql
CREATE TABLE IF NOT EXISTS videos (
  bvid          TEXT PRIMARY KEY,          -- B站视频 ID
  title         TEXT NOT NULL,
  author_name   TEXT,
  author_mid    TEXT,
  cover_url     TEXT,
  pubdate       INTEGER,                   -- 发布时间（Unix 秒）
  duration      INTEGER,                   -- 时长（秒）
  tname         TEXT,                      -- 分区名
  view          INTEGER DEFAULT 0,
  like          INTEGER DEFAULT 0,
  coin          INTEGER DEFAULT 0,
  favorite      INTEGER DEFAULT 0,
  reply         INTEGER DEFAULT 0,
  danmaku       INTEGER DEFAULT 0,
  share         INTEGER DEFAULT 0,
  quality_score REAL,                      -- 综合质量分（0-100）
  data_complete INTEGER DEFAULT 1,         -- 0 = 详情数据不全（播放量为 0 等）
  fetched_at    INTEGER                    -- 抓取时间
);

CREATE TABLE IF NOT EXISTS favorites (
  bvid       TEXT PRIMARY KEY,
  created_at INTEGER,
  FOREIGN KEY (bvid) REFERENCES videos(bvid)
);

CREATE TABLE IF NOT EXISTS video_notes (
  bvid       TEXT PRIMARY KEY,
  note       TEXT DEFAULT '',
  updated_at INTEGER,
  FOREIGN KEY (bvid) REFERENCES videos(bvid)
);

CREATE TABLE IF NOT EXISTS search_cache (
  cache_key  TEXT PRIMARY KEY,             -- md5(keyword + time_range)
  keyword    TEXT,
  time_range TEXT,
  bvids      TEXT,                         -- JSON 数组，保持抓取顺序
  fetched_at INTEGER
);
```

关键约束：
- videos 按 bvid 去重，重复抓取只更新数据（UPSERT），不产生重复行；
- 收藏/备注外键关联 videos，但删除策略为不级联（数据保留，避免误删）。

---

## 5. 后端 API 设计

| 方法 | 路径 | 请求 | 返回 |
| --- | --- | --- | --- |
| GET | `/` | - | 首页 HTML |
| GET | `/video/{bvid}` | - | 详情页 HTML |
| GET | `/favorites` | - | 我的案例页 HTML |
| POST | `/api/search` | `{keyword, time_range, sort}` | `{items: [视频卡片数据], cached: bool, total}` |
| GET | `/api/video/{bvid}` | - | `{video 全字段, ratios, note, is_favorite}` |
| POST | `/api/video/{bvid}/note` | `{note}` | `{ok}` |
| POST | `/api/video/{bvid}/favorite` | - | `{ok, is_favorite}` |
| DELETE | `/api/video/{bvid}/favorite` | - | `{ok, is_favorite}` |
| GET | `/api/favorites` | - | `{items: [收藏视频卡片]}` |
| GET | `/api/backup` | - | 下载备份 db 文件 |
| POST | `/api/restore` | 上传 .db 文件 | `{ok}` 或错误信息 |

`time_range` 取值：`all` / `7d` / `30d` / `90d`；`sort` 取值：`quality`（默认）/ `view` / `pubdate`。

跳转 B站播放：无需后端接口，前端根据 bvid 构造 `https://www.bilibili.com/video/{bvid}` 用新标签页打开（`target="_blank"`）。

---

## 6. 核心模块实现要点

### 6.1 B站抓取（app/bili/client.py）

**搜索接口**（无需登录）：

```
GET https://api.bilibili.com/x/web-interface/search/type
参数：search_type=video & keyword={关键词} & page=1 & page_size=50
返回：data.result[]，每项含 bvid / title / author / pubdate / duration / pic(封面) / play(播放) / video_review(评论) / danmaku / mid
```

**详情接口**（补全完整指标，逐条调用）：

```
GET https://api.bilibili.com/x/web-interface/view?bvid={bvid}
返回：data.stat = {view, danmaku, reply, favorite, coin, share, like}
     data.owner = {mid, name}
     data.pubdate / data.duration / data.pic / data.tname
```

**请求策略**：
- 请求头：浏览器 UA + `Referer: https://www.bilibili.com/`；
- 频控：详情请求串行，间隔 ≥ 0.8 秒/个；全局每分钟请求数上限 60（config 可调）；
- 超时：10 秒；失败退避重试 3 次（1s / 2s / 4s）；仍失败 → 该视频 `data_complete=0`，跳过继续，不中断整体；
- WBI 签名（app/bili/wbi.py）：**预留实现**——从 `nav` 接口取 `wbi_img` 的 img/sub key 生成 mixin key。当前搜索/详情接口默认不需要签名；若请求返回 412，自动启用签名重试；
- 抓取量：每关键词 1 次搜索 + 50 次详情，串行约 40–60 秒完成，前端显示进度（见 7.3）。

### 6.2 缓存策略（app/services/search.py）

- `cache_key = md5(f"{keyword}|{time_range}")`，有效期 **24 小时**；
- 命中缓存 → 从 videos 表按 bvids 读取、按 sort 排序返回，`cached=true`，**不发起任何 B 站请求**；
- 未命中 → 抓取 → 写入 videos（UPSERT）+ 写入 search_cache → 排序返回；
- 时间范围过滤：`all` 不过滤；`7d/30d/90d` 按 `pubdate ≥ now - N 天` 过滤（抓取后与读取缓存时都过滤，保证一致）。

### 6.3 排序实现（app/services/rank.py）

```
质量分 = 互动率×30% + 收藏率×20% + 播放量分×20% + 投币率×15% + 时效因子×15%
互动率 = (like + coin + favorite + reply) / view
收藏率 = favorite / view
投币率 = coin / view
播放量分 = min(100, log10(view) / log10(1000000) * 100)      # 百万播放封顶 100
时效因子 = min(100, 100 * (1 - 天数差 / 180))                  # 半年内线性衰减，最少不为负
```

- 播放量为 0 或详情缺失（`data_complete=0`）→ 质量分置空，列表置底，标注"数据不全"；
- 三个排序方式：`quality`（质量分降序，空分置底）/ `view`（播放量降序）/ `pubdate`（发布时间降序）；
- 播放量等大数展示统一格式化（如 `1.2万` / `356`），质量分显示为整数。

### 6.4 收藏与备注（app/services/favorite.py）

- 收藏：favorites 表 UPSERT；取消收藏：DELETE；重复收藏不报错；
- 备注：video_notes 表 UPSERT，保存时更新 updated_at；
- 我的案例页 = favorites 关联 videos，按收藏时间倒序。

---

## 7. 前端页面设计

### 7.1 首页（templates/index.html）

- 顶部导航（base.html）：**首页 ｜ 我的案例**；
- 标题区：网站名 + 一句话说明；
- 搜索区：关键词输入框 + 搜索按钮 + 时间范围下拉（全部/近7天/近30天/近90天）；
- 排序切换：三个按钮或下拉（质量分/播放量/发布时间）；
- 结果区：卡片网格（flex 自适应换行），卡片含封面、标题（截断）、UP主、发布时间、播放量、点赞、收藏、评论、质量分徽章（绿色高分为佳，数据不全灰显"数据不全"）；卡片右上角提供"▶ 去B站观看"角标（新标签页打开 `https://www.bilibili.com/video/{bvid}`），点击卡片主体进入站内详情页；
- 状态区：加载中（"正在从 B 站抓取数据，已获取 n/50…"）、无结果、失败提示（含"接口繁忙，请稍后重试"）；
- 页脚：数据来源说明 + "数据仅供个人分析参考" + 导出备份/恢复按钮。

### 7.2 详情页（templates/video.html）

- 视频标题、UP主、发布时间、分区、封面大图；
- 六项指标卡片：播放 / 点赞 / 投币 / 收藏 / 评论 / 弹幕；
- 比率区：互动率、收藏率、投币率（百分比）；
- 备注框：textarea + 保存按钮（保存后提示成功）；
- "去B站观看"按钮（醒目样式，新标签页打开 `https://www.bilibili.com/video/{bvid}`）；
- 收藏按钮（收藏/已收藏 状态切换）；
- 返回首页链接。

### 7.3 交互（static/app.js）

- 搜索：fetch POST `/api/search`；抓取进行中每 3 秒轮询进度（后端提供 `GET /api/search/progress` 返回 `{done, total}`，抓取完成后返回结果）；简化替代：单次请求等结果，前端显示"正在抓取，约 1 分钟"；
- 排序切换 / 时间范围变更：重新请求（命中缓存时秒回）；
- 收藏 / 备注：fetch 调用对应 API，即时更新按钮状态；
- 所有 fetch 统一 try/catch，失败显示页内提示，不白屏。

### 7.4 我的案例页（templates/favorites.html）

- 收藏视频卡片列表（复用首页卡片样式，含"去B站观看"角标）；
- 每张卡片可取消收藏（确认后移除）；
- 空态提示："还没有收藏案例，去首页搜索看看吧"。

---

## 8. 备份与恢复

### 8.1 导出（GET /api/backup + 页脚按钮）

- 将 `data/bili_case.db` 复制到 `backups/bili_case_backup_YYYYmmdd_HHMMSS.db` 后以附件下载；
- 失败（数据库被占用等）时返回明确错误信息。

### 8.2 恢复（POST /api/restore + 页脚按钮，需选文件）

1. 校验上传文件头为 SQLite（`SQLite format 3`），否则拒绝；
2. 先自动备份当前库（同 8.1）；
3. 关闭数据库连接 → 用 `os.replace` 原子替换 `data/bili_case.db` → 重建连接；
4. 返回成功；失败时回滚（保留原库并提示）。

### 8.3 要求（对齐 PRD 7.4）

- 数据文件固定路径 `data/bili_case.db`，不随升级删除；
- 启动时检查数据库可读，异常时页面给出提示而非崩溃；
- 备份/恢复操作均有成功/失败明确反馈。

---

## 9. 部署方案

### 9.1 本地启动

```
cd bili-case-tool
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

提供 `start.bat` 一键执行上述安装+启动（已安装则跳过安装）。

### 9.2 公网访问（内网穿透）

按优先级尝试：

| 方案 | 说明 | 需用户配合 |
| --- | --- | --- |
| Cloudflare Tunnel（trycloudflare） | 免注册，一条命令生成临时公网链接；重启后链接变化 | 无 |
| cpolar 免费版 | 国内访问稳定，需注册免费账号；免费版链接重启后变化 | 注册一个免费账号 |
| ngrok 免费版 | 需注册；国内访问可能不稳定 | 注册账号 |

- 先尝试 trycloudflare（零门槛最快打通，用于验收）；如需长期稳定链接再切 cpolar；
- 提供 `start_tunnel.bat` 封装隧道命令；
- 注意：免费方案链接重启会变化，最终若用户需要固定链接，部署阶段再讨论方案（如付费隧道或云服务器）。

---

## 10. 实施阶段与验收映射

| 阶段 | 任务 | 产出/交付 | 对应 PRD 验收项 |
| --- | --- | --- | --- |
| **P0 环境初始化**（约 0.5 天） | 建目录结构、venv、安装依赖、database.py 建表、config.py | 空壳可启动，数据库文件生成 | 12 |
| **P1 抓取模块**（约 1 天） | bili/client.py（搜索+详情+频控+重试）+ wbi.py 预留 + tests/test_bili.py | 命令行脚本可抓取一个关键词并打印完整数据 | 16 |
| **P2 数据层**（约 0.5 天） | rank.py、search.py（缓存）、favorite.py、tests/test_rank.py、test_cache.py | 数据落库、去重、缓存、排序正确 | 3、4、10 |
| **P3 后端 API**（约 0.5 天） | routes/pages.py、api.py、backup.py | 全部接口 curl 可调通 | 15（备份恢复可调） |
| **P4 前端三页**（约 1 天） | base/index/video/favorites 模板 + style.css + app.js | 浏览器走通：搜索→列表→详情→备注→收藏→案例页→跳转B站播放 | 1、2、6、7、8、9、11、13、17 |
| **P5 缓存与失败验证**（约 0.5 天） | 二次搜索日志验证、断网提示、412 降级 | 日志证明未重复请求；异常有提示 | 10、11、16 |
| **P6 联调与全量验收**（约 1 天） | 按 PRD 第 10 节 18 条逐项实测 | 验收报告（逐项打勾） | 全部 18 条 |
| **P7 部署上线**（约 0.5 天） | start.bat 一键启动、内网穿透公网链接 | 公网链接可访问并完成一次搜索 | 13、14 |

合计约 **5–6 个工作日**。P1–P2 为核心风险点（抓取稳定性），优先完成并验证。

---

## 11. 测试策略

- 单元测试（pytest，不依赖真实网络）：
  - test_rank.py：质量分公式、播放量为 0、数据缺失置底、三种排序；
  - test_cache.py：命中/过期/不同关键词互不串；
  - test_bili.py：mock httpx 返回正常数据 / 412 / 超时 → 验证重试与降级；
- 手工验收：按 PRD 第 10 节逐项执行，记录结果；
- 运行日志：打印每次请求 B 站的数量、命中缓存次数、失败跳过数量，供验收与排查。

---

## 12. 风险与应对

| 风险 | 应对 |
| --- | --- |
| B站风控（412） | 频控 + 低并发 + 重试；必要时启用 WBI 签名；仍不行则降级为只用搜索接口字段（不补详情），标注"数据不全" |
| B站接口字段变动 | 抓取层独立封装，字段映射集中在 client.py，便于快速修复 |
| 首次抓取耗时 40–60 秒 | 前端进度提示；缓存命中后秒回 |
| Python 3.14 个别包不兼容 | 开发时如遇兼容问题，锁定兼容版本或更换等价包 |
| 免费内网穿透链接不稳定/重启变化 | 提供多方案；验收与演示前重新生成链接；长期方案另行确认 |
| 备份恢复误操作 | 恢复前强制先自动备份当前库，且校验 SQLite 文件头 |

---

## 13. 需要用户配合的事项（开发过程中逐步确认）

1. 部署阶段：如 trycloudflare 不可用，需用户注册一个免费 cpolar 账号（约 1 分钟）；
2. 验收阶段：用户需打开公网链接实测一次搜索与收藏；
3. 若最终需要**固定不变**的公网链接，需另行讨论方案与成本。

---

## 14. 开始开发的第一步（P0 具体动作）

1. 在 `D:\Sky Rain's Work\` 下创建 `bili-case-tool` 目录及结构（不含用户既有文件）；
2. 创建 venv 并安装 requirements.txt；
3. 编写 config.py / database.py，启动空壳服务验证可访问；
4. 进入 P1 抓取模块开发。
