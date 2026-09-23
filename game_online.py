#!/usr/bin/env python3
"""
Avatar World — 多人共享世界版本。

世界状态存在一个公开 GitHub 仓库里（jingweiwu26/avatar-world），
每条贡献是 contributions/ 目录下的一个独立 JSON 文件，
所有玩家的贡献共同构成同一个世界。

认证：
  - 环境变量 GITHUB_TOKEN（fine-grained PAT，只需要目标仓库的 Contents 读写权限），或
  - 本地装了 gh 并且已经 `gh auth login` 过，脚本会自动用 `gh auth token` 取

读写世界完全通过 GitHub REST API 完成，玩家不需要在本地装 git。
"""

import base64
import hashlib
import json
import os
import ssl
import subprocess
import sys
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime, date

try:
    import certifi
    SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CONTEXT = ssl.create_default_context()

OWNER = os.environ.get("GITHUB_OWNER", "jingweiwu26")
REPO = os.environ.get("GITHUB_REPO", "avatar-world")
BRANCH = "main"
API_ROOT = f"https://api.github.com/repos/{OWNER}/{REPO}"
RAW_ROOT = f"https://raw.githubusercontent.com/{OWNER}/{REPO}/{BRANCH}"

TYPES = {
    "1": ("color", "颜色", "给世界添加一种颜色"),
    "2": ("word", "词语/概念", "给世界添加一个词语或概念"),
    "3": ("story", "故事片段", "写一小段发生在这个世界里的故事"),
    "4": ("rule", "规则", "为这个世界定一条规则"),
    "5": ("creature", "生物", "创造一种生活在这个世界里的生物"),
    "6": ("place", "地点", "命名一个世界里的地点"),
}

FACES = ["(｡◕‿◕｡)", "(๑˃ᴗ˂)ﻭ", "( •_•)", "(≧◡≦)", "(⌐■_■)", "(°◡°)", "(ノ◕ヮ◕)ノ", "(◔_◔)"]

TITLES = [
    (0, "游荡者"),
    (1, "初来者"),
    (3, "贡献者"),
    (6, "建造者"),
    (10, "长居者"),
    (20, "传奇"),
]

ANSI = {
    "reset": "\033[0m", "bold": "\033[1m", "dim": "\033[2m",
    "cyan": "\033[36m", "yellow": "\033[33m", "magenta": "\033[35m",
    "green": "\033[32m", "blue": "\033[34m",
}


def c(text, color):
    return f"{ANSI[color]}{text}{ANSI['reset']}"


# ---------- GitHub API ----------

def get_token():
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        return token
    try:
        result = subprocess.run(
            ["gh", "auth", "token"], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    print(c("没有找到 GitHub 凭证。", "bold"))
    print("要么设置环境变量 GITHUB_TOKEN，要么本地装 gh 并 `gh auth login`。")
    sys.exit(1)


def api_call(url, method="GET", body=None, token=None, ok_statuses=None):
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, context=SSL_CONTEXT) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        if ok_statuses and e.code in ok_statuses:
            return None
        msg = e.read().decode()
        print(c(f"GitHub API 错误 ({e.code}) {method} {url}: {msg}", "bold"))
        sys.exit(1)


def api_request(path, method="GET", body=None, token=None, ok_statuses=None):
    return api_call(f"{API_ROOT}{path}", method=method, body=body, token=token, ok_statuses=ok_statuses)


