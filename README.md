# NearHelp（附近互助）

## 附近求助与附近讨论

首页切换「附近求助」和「附近讨论」。两个入口共用浏览中心与范围，默认 1 公里。在本地预览可手动选择香港城市大学，进入第一道「会场一问」。初始数据仅含编辑选题，发言始终来自参与者。访客支持公开回答和一级回复，每 3 秒刷新。

管理员在 `/admin` 展开「管理会场一问」，可选会场、题目和知乎问题或回答原文链接。新会场使用管理员当前选择的公开会场中心，更换题目时旧链接继续提供只读历史。同一会场仅有一道进行中的题目。

「管理讨论发言」可下架和恢复回答。下架后，相关回复会从公开页收起，小结同步移除来源；恢复后保留单独下架的回复状态。

发表主回答时自动获取设备位置。服务器根据五分钟内的设备位置、至多 500 米的定位精度及距会场中心 1 公里以内判断是否纳入附近小结和 DeepSeek 整理。服务端只记录是否符合范围。设备位置不可用时仍可发言。小结取最近最多 80 位独立访客各自的一条实质性主回答，达到 3 人后才展示。摘录可点回原回答。

题库的 AI 视角随题目预先准备。在讨论详情的「管理讨论参考资料」中，管理员可以按关键词检索知乎回答并更新 DeepSeek 小结。后端从环境变量读取 `DEEPSEEK_API_KEY` 和 `ZHIHU_ACCESS_SECRET`。没有凭证时仍可使用公开发言和本地摘录。

DeepSeek 小结需要至少三位符合条件的附近访客。缓存中的任何输入被下架或对当前读者不可见时，读者会看到原有摘录。讨论页显示知乎搜索返回的作者、赞同数及摘要，来源链接保留在后台。在账户授权覆盖向第三方模型传输、缓存及展示生成结果时，管理员可配置 `ZHIHU_RAG_ENABLED=true` 来启用观点对照。该设置默认为关闭。

## 访客演示版

两位访客可以在各自的浏览器中发布免费或悬赏需求、公开评论、回复和申请协助。发布者接受一位帮忙者后，双方即可私信，需求变为进行中。发布者标记已解决后，评论和私信可继续查看。悬赏使用港币，金额仅供双方约定。

### 电脑本地运行

在两个 PowerShell 窗口分别执行以下命令。首次使用先按下方「本地启动」安装依赖。有其他 NearHelp 版本运行时也可使用这组独立端口和数据库。

```powershell
cd D:\Neartalk\backend
$env:NEARHELP_DEMO_GUESTS = 'true'
$env:NEARTALK_DB_PATH = 'data/demo-preview.sqlite3'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8186
```

```powershell
cd D:\Neartalk\frontend
$env:NEARHELP_DEV_API_PORT = '8186'
npm.cmd run dev -- --host 127.0.0.1 --port 5286
```

