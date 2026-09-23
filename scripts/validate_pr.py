#!/usr/bin/env python3
"""
校验一个贡献 PR 是否合法，合法就把 PR 标记为可以自动合并。

设计上刻意不 checkout / 执行 fork 里的任何代码——只通过 GitHub API
读取 PR 改动的文件内容（数据），在 pull_request_target 场景下用
有特权的 token 直接执行 fork 来源的代码是已知的安全隐患。

校验规则：
  1. PR 只能新增（不能修改/删除）contributions/ 目录下的文件
  2. 只能新增恰好一个文件
  3. 文件名格式必须是 contributions/<date>-<author>-<hash8>.json
  4. JSON 必须包含全部必需字段，且各字段互相一致（文件名里的 date/author
     要和内容里的一致）
  5. content.author 必须等于 PR 提交者的 GitHub 用户名（防止冒充别人贡献）
  6. content.hash 必须是对 content（去掉 hash 字段后）重新计算的 sha256
  7. content.prev_hash 必须等于当前主分支上最新一条贡献的 hash（防止
     基于过期状态提交，保证哈希链严格递增、不分叉）
  8. 同一个作者同一天不能有两条贡献（主分支上已存在的记录里查重）
"""

import hashlib
import json
import os
import re
import subprocess
import sys

REPO = os.environ["GITHUB_REPOSITORY"]  # "owner/repo"
BASE_SHA = os.environ["BASE_SHA"]
HEAD_SHA = os.environ["HEAD_SHA"]
PR_NUMBER = os.environ["PR_NUMBER"]
PR_AUTHOR = os.environ["PR_AUTHOR"]

FILENAME_RE = re.compile(r"^contributions/(\d{4}-\d{2}-\d{2})-([\w-]+)-([0-9a-f]{8})\.json$")
VALID_TYPES = {"color", "word", "story", "rule", "creature", "place"}
REQUIRED_FIELDS = {"type", "content", "author", "date", "timestamp", "prev_hash", "hash"}


def fail(msg):
    print(f"::error::{msg}")
    sys.exit(1)


def gh_api(path, **kwargs):
    result = subprocess.run(
        ["gh", "api", path], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        fail(f"GitHub API 调用失败 ({path}): {result.stderr}")
    return json.loads(result.stdout)


def gh_api_raw(path):
    result = subprocess.run(
        ["gh", "api", path, "-H", "Accept: application/vnd.github.raw"],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        fail(f"GitHub API 调用失败 ({path}): {result.stderr}")
    return result.stdout


def compute_hash(entry):
    """紧凑、无空格、key 排序的 JSON——必须和网页版 JS 实现字节对字节一致。"""
    payload = {k: v for k, v in entry.items() if k != "hash"}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def main():
    files = gh_api(f"repos/{REPO}/pulls/{PR_NUMBER}/files")

    added = [f for f in files if f["status"] == "added"]
    non_added = [f for f in files if f["status"] != "added"]
    outside = [f for f in files if not f["filename"].startswith("contributions/")]

    if non_added:
        fail(f"PR 只允许新增贡献文件，不能修改或删除已有文件: {[f['filename'] for f in non_added]}")
    if outside:
        fail(f"PR 只允许改动 contributions/ 目录下的文件: {[f['filename'] for f in outside]}")
    if len(added) != 1:
        fail(f"每个 PR 必须且只能新增一个贡献文件，实际新增了 {len(added)} 个")

    filename = added[0]["filename"]
    m = FILENAME_RE.match(filename)
    if not m:
        fail(f"文件名格式不对: {filename}，应为 contributions/<date>-<author>-<hash8>.json")
    fn_date, fn_author, fn_hash8 = m.groups()

    raw = gh_api_raw(f"repos/{REPO}/contents/{filename}?ref={HEAD_SHA}")
    try:
        entry = json.loads(raw)
    except json.JSONDecodeError:
        fail("文件内容不是合法 JSON")

    missing = REQUIRED_FIELDS - entry.keys()
    if missing:
        fail(f"缺少必需字段: {missing}")
    if entry["type"] not in VALID_TYPES:
        fail(f"type 不合法: {entry['type']}")
    if not str(entry["content"]).strip():
        fail("content 不能为空")
    if entry["author"] != PR_AUTHOR:
        fail(f"author 字段 ({entry['author']}) 与 PR 提交者 ({PR_AUTHOR}) 不一致")
    if entry["date"] != fn_date:
        fail(f"文件名日期 ({fn_date}) 与内容 date 字段 ({entry['date']}) 不一致")
    if entry["author"] != fn_author:
        fail(f"文件名作者 ({fn_author}) 与内容 author 字段 ({entry['author']}) 不一致")

    recomputed = compute_hash(entry)
    if recomputed != entry["hash"]:
        fail(f"哈希校验失败，内容可能被篡改或计算方式不对（期望 {recomputed}，实际 {entry['hash']}）")
    if not recomputed.startswith(fn_hash8):
        fail("文件名里的哈希前缀和内容哈希对不上")

    tree = gh_api(f"repos/{REPO}/git/trees/{BASE_SHA}?recursive=1")
    existing_paths = [
        item["path"] for item in tree.get("tree", [])
        if item["path"].startswith("contributions/") and item["path"].endswith(".json")
    ]
    existing = []
    for path in existing_paths:
        raw = gh_api_raw(f"repos/{REPO}/contents/{path}?ref={BASE_SHA}")
        try:
            existing.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    existing.sort(key=lambda x: x.get("timestamp", ""))

    expected_prev_hash = existing[-1]["hash"] if existing else None
    if entry["prev_hash"] != expected_prev_hash:
        fail(
            "prev_hash 跟主分支当前最新一条记录对不上，说明这个 PR 是基于过期的世界状态提交的，"
            "请同步最新状态后重新贡献。"
        )

    if any(x["author"] == entry["author"] and x["date"] == entry["date"] for x in existing):
        fail(f"{entry['author']} 在 {entry['date']} 已经贡献过一次了，每天限一次。")

    print("全部校验通过。")


if __name__ == "__main__":
    main()
