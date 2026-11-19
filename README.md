# NearHelp（附近互助）

## MVP 2.0 · 附近互助

当前开发分支把首页改为附近的免费求助。游客可浏览，注册或登录后才能发布、回复和申请协助。发布时需要浏览器定位成功，手动选区仅用于浏览。发布者接受一位帮忙者后，两人可在消息页协调。发布者可标记已解决或取消，过期需求会自动退出附近列表，已建立的私信保留。

- 默认浏览范围为 500 米，可扩大至 1 公里或 3 公里。定位由用户主动开启，已有浏览器授权可在下次打开时复用。
- 活跃统计和公开资料均默认关闭。活跃统计按账号去重，5 分钟后失效。公开资料仅供已登录用户查看，并按约公里级区域及小样本阈值展示。服务端按粗略位置计算距离，客户端不会收到陌生人的坐标。浏览器位置不能作为到场证明。
- 帮忙申请、私信和解决状态由服务端检查权限。可举报或屏蔽相关账号，在「我的」解除屏蔽。举报写入 `help_reports` 供运营审阅，当前没有运营管理页面。第一轮仅支持免费求助。
- 旧版话题与评论继续可通过 `/archive` 或原链接查看。地图保留 Leaflet 和原瓦片配置。新版无需新的地图或账号服务密钥。

### 本地验证新版

首次安装或依赖变化时，按下方本地启动说明安装依赖。建议为联调使用独立数据库。在后端 PowerShell 执行：

```powershell
cd D:\Neartalk\backend
$env:NEARTALK_DB_PATH = 'data/mvp2-local.sqlite3'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

另开一个窗口运行前端：

```powershell
cd D:\Neartalk\frontend
npm.cmd run dev
```

打开 [http://localhost:5173](http://localhost:5173)。用普通窗口和无痕窗口分别注册两个账号，允许浏览器定位后依次测试免费发布、公开回复、申请协助、接受、双向私信和结束需求。未取得可用位置时无法发布，但可手动选区浏览。手机访问其他设备的局域网 HTTP 地址通常无法调用定位，真机验收需要 HTTPS。

后端测试在 `backend/` 运行 `python -m pytest -q`，前端在 `frontend/` 运行 `npm ci` 和 `npm run build`。生产发布前先备份 SQLite，在备份副本验证新增表与旧链接，再打包前后端，按既有发布流程部署并重启服务。新表会自动创建，历史帖子无需转换。首次生产发布后，应实测双账号流程及 HTTPS 下账号 Cookie 的 `Secure` 属性。

## 生产环境

NearHelp 继续使用 https://hacker.guihongyu.com 。服务器通过已有的 `ssh tencent` 配置连接。服务与数据库路径沿用原有标识，后面的原版功能文档供历史版本维护参考。

## 当前服务器维护

- 程序目录为 `/opt/neartalk`，SQLite 数据库为 `/var/lib/neartalk/neartalk.sqlite3`。
- 服务由 systemd 管理，开机自动启动。查看状态用 `sudo systemctl status neartalk`，重启用 `sudo systemctl restart neartalk`，查看日志用 `sudo journalctl -u neartalk -n 100`。
- Nginx 配置位于 `/etc/nginx/sites-available/neartalk`，后端监听 `127.0.0.1:8010`。
- HTTPS 证书由 Certbot 管理，`certbot.timer` 已启用自动续期。
- `deploy/` 保存服务配置、Nginx 配置和发布脚本。旧版验收脚本只适用于稳定基线。

面向校园、宿舍和活动现场的匿名话题社区。打开首页即进入 `cityu-hackathon`。点击右上角的昵称可以修改发言时使用的名字。

## 本地启动

需要 Python 3.12 或更新版本，以及 Node.js 22 或更新版本。以下命令从项目根目录开始，在两个终端分别执行。

### 后端（Windows PowerShell）

```powershell
Copy-Item .env.example .env
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### 后端（Ubuntu）

