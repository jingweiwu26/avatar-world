# Avatar World — Web

零门槛版本：打开链接、不用登录、点一下就能给世界贡献一样东西、拿到自己的 Avatar。

访客身份是存在浏览器 localStorage 里的一个随机 ID，不对应真实账号——所以这个版本
里"谁贡献的"不再是可验证的真实身份，换个浏览器/清一下 localStorage 就是"新的人"。
想要贡献和真实 GitHub 身份绑定、更强的防篡改保证，用 [../game_online.py](../game_online.py)
终端版。两边写的是同一个世界（同一个 `contributions/` 目录，同一条哈希链），可以共存。

## 本地跑起来

```bash
cd web
npx wrangler pages dev .
```

需要一个 `.dev.vars` 文件（不会被提交），内容：

```
GITHUB_TOKEN=你的token
```

这个 token 需要对 `avatar-world` 仓库有 Contents 读写权限——网页版的写入是
服务端直接用这一个凭证替所有匿名访客提交，不是每个访客各自的 token。

## 部署到 Cloudflare Pages（免费）

```bash
npx wrangler login                        # 浏览器授权一次
cd web
npx wrangler pages deploy . --project-name=avatar-world
```

部署后，在 Cloudflare Dashboard → Pages → avatar-world → Settings → Environment variables
里加一个 secret：`GITHUB_TOKEN`，值是一个 fine-grained PAT（只给 `avatar-world` 仓库
Contents 读写权限，不要用你自己账号权限很大的 token）。加完之后触发一次 redeploy 让它生效。

## 防刷机制（不是强安全边界，够用就行）

- 每个 visitor_id（浏览器本地随机 ID）每天限一次
- 每个 IP 每天也限一次，防止简单清一下 localStorage 就刷无限次
- 内容长度限制在 200 字以内

## 已知限制

- 世界状态读取（`/api/world`）走的是 `raw.githubusercontent.com` 这个 CDN，刚写入的
  内容几十秒内可能还看不到（GitHub CDN 传播延迟）。写入前的每日限额检查走的是
  GitHub 的 Git Blobs API（不走 CDN，强一致），不受这个延迟影响，不会因为这个产生
  重复贡献或哈希链分叉。
- 没有内容审核。这是一个公开、匿名、永久保留的世界，理论上任何人都能写入任意文字
  内容。仓库所有者可以直接删除有问题的贡献文件（会在 `--verify` 里显示为哈希链
  从那个点开始"断开"，这本身就是一种公开、可追溯的审核记录，而不是偷偷摸摸地改）。
