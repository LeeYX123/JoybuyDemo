# 活动页 / 店铺页部署说明（首页「为你推荐」10 个落地页）

> 适用对象：负责把本地已完成的 10 个活动页（9 个 `/active/<id>` + 1 个 `/store/100000744`）发布到服务器的人或 Agent。
> 现象：代码部署后，首页 10 张推荐卡点击仍然跳到旧的 `/search`，没有进 `/active/...`。

## 0. 结论先行：跳转链接不在代码里，在数据库里

首页那 10 张卡的跳转是**数据库行**（`home_campaign_card.href`），不是前端写死的路由。本地这条数据已经改成 `/active/<id>`，服务器上仍然是**首页快照**里的旧卡片。

回退链条（已核对代码）：

1. 接口 `/api/v1/storefront/home` 先查 `home_campaign_card`（`section='campaign'` 且 `enabled=true`）；
2. 查到 → 用这 10 行覆盖 `campaign_grid` 模块；
3. **查不到（或一条都没启用）→ 直接沿用 CMS 首页快照 `cms_module.payload`**；
4. 而快照里那 10 张卡片的 `href` 全是 `/search`（`{title: "Welcome Offers", href: "/search"}` 这种）——你在服务器上看到的就是这一层。

所以：

- 只发代码、只跑 `migrate`，**跳转不会变**；
- 必须把 **CMS 数据**（活动页 + 楼层 + 商品位次 + 首页卡 href）同步到服务器库；
- 活动页图片/视频随代码仓库（`storefront/public/`）发布，不用单独传；
- 商品图走 `/media/`，要看服务器的媒体后端是本地盘还是对象存储。

一句话：**代码 + 迁移 + 数据包 + 静态资源 + 前端重建，五样缺一不可。**

## 1. 先定位到底缺哪一环（5 条命令）

在服务器上按顺序查，哪条不对就修哪条：

```bash
# 1) 卡片行是否存在且启用（期望 10 行、href 全是 /active/ 或 /store/）
python manage.py shell -c "from content.models import HomeCampaignCard as H; print(H.objects.filter(section='campaign').count()); print(list(H.objects.filter(section='campaign').order_by('sort_order').values_list('sort_order','enabled','href')))"

# 1b) 若第 1 条是 0 行：确认前端正在回退到快照（快照里 href 全是 /search）
python manage.py shell -c "from content.models import CmsModule; m=CmsModule.objects.filter(module_type='campaign_grid').first(); print([(i.get('title'), i.get('href')) for i in (m.payload or {}).get('items', [])][:3])"

# 2) 活动页是否真的建出来了（期望 10 行，9 个 ACTIVITY + 1 个 STORE）
python manage.py shell -c "from content.models import ActivityPage; print(ActivityPage.objects.count()); print(list(ActivityPage.objects.values_list('kind','external_id')))"

# 3) 楼层和商品位次是否有数据（期望 sections 48、items 856）
python manage.py shell -c "from content.models import ActivitySection, ActivitySectionProduct; print(ActivitySection.objects.count(), ActivitySectionProduct.objects.count())"

# 4) 前端产物是否有 /active 路由（期望 200，不是 404）
curl -s -o /dev/null -w '%{http_code}\n' https://<域名>/active/7Uw83BgGwFGKHFJYkSfon4pzPsQ

# 5) 接口是否返回页面（期望 JSON 里 sections 有 products）
curl -s https://<域名>/api/v1/activity-pages/active/7Uw83BgGwFGKHFJYkSfon4pzPsQ | head -c 300
```

典型结果对照：

| 现象 | 结论 | 处置 |
| --- | --- | --- |
| 第 1 条 0 行（或全 disabled） | 卡片数据没同步，前端回退到快照的 `/search` 卡片 | 走 2.2 数据包流程 |
| 第 2 条 count=0 | 活动页没建 | 同上 |
| 第 4 条 404 | 前端产物是旧的 | 重新 build + 重启 storefront |
| 第 4 条 200 但页面空白 | 楼层/商品为空 | 检查第 3 条、商品是否在服务器库 |
| 图片 404 | `public/` 资源没进产物或 media 后端不一致 | 见 2.4 / 2.5 |

