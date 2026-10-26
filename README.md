# B站优质视频案例库

一个面向内容运营 / 市场调研的检索工具：输入关键词，从 B站 抓取公开视频数据，按**质量分**（互动率、收藏率、投币率、播放量、时效）排序，帮你在大量结果里先筛出值得点开的案例。

- 后端：FastAPI + httpx + SQLite（只做搜索缓存）
- 前端：Jinja2 模板 + 原生 CSS/JS（无构建步骤）
- 收藏与备注：存在**浏览器 localStorage**，不上传、不共享
- 部署：Render 免费层（`render.yaml` 已就绪）

## 本地运行

```bat
start.bat
```

或手动：

```sh
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

然后打开 http://127.0.0.1:8000 。首次运行会自动建表（`data/bili_case.db`）。

## 配置（app/config.py）

| 项 | 默认 | 说明 |
|---|---|---|
| `SEARCH_MAX_RESULTS` | 24 | 单次搜索最多处理/展示条数 |
| `DETAIL_CONCURRENCY` | 5 | 详情并发数 |
| `DETAIL_INTERVAL` | 0.15 | 相邻详情请求最小间隔（秒） |
| `RATE_LIMIT_PER_MINUTE` | 8 | 单 IP 每分钟搜索次数 |
| `GLOBAL_SEARCH_CONCURRENCY` | 2 | 同时进行的搜索任务上限 |
| `CACHE_TTL_SECONDS` | 86400 | 搜索结果缓存有效期 |

> 并发与限流是为了**保护服务器 IP 不被 B站 风控**。调大并发会更快，但被封的概率也更高。

## 部署到 Render（免费）

1. 把这个目录推到一个 GitHub 仓库（public 或 private 都可以）。
2. 打开 [render.com](https://render.com)，用 GitHub 账号登录。
3. **New → Blueprint** → 选择这个仓库。Render 会自动读取 `render.yaml`。
4. 点 **Apply**，等 2–3 分钟构建完成，会得到一个固定网址：`https://<服务名>.onrender.com`。
5. 之后每次 `git push`，Render 会自动重新部署。

免费层的两个已知限制：

- **闲置 15 分钟会休眠**，再次访问需要等 30–60 秒冷启动。
- **磁盘是临时的**：重启后 SQLite 里的搜索缓存会清空（不影响收藏，收藏在浏览器里）。

## 目录结构

```
app/
  main.py          FastAPI 入口
  config.py        路径、抓取、限流参数
  database.py      SQLite 建表
  utils.py         展示层格式化
  bili/client.py   B站 接口客户端（搜索 / 详情 / WBI 签名）
  bili/wbi.py      WBI 签名算法
  routes/pages.py  页面路由
  routes/api.py    JSON API（含限流）
  services/search.py  搜索编排（缓存 → 并发抓详情 → 入库 → 排序）
  services/rank.py    质量分与排序
  templates/       Jinja2 页面
  static/          style.css / app.js
tests/             pytest 用例
render.yaml        Render 部署描述
```

## 测试

```sh
.venv\Scripts\python.exe -m pytest -q
```

测试全部使用 mock，不会真的请求 B站。