def get_username(token):
    req = urllib.request.Request(
        "https://api.github.com/user",
        headers={"Accept": "application/vnd.github+json", "Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, context=SSL_CONTEXT) as resp:
        return json.loads(resp.read().decode())["login"]


def fetch_all_contributions():
    tree = api_request(f"/git/trees/{BRANCH}?recursive=1")
    paths = [
        item["path"] for item in tree.get("tree", [])
        if item["path"].startswith("contributions/") and item["path"].endswith(".json")
    ]
    contributions = []
    failed = 0
    for path in paths:
        try:
            with urllib.request.urlopen(f"{RAW_ROOT}/{path}", context=SSL_CONTEXT) as resp:
                contributions.append(json.loads(resp.read().decode()))
        except urllib.error.URLError:
            failed += 1
    if failed:
        print(c(
            f"警告: {failed} 条贡献暂时读取失败（可能是 CDN 缓存延迟，刚写入的文件几十秒内会出现），"
            "世界状态可能不完整，过一会再试。",
            "dim",
        ))
    contributions.sort(key=lambda x: x.get("timestamp", ""))
    return contributions


def has_push_access(token):
    repo = api_request("", token=token)
    return bool(repo.get("permissions", {}).get("push"))


def ensure_fork(token, username):
    fork_url = f"https://api.github.com/repos/{username}/{REPO}"
    existing = api_call(fork_url, token=token, ok_statuses={404})
    if existing:
        return
    api_request("/forks", method="POST", body={}, token=token)
    import time
    for _ in range(15):
        if api_call(fork_url, token=token, ok_statuses={404}):
            return
        time.sleep(2)
    print(c("Fork 创建超时，稍后重试一次。", "bold"))
    sys.exit(1)


def get_branch_sha(owner, branch, token):
    ref = api_call(
        f"https://api.github.com/repos/{owner}/{REPO}/git/ref/heads/{branch}", token=token
    )
    return ref["object"]["sha"]


def create_branch(owner, new_branch, from_sha, token):
    api_call(
        f"https://api.github.com/repos/{owner}/{REPO}/git/refs",
        method="POST",
        body={"ref": f"refs/heads/{new_branch}", "sha": from_sha},
        token=token,
    )


def create_file(owner, path, content_str, message, branch, token):
    body = {
        "message": message,
        "content": base64.b64encode(content_str.encode()).decode(),
        "branch": branch,
    }
    api_call(f"https://api.github.com/repos/{owner}/{REPO}/contents/{path}", method="PUT", body=body, token=token)


def open_pr(head_owner, head_branch, title, body_text, token):
    head = head_branch if head_owner == OWNER else f"{head_owner}:{head_branch}"
    pr = api_request(
        "/pulls", method="POST",
        body={"title": title, "head": head, "base": BRANCH, "body": body_text},
        token=token,
    )
    return pr["html_url"]


def push_contribution(entry, token, username):
    filename = f"{entry['date']}-{entry['author']}-{entry['hash'][:8]}.json"
    path = f"contributions/{filename}"
    content_str = json.dumps(entry, ensure_ascii=False, indent=2)
    branch_name = f"contribute/{entry['date']}-{entry['hash'][:8]}"

    if has_push_access(token):
        head_owner = OWNER
    else:
        head_owner = username
        ensure_fork(token, username)

    base_sha = get_branch_sha(head_owner, BRANCH, token)
    create_branch(head_owner, branch_name, base_sha, token)
    create_file(head_owner, path, content_str, f"contribute({entry['type']}) by {username}", branch_name, token)
    return open_pr(
        head_owner, branch_name,
        f"contribute({entry['type']}) by {username}",
        f"自动生成的贡献 PR，通过后会由 GitHub Action 校验并自动合并。\n\n类型: {entry['type']}\n内容: {entry['content']}",
        token,
    )


# ---------- Avatar logic ----------

def title_for(count):
    result = TITLES[0][1]
    for threshold, name in TITLES:
        if count >= threshold:
            result = name
    return result


def face_for(contributions):
    if not contributions:
        return FACES[0]
    blob = "".join(item["content"] for item in contributions)
    idx = int(hashlib.sha256(blob.encode()).hexdigest(), 16) % len(FACES)
    return FACES[idx]


def canonical_hash(entry):
    """哈希输入用紧凑、无空格、key 排序的 JSON——必须和网页版 JS 实现字节对字节一致。"""
    payload = {k: v for k, v in entry.items() if k != "hash"}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def avatar_code(contributions):
    if not contributions:
        return "AVT-0000"
    blob = "|".join(f"{item['type']}:{item['content']}" for item in contributions)
    h = hashlib.sha256(blob.encode()).hexdigest()[:6].upper()
    return f"AVT-{h}"


def build_avatar(my_contributions, world_contributions, username):
    count = len(my_contributions)
    colors = [x["content"] for x in my_contributions if x["type"] == "color"]
    types_used = {x["type"] for x in my_contributions}
    traits = []
    if "color" in types_used:
        traits.append("调色者")
    if "word" in types_used:
        traits.append("命名者")
    if "story" in types_used:
        traits.append("说书人")
    if "rule" in types_used:
        traits.append("立法者")
    if "creature" in types_used:
        traits.append("造物主")
    if "place" in types_used:
        traits.append("拓荒者")
    if len(types_used) >= 6:
        traits.append("全能建造者")

    days = sorted({x["date"] for x in my_contributions})
    creatures = [x["content"] for x in my_contributions if x["type"] == "creature"]

    first_authors = []
    for item in world_contributions:
        if item["author"] not in first_authors:
            first_authors.append(item["author"])
    rank = first_authors.index(username) + 1 if username in first_authors else None

    return {
        "code": avatar_code(my_contributions),
        "face": face_for(my_contributions),
        "title": title_for(count),
        "count": count,
        "days": len(days),
        "first_day": days[0] if days else None,
        "colors": colors,
        "creatures": creatures,
        "traits": traits or ["尚未定型"],
        "rank": rank,
        "world_contributors": len(first_authors),
        "world_total": len(world_contributions),
    }


def visible_len(text):
    result = text
    for code in ANSI.values():
        result = result.replace(code, "")
    width = 0
    for ch in result:
        width += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return width


def render_card(avatar):
    width = 44
    lines = []
    lines.append("┌" + "─" * width + "┐")

    def row(text):
        pad = width - visible_len(text)
        lines.append("│" + text + " " * max(pad, 0) + "│")

    def row_centered(text):
        pad = width - visible_len(text)
        left = pad // 2
        right = pad - left
        lines.append("│" + " " * max(left, 0) + text + " " * max(right, 0) + "│")

    row_centered(c(avatar["code"], "bold"))
    row("")
    row_centered(c(avatar["face"], "cyan"))
    row("")
    companion = f"  同伴: {avatar['creatures'][-1]}" if avatar["creatures"] else ""
    row(f"  称号: {c(avatar['title'], 'yellow')}{companion}")
    rank_str = f"第 {avatar['rank']} 位加入此世界的人" if avatar["rank"] else "尚未加入此世界"
    row(f"  起源: {rank_str}")
    colors_str = "、".join(avatar["colors"][-3:]) if avatar["colors"] else "（无）"
    row(f"  色彩: {c(colors_str, 'magenta')}")
    traits_str = "、".join(avatar["traits"])
    row(f"  特质: {c(traits_str, 'green')}")
    row(f"  历史: 共 {avatar['count']} 次贡献 · {avatar['days']} 天")
    lines.append("├" + "─" * width + "┤")
    row(f"  世界: {avatar['world_contributors']} 位玩家 · 共 {avatar['world_total']} 次贡献")
    lines.append("└" + "─" * width + "┘")
    return "\n".join(lines)


def already_contributed_today(my_contributions):
    today = date.today().isoformat()
    return any(x["date"] == today for x in my_contributions)


def prompt_contribution(username, last_hash):
    print()
    print(c("今天想为这个世界创造点什么？", "bold"))
    for key, (_, label, hint) in TYPES.items():
        print(f"  [{key}] {label} — {hint}")
    choice = input(c("选一个类型 (1-6): ", "dim")).strip()
    if choice not in TYPES:
        print("没有这个选项，取消。")
        return None
    type_key, label, hint = TYPES[choice]
    content = input(c(f"写下你的{label}: ", "dim")).strip()
    if not content:
        print("空的贡献不会被世界记住，取消。")
        return None
    entry = {
        "type": type_key,
        "content": content,
        "author": username,
        "date": date.today().isoformat(),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "prev_hash": last_hash,
    }
    entry["hash"] = canonical_hash(entry)
    return entry


def show_history(world_contributions):
    if not world_contributions:
        print("这个世界还什么都没有。")
        return
    print(c(f"\n世界历史（共 {len(world_contributions)} 条,来自所有玩家）：", "bold"))
    for item in world_contributions:
        label = dict((v[0], v[1]) for v in TYPES.values())[item["type"]]
        print(f"  {item['date']}  [{label}] {item['content']}  —— {item['author']}")


def verify_chain(world_contributions):
    broken = []
    for item in world_contributions:
        recomputed = canonical_hash(item)
        if item.get("hash") != recomputed:
            broken.append(item)
    return broken


def main():
    args = sys.argv[1:]
    token = get_token()
    username = get_username(token)

    print(c(f"正在同步世界状态（{OWNER}/{REPO}）...", "dim"))
    world_contributions = fetch_all_contributions()

    if "--history" in args:
        show_history(world_contributions)
        return

    if "--verify" in args:
        broken = verify_chain(world_contributions)
        if broken:
            print(c(f"发现 {len(broken)} 条记录哈希不匹配，可能被篡改：", "bold"))
            for item in broken:
                print(f"  {item.get('date')} {item.get('author')} {item.get('content')}")
        else:
            print(c(f"全部 {len(world_contributions)} 条记录哈希链验证通过。", "green"))
        return

    my_contributions = [x for x in world_contributions if x["author"] == username]
    avatar = build_avatar(my_contributions, world_contributions, username)
    print()
    print(render_card(avatar))

    force = "--force" in args
    if already_contributed_today(my_contributions) and not force:
        print(c("\n今天已经为这个世界贡献过了，明天再来。", "dim"))
        return

    last_hash = world_contributions[-1]["hash"] if world_contributions else None
    contribution = prompt_contribution(username, last_hash)
    if contribution is None:
        return

    print(c("正在提交贡献 PR...", "dim"))
    pr_url = push_contribution(contribution, token, username)
    print()
    print(c("PR 已提交，等待自动校验合并：", "bold"))
    print(f"  {pr_url}")
    print(c("合并后再跑一次这个脚本，Avatar 就会更新。", "dim"))


if __name__ == "__main__":
    main()