打开 [电脑本地演示](http://127.0.0.1:5286)。用普通窗口和无痕窗口可以分别担任发布者和帮忙者。首次打开会看到系统分配的昵称。点击「获取当前位置」后才会请求位置权限。重新打开或刷新后可手动定位，在原标签页刷新会保留大致浏览区域。

### 两部真机演示

两部手机用 Safari 或 Chrome 直接打开**同一个受信任的 HTTPS 演示地址**。电脑上的回环地址只能用于电脑本机。若使用独立测试域名，按下方「部署前确认」启用演示。也可以在同一 Wi-Fi 内运行以下本地预览。

1. 保持上述后端启动。在电脑用 `ipconfig` 找到 Wi-Fi 的 IPv4 地址。准备覆盖这个 IP、且两部测试手机都信任的开发证书。使用 mkcert 时，可在项目以外的目录执行 `mkcert -cert-file demo.pem -key-file demo-key.pem <电脑的Wi-Fi地址>`。两部测试手机只需安装开发 CA 的公开证书，iOS 还需启用完全信任。私钥留在电脑。测试结束可移除测试 CA。[mkcert 手机证书说明](https://github.com/FiloSottile/mkcert#mobile-devices)
2. 在前端窗口停止原预览，设置环境变量并启动 HTTPS。以下证书文件路径按实际替换。若系统弹出防火墙提示，仅允许专用网络。

```powershell
cd D:\Neartalk\frontend
$env:NEARHELP_DEV_API_PORT = '8186'
$env:NEARHELP_DEV_CERT = 'C:\nearhelp-certs\demo.pem'
$env:NEARHELP_DEV_KEY = 'C:\nearhelp-certs\demo-key.pem'
npm.cmd run dev -- --host 0.0.0.0 --port 5286
```

3. 两部手机打开 `https://电脑的Wi-Fi地址:5286`，分别点击「获取当前位置」。核对昵称不同，界面显示定位成功。若授权被拒，检查系统定位和网站位置权限。只有大致位置时可以浏览，发布需要最近五分钟内且精度在 500 米以内的设备位置。浏览器位置由设备报告，手动选区仅改变浏览中心。[iPhone 定位设置](https://support.apple.com/en-us/102647) · [Android Chrome 网站权限](https://support.google.com/chrome/answer/142065?co=GENIE.Platform%3DAndroid)
4. A 发布「借一个 Type-C 充电器半小时」，选择悬赏 HK$5、1 小时。B 保持「附近」页，通常在一次 6 秒轮询内看到。若两部手机的定位精度相差较大，可将浏览范围扩大至 1 公里。
5. B 打开评论并留言，A 点该条评论下的「回复」。B 单独点击「我能帮忙」，A 在「消息」中接受。两人互发一条私信，再各自刷新。A 回到关联需求点「标记已解决」，B 的附近列表应移除它。「我的」仍能打开详情和聊天记录。
6. 额外检查拒绝定位后的手动浏览、拒绝协助、免费需求，以及第三位访客打开私信直链时的访问限制。

### 数据、权限与清理

服务端的 `NEARHELP_DEMO_GUESTS` 默认关闭。开启时，互助接口接受带 HttpOnly、SameSite=Strict 凭证的访客，HTTPS 下同时设置 Secure。凭证有效期 30 天，SQLite 仅保存凭证摘要。清除网站数据会失去该访客身份的访问权。原有注册账号保留，账号登录和访客会话使用不同 Cookie。关闭开关并重启后，已有访客凭证也不能操作互助接口。旧讨论的写权限仍要求注册账号。

需求和私信的所有权、会话成员、拉黑、举报和限频均由后端检查。每身份每分钟上限为发布 3 条、评论或回复 15 条、协助申请 12 次、私信 30 条，另有按 IP 的限制。标题、说明和评论或私信的上限分别是 80、2000 和 500 字。新访客和新注册用户默认参与附近统计并允许展示昵称。授权定位后按 1 公里范围刷新，可在「我的」分别关闭两个开关。已有用户的设置继续生效。公开卡片只展示大致距离。

演示数据建议放入独立 SQLite 文件。要移除单场测试，在后端目录先运行下列预览命令。数字改为测试需求详情链接末尾的编号。核对标题后追加 `--apply`，会在一个事务内删除该访客需求及其关联的评论、申请、私信和举报。命令拒绝清理注册账号发布的需求。

```powershell
.\.venv\Scripts\python.exe -m app.clean_demo --db data/demo-preview.sqlite3 --request 1
```

### 管理公开需求

管理员从 `/admin` 登录，也可以在「我的」进入「管理公开需求」。列表可按公开或下架状态筛选，查看正文和举报次数。点击「下架」后，需求从附近列表、地图和公开详情移除。在「已下架」中可以恢复。已建立的私信仍由原会话参与者访问。

待解决的公开需求可在原有浏览半径内置顶，最多 12 小时，到需求过期时提前结束。进入处理、解决、取消或下架后也会结束置顶。「取消置顶」立即恢复普通排序。

首次建号在服务器的后端目录由维护者执行下列命令。命令提示输入并确认密码，只接受未被注册过的新账号名。数据库沿用正在运行的实例。

```sh
cd /opt/neartalk/backend
sudo -u neartalk .venv/bin/python -m app.create_admin --db /var/lib/neartalk/neartalk.sqlite3 --username YOUR_NEW_USERNAME
```

### 重跑自动验收

后端在 `backend/` 运行 `.\.venv\Scripts\python.exe -m pytest -q`。前端在 `frontend/` 依次运行 `npm.cmd ci`、`npm.cmd run build` 和 `npm.cmd run test:demo`。浏览器测试需要本机 Chrome、后端虚拟环境及已构建的前端。测试会自动启动临时服务，创建并清理独立数据库，使用测试设备位置。验证 WebKit 可先运行 `npx.cmd playwright-core install webkit`，再运行 `npm.cmd run test:demo -- --webkit`。如果当前终端已配置上文开发证书，测试同样会走 HTTPS。

### 部署前确认

确认演示域名、启用时间和数据库路径，建议先使用独立演示数据库和受信任 HTTPS。若升级现有实例，先备份 SQLite，在副本验证升级，再部署同一版本的前后端。启动时会自动添加访客标志、悬赏金额和回复关联列，旧需求默认为免费。沿用 Nginx 同源 `/api` 反向代理，保留原始 Host 和 HTTPS 协议，直接在浏览器中打开页面。地图沿用现有瓦片配置。没有新增服务密钥。上线后用两部真机复测定位、Cookie 和完整流程。

## 生产环境

NearHelp 继续使用 https://hacker.guihongyu.com 。服务器通过已有的 `ssh tencent` 配置连接。服务与数据库路径沿用原有标识，后面的原版功能文档供历史版本维护参考。

## 当前服务器维护

- 程序目录为 `/opt/neartalk`，SQLite 数据库为 `/var/lib/neartalk/neartalk.sqlite3`。
- 服务由 systemd 管理，开机自动启动。查看状态用 `sudo systemctl status neartalk`，重启用 `sudo systemctl restart neartalk`，查看日志用 `sudo journalctl -u neartalk -n 100`。
- Nginx 配置位于 `/etc/nginx/sites-available/neartalk`，后端监听 `127.0.0.1:8010`。
- HTTPS 证书由 Certbot 管理，`certbot.timer` 已启用自动续期。
- `deploy/` 保存服务配置、Nginx 配置和发布脚本。旧版验收脚本只适用于稳定基线。

下方保留基础安装命令和旧版匿名话题社区的维护记录。当前演示版的首页、权限、范围和真机运行方式见本文开头。

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
- 两部手机验收定位和互助流程请使用上文「两部真机演示」中的 HTTPS 配置。
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