## 2. 部署步骤

### 2.1 代码

```bash
cd /srv/joybuy            # 或实际代码目录
git pull                  # 目标 commit 含：活动页模型/接口/前端页面/后台配置页
cd backend
../venv/bin/python manage.py migrate --noinput      # content 0020~0025、crawler 0011~0012
../venv/bin/python manage.py showmigrations content # 全部 [X]
../venv/bin/python manage.py collectstatic --noinput
```

> 迁移只建表，不建数据。跑完 `migrate` 后活动页表依然是空的，这是正常的。

### 2.2 数据包（关键一步）

数据包里只有 CMS 数据（页面、楼层、商品位次、首页卡），**不含商品本身**；商品用「来源身份」`joybuy_uk:<source_id>` 关联，服务器按自己的 SPU 解析。

**本地导出**（在有正确数据的机器上执行）：

```bash
.venv/Scripts/python.exe backend/manage.py export_activity_pages \
  --out "E:/code/AgentProject/Joybuy/backend/var/deploy/activity_pages.json"
# 期望输出：pages=10 sections=48 items=856 cards=10 static=34 unresolved=0
```

**上传**：

```bash
scp backend/var/deploy/activity_pages.json <user>@<host>:/srv/joybuy/var/deploy/
```

**服务器导入**（先干跑看清楚能解析多少商品）：

```bash
cd /srv/joybuy/backend
../venv/bin/python manage.py import_activity_pages --bundle /srv/joybuy/var/deploy/activity_pages.json
# 期望：resolved spu=735/735 sku=70/70 missing_spu=0，然后逐页列出 sections/items

../venv/bin/python manage.py import_activity_pages --bundle /srv/joybuy/var/deploy/activity_pages.json --apply
# 期望：IMPORTED items=856 skipped=0；home cards updated: 10, created: 0
#      （服务器若一条 campaign 卡都没有，则是 created: 10 —— 关键，这正是 /search 的来源）
```

`missing_spu > 0` 说明服务器商品库缺这批商品，导入会跳过对应位置并打印预览。此时先跑商品同步/爬虫，再重跑导入（幂等，可重复执行）。

> **只修跳转、不想动页面**：`--apply` 对页面是「同内容整页替换」，不会改变可见结果；如果连这一步都不想跑，也可以只改 10 行：
> ```bash
> python manage.py shell -c "
> from content.models import HomeCampaignCard as H
> for c in H.objects.filter(section='campaign'): print(c.sort_order, c.href)
> "
> ```
> 然后按 `sort_order` 把 `href` 依次改成 `/active/7Uw…`、`/store/100000744`、`/active/3GBT…`、`/active/jnSk…`、`/active/89Hg…`、`/active/295t…`、`/active/TLgE…`、`/active/24EG…`、`/active/4ZXg…`、`/active/3Yu5…`，并确保 `enabled=true`。
> **注意**：`href` 只要有一条不站内、或 `campaign` 一条都没有，前台就会整体回退到 `/search` 快照。

### 2.3 前端与后台重建

```bash
cd /srv/joybuy
pnpm --filter @joybuy/storefront build     # 产物含 /active/[id]、/store/[id] 与 public 静态资源
pnpm --filter @joybuy/admin-web build      # 后台「活动页 / 店铺页」配置页
sudo systemctl restart joybuy-storefront joybuy-api
# admin 静态产物按现网约定放到 /srv/joybuy/admin-dist/
```

### 2.4 静态资源（随代码走，但要确认进产物）

活动页的 banner、轮播图、视频、卡片图都在仓库里：

- `storefront/public/images/activity/**`（约 5.2 MB，42 个文件）
- `storefront/public/videos/activity/**`（约 9.2 MB，店铺页 2 段视频）