```bash
cp .env.example .env
cd backend
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

第一次启动会自动建表并创建默认社区。也可在 `backend/` 中用虚拟环境里的 Python 执行 `python -m app.db` 手动初始化。默认数据库是 `backend/data/neartalk.sqlite3`。`.env` 可省略，若设置 `NEARTALK_DB_PATH`，相对路径以 `backend/` 为基准。健康检查地址为 [http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health)。

### 前端

```text
cd frontend
npm ci
npm run dev
```

Windows 若限制 PowerShell 脚本执行，可用 `npm.cmd ci` 和 `npm.cmd run dev`。打开 [http://localhost:5173](http://localhost:5173)。Vite 会把同源的 `/api` 请求转发到本机 8000 端口。

## 验收与测试

### 地图、附近人数与地点社区

- 地图入口是 `/map`。本地开发默认使用 OpenStreetMap 瓦片。低流量交互试点可在构建时设置 `VITE_ALLOW_OSM_TILES=true`，使用时须保留署名、浏览器 Referer 和默认缓存行为，并遵守 [OpenStreetMap 瓦片政策](https://operations.osmfoundation.org/policies/tiles/)。常规生产使用 Geoapify，将 `frontend/.env.example` 复制为 `frontend/.env.local`，设置 `VITE_GEOAPIFY_MAP_KEY` 再构建。瓦片密钥对浏览器可见，应使用专用密钥，并在 Geoapify 控制台限制可用来源。
- 将 `GEOAPIFY_PLACES_KEY` 设置在后端进程环境或项目根目录 `.env` 中。它负责查询地点和首次解析地点时区。未配置时可在九龙塘浏览香港城市大学及邵逸夫图书馆，来源为城大校园目录。地点搜索以约公里精度传递地图中心，默认查询约 2 公里范围，保留数据来源与地点 ID。
- 首页与地图共享浏览地区和范围。进入时自动尝试定位，成功后更新地区。手动选区会在当前标签页保留，直到点击「定位到我」。定位失败时保留上次地区，初次浏览则使用香港九龙塘。默认范围为 5 公里，可切换为 1 公里、10 公里或同城。距离按约 500 米网格的浏览中心计算，同城目前使用香港、深圳、广州的试点覆盖范围。原有城大话题归属九龙塘，首页新话题归属发布时选择的区域。热榜为全站内容。
- 活跃人数默认可见，另行开启统计才会贡献自己的位置。前台约每分钟上报降精度坐标，服务端在选定范围内统计最近 5 分钟活跃的浏览器会话。0、1、2 人直接显示，3 人起显示区间。开启且处于所选范围内时会计入自己。关闭后删除当前会话的位置。浏览器定位可被修改，不能作为到场证明。
- 独立访客由后端签发的 HttpOnly Cookie 区分，同浏览器的普通标签页共享身份。清除 Cookie、隐私窗口和不同浏览器会话可能被分别计数。后台停止上报，位置在查询中 5 分钟后过期，清理任务约每分钟删除过期数据。社区访问单独按地点的 IANA 时区、访客与当地日期去重，访问记录保留约 48 小时。当前所有已发布的社区话题都计为有效。
- 手机端定位需 HTTPS。原版部署使用既有 Nginx 同源 `/api` 和 SPA 路由配置。原版地点服务使用后端地点密钥。

- 用两个独立浏览器会话打开首页。A 发布后跳到详情，B 在保持前台的列表页约 2 秒内看到新话题。B 点开话题并发表评论，A 在详情页约 2 秒内看到回复。刷新页面并重启后端后，检查话题与评论仍在。
- 两部手机实测时，让手机和开发机连接同一局域网，用 `npm run dev -- --host 0.0.0.0` 启动前端并访问 `http://开发机局域网IP:5173`。手机只需访问 5173 端口，后端仍使用本地回环地址。
- 在 `backend/` 用虚拟环境的 Python 执行 `python -m pytest -q`。API 测试使用临时 SQLite 数据库，覆盖默认社区、跨会话读写、重启持久性、输入校验和写入限频。
- 在 `frontend/` 运行 `npm run build`，进行 TypeScript 检查并生成 `dist/`。

昵称、标题、话题正文和评论的长度上限分别为 24、80、2000 和 500 个字符。后端校验去除首尾空白后的值，页面显示当前字数。每个访客每分钟最多发 3 条话题和 12 条评论，同一 IP 每分钟分别最多发 60 条和 240 条。访客标识和昵称保存在浏览器本地，公开接口返回昵称。话题和评论作为纯文本展示。

## 后续部署

在 Ubuntu 上可将 `frontend/dist/` 交给 Nginx 静态托管。页面路由回退到 `index.html`，以支持直接打开话题详情链接。将 `/api/` 原路径代理到监听 `127.0.0.1:8000` 的 Uvicorn，并由 Nginx 提供 HTTPS。若使用代理传递客户端 IP，在 Nginx 用 `$remote_addr` 覆盖 `X-Forwarded-For`，并让 Uvicorn 仅信任本机代理。将 SQLite 放在可持续保存的目录，并授予后端进程读写权限。

后端的社区独立建表，话题通过社区标识归属。以后可以新增位置社区和社区选择页。后续 AI 功能可以接入独立路由或服务，沿用现有话题和评论数据结构。

## 验证知乎官方热榜接口

在[知乎数据开放平台](https://developer.zhihu.com/)个人中心创建 Access Secret，并确认账号具备热榜接口权限和额度。在项目根目录已有的 `.env` 中填入 `ZHIHU_ACCESS_SECRET`。如果尚无该文件，可先复制 `.env.example`。默认请求 10 条，`ZHIHU_CACHE_TTL` 默认是 1800 秒。请将密钥仅存于本地或后端进程环境。

从项目根目录在 PowerShell 中运行验证脚本。

```powershell
cd backend
.\.venv\Scripts\python.exe -m app.check_zhihu
```

在 Ubuntu 中，从 `backend/` 运行 `.venv/bin/python -m app.check_zhihu`。脚本只请求知乎官方接口，成功后输出热榜标题和原文链接。失败时返回非零退出码，并在上游提供相应信息时显示 HTTP 状态、业务码和经过脱敏的消息。

首页通过 `GET /api/hot-topics` 读取服务端热榜。SQLite 缓存有效期默认 30 分钟，刷新失败后可继续用上一份榜单，最长为两倍缓存周期。热点讨论及评论会保留，榜单刷新时按社区、来源和原文 URL 复用讨论入口。同一客户端频繁轮询不会反复请求上游。

可在 `backend/` 通过虚拟环境运行 `python -m app.add_hot_topic "热点标题" "https://example.org/article"`，录入人工热点。部署环境中运行该命令时，使用与服务相同的 `NEARTALK_DB_PATH` 和数据库用户。

上线前请核对账号授权是否覆盖公开展示、缓存及保留历史讨论中的标题和原文链接。先备份 SQLite，再部署后端代码和前端构建产物。通过 NearTalk 的 systemd 环境文件在服务器上配置新密钥，文件权限设为 0600，再重启服务以自动建表。检查 `/api/health` 和 `/api/hot-topics`，并在首页打开一条热点验证评论和原文链接。
