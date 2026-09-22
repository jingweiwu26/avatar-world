# Avatar World

一个共享的持久世界。每个玩家每天做一个动作——往世界里创造/添加一样东西
（颜色 / 词语 / 故事片段 / 规则 / 生物 / 地点）。

你的 Avatar 不是随机生成的图片，而是你贡献历史的可视化压缩：

```
Avatar_i = f(你的贡献历史, 世界状态, 时间)
```

所有贡献都是这个仓库里 `contributions/` 目录下的独立 JSON 文件，永久保留、
带哈希链防篡改（每条记录都指向上一条的哈希），任何人都可以审计整个世界的
演化过程。

## 怎么玩

游戏是完全开放的：**任何人都可以 fork 这个仓库、提贡献，不需要向仓库所有者
申请写权限**。提交的贡献会由 GitHub Action 自动校验（哈希链是否连续、格式
是否正确、今天是否已经贡献过），通过就自动合并进主世界，不需要人工审核。

### 1. 准备一个 GitHub 认证方式

- 本地装了 [`gh`](https://cli.github.com/) 并且 `gh auth login` 过，脚本会自动用它；或者
- 生成一个 [fine-grained personal access token](https://github.com/settings/personal-access-tokens/new)，
  权限选 `Contents: Read and write`（只需要对你自己账号下的 fork 有效，不需要
  这个仓库的写权限），然后：

  ```bash
  export GITHUB_TOKEN=你的token
  ```

### 2. 跑游戏

```bash
python3 game_online.py            # 查看 Avatar，今天贡献一样东西
python3 game_online.py --history  # 看整个世界目前的贡献历史（所有玩家）
python3 game_online.py --verify   # 校验整条哈希链有没有被篡改
```

脚本会自动 fork 这个仓库到你自己账号下、开一个分支、提交贡献、开 PR。
PR 通过校验后由 Action 自动合并——运气好的话几十秒内就能在世界历史里看到。
合并之前 Avatar 卡片显示的还是合并前的状态，再跑一次脚本就会更新。

### 3. 贡献规则（由 `.github/workflows/validate-contribution.yml` 强制执行）

- 一个 PR 只能新增一个贡献文件，不能改动已有文件（世界历史不可编辑）
- 每人每天限一次贡献
- `prev_hash` 必须精确等于主分支当前最新一条贡献的哈希——如果你 fork 之后
  世界又被别人更新了，脚本重新生成的 `prev_hash` 会自动跟上，正常跑一遍就行

## 数据结构

```json
{
  "type": "color | word | story | rule | creature | place",
  "content": "贡献的具体内容",
  "author": "GitHub 用户名",
  "date": "YYYY-MM-DD",
  "timestamp": "ISO 8601 时间戳",
  "prev_hash": "上一条记录的 sha256，null 表示世界的第一条记录",
  "hash": "对本记录（除 hash 字段外）计算的 sha256"
}
```

文件命名：`contributions/<date>-<author>-<hash 前 8 位>.json`

## License

MIT，见 [LICENSE](LICENSE)。