`git pull` + `pnpm build` 后应由 Nuxt 输出到 `.output/public`，由 3000 端口直接服务。验证：

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://<域名>/images/activity/pages/7Uw83BgGwFGKHFJYkSfon4pzPsQ/hero.webp   # 期望 200
curl -s -o /dev/null -w '%{http_code}\n' https://<域名>/videos/activity/100000744/video-1.mp4                        # 期望 200
```

### 2.5 商品图（`/media/`）

活动页商品卡用的是商品主图，走 `/media/...`。服务器媒体后端有两种，按实际情况处理：

| `MEDIA_BACKEND` | 处理 |
| --- | --- |
| `local` | 商品图必须存在于 `/srv/joybuy/data/media/`；本地爬的图要 `rsync` 上去，否则卡片图裂 |
| `s3`（Spaces） | 商品图需已在对象存储；nginx 已把 `/media/` 反代到 Spaces（见现网配置），本地新图要先上传 |

### 2.6 缓存

- nginx 对 `/media/` 有 7 天强缓存，换图要换文件名或清缓存；
- Nuxt SSR 没有页面级缓存，但浏览器/反代若有 CDN 需刷新；
- 浏览器强刷一次（Ctrl+F5）再判断是否生效。

## 3. 验收清单

| 项 | 命令 / 方法 | 期望 |
| --- | --- | --- |
| 首页卡行数 | `HomeCampaignCard.objects.filter(section='campaign').count()` | 10（一条都不能少，0 条会整体回退 `/search`） |
| 首页卡链接 | 同上，打印 `(sort_order, href, enabled)` | 10 行全是 `/active/…` 或 `/store/100000744`，`enabled=True` |
| 活动页存在 | `ActivityPage.objects.count()` | 10 |
| 楼层/位次 | `ActivitySection` / `ActivitySectionProduct` | 48 / 856 |
| 接口 | `GET /api/v1/activity-pages/active/<id>` | 200，sections 有 products |
| 页面 | 打开 `/active/7Uw…`、`/active/jnSk…`、`/store/100000744` | 不 404、图片正常、无「不可用」 |
| 首页跳转 | 点首页第一张推荐卡 | 进 `/active/7Uw83BgGwFGKHFJYkSfon4pzPsQ`，不是 `/search` |
| 移动端 | 用手机 UA 或 m. 域名打开同一路径 | 渲染移动端版本 |
| 购物车角标 | 加购后看头部 Cart | 显示总件数，99+ 截断 |

## 4. 回滚

- 数据：导入前先备份 `ActivityPage/ActivitySection/ActivitySectionProduct`（`mysqldump` 或 `pg_dump` 单表）；回滚即恢复这三张表 + `home_campaign_card`。
- 代码：`ln -sfn releases/<prev> current && systemctl reload joybuy`（沿用现有发布方式）。
- 卡片链接可单独回退：把 `home_campaign_card.href` 改回旧值即可让跳转恢复原样，不影响页面数据。

## 5. 已知坑

1. **只发代码不发数据** → 跳转仍是 `/search`，页面 404。这是本次线上现象的直接原因。
2. **`migrate` 不建数据** → 活动页表空着，接口返回 `PAGE_NOT_FOUND`。
3. **管理命令的相对路径按 `backend/` 解析**（`manage.py` 运行时 cwd 在 `backend/`），传 `--out`/`--bundle` 一律用**绝对路径**。
4. **商品缺失是软失败**：导入会跳过并报 `missing_spu`，页面不报错但楼层少卡。先同步商品再重跑导入。
5. **导入是"整页替换"**：同一 `kind+external_id` 的楼层会被清空重建，服务器上手工改过的楼层会被覆盖。部署前确认没有线上手工配置。
6. **店铺页视频 9 MB**，若用 Git LFS 或忽略大文件策略同步，确认视频真的进了产物目录。
