# Avatar World

一个共享的持久世界。每个玩家每天做一个动作——往世界里创造/添加一样东西
（颜色 / 词语 / 故事片段 / 规则 / 生物 / 地点）。

你的 Avatar 不是随机生成的图片，而是你贡献历史的可视化压缩：

```
Avatar_i = f(你的贡献历史, 世界状态, 时间)
```

所有贡献都以文件形式永久留在这个仓库里，任何人都可以审计整个世界的演化过程。

## 数据结构

每条贡献是 `contributions/` 目录下的一个独立 JSON 文件，命名格式：

```
contributions/<date>-<github-username>-<shorthash>.json
```

文件内容：

```json
{
  "type": "color | word | story | rule | creature | place",
  "content": "贡献的具体内容",
  "author": "GitHub 用户名",
  "date": "YYYY-MM-DD",
  "timestamp": "ISO 8601 时间戳",
  "prev_hash": "上一条记录内容的 sha256，形成防篡改哈希链"
}
```

一条贡献一个文件，避免多个玩家同时贡献时产生 git 冲突。

## 怎么玩

1. 生成一个 GitHub Personal Access Token（fine-grained，只给这个仓库 Contents 读写权限），
   或者本地装了 `gh` 并且 `gh auth login` 过，脚本会自动用 `gh auth token`。
2. 拿到 `avatar_game` 脚本（联系仓库所有者），运行：

```bash
export GITHUB_TOKEN=你的token   # 如果用 gh auth login 可以跳过这步
python3 game_online.py
```

3. 每天最多贡献一次，Avatar 会根据你的完整贡献历史实时重新计算。
