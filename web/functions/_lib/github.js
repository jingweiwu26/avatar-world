export const OWNER = "jingweiwu26";
export const REPO = "avatar-world";
export const BRANCH = "main";

async function fetchTree() {
  const treeResp = await fetch(
    `https://api.github.com/repos/${OWNER}/${REPO}/git/trees/${BRANCH}?recursive=1`,
    { headers: { "User-Agent": "avatar-world-web" } }
  );
  if (!treeResp.ok) throw new Error(`tree fetch failed: ${treeResp.status}`);
  const tree = await treeResp.json();
  return (tree.tree || []).filter(
    (item) => item.path.startsWith("contributions/") && item.path.endsWith(".json")
  );
}

// 给公开只读展示用（/api/world）：走 raw.githubusercontent.com 这个 CDN，快、不占
// GitHub API 配额，但刚写入的文件几十秒内可能还读不到（CDN 传播延迟）。
export async function fetchWorld() {
  const items = await fetchTree();
  const contributions = [];
  for (const item of items) {
    const raw = await fetch(`https://raw.githubusercontent.com/${OWNER}/${REPO}/${BRANCH}/${item.path}`);
    if (raw.ok) {
      try {
        contributions.push(await raw.json());
      } catch (_) {
        // skip malformed
      }
    }
  }
  contributions.sort((a, b) => (a.timestamp || "").localeCompare(b.timestamp || ""));
  return contributions;
}

// 给写入前的校验用（每日限额 / prev_hash 检查）：必须读到最新状态，不能有 CDN 延迟，
// 不然两次间隔几十秒内的提交会互相看不见对方，导致同一个人绕过每日限制、
// 哈希链分叉。直接用 Git Blobs API 读 blob 内容，这个是强一致的、不走 CDN 缓存。
export async function fetchWorldAuthoritative(token) {
  const items = await fetchTree();
  const contributions = [];
  for (const item of items) {
    const resp = await fetch(
      `https://api.github.com/repos/${OWNER}/${REPO}/git/blobs/${item.sha}`,
      {
        headers: {
          Authorization: `Bearer ${token}`,
          Accept: "application/vnd.github+json",
          "User-Agent": "avatar-world-web",
        },
      }
    );
    if (!resp.ok) continue;
    const blob = await resp.json();
    try {
      const text = decodeURIComponent(escape(atob(blob.content.replace(/\n/g, ""))));
      contributions.push(JSON.parse(text));
    } catch (_) {
      // skip malformed
    }
  }
  contributions.sort((a, b) => (a.timestamp || "").localeCompare(b.timestamp || ""));
  return contributions;
}

// 紧凑、无空格、key 排序的 JSON —— 必须和 Python 版 (game_online.py / validate_pr.py)
// 的 canonical_hash / compute_hash 字节对字节一致，这样两边写入的记录能共用同一条哈希链。
export function canonicalJson(entry) {
  const keys = Object.keys(entry)
    .filter((k) => k !== "hash")
    .sort();
  const parts = keys.map((k) => JSON.stringify(k) + ":" + JSON.stringify(entry[k]));
  return "{" + parts.join(",") + "}";
}

export async function sha256Hex(str) {
  const bytes = new TextEncoder().encode(str);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export async function computeHash(entry) {
  return sha256Hex(canonicalJson(entry));
}

export function jsonResponse(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Access-Control-Allow-Origin": "*",
    },
  });
}

function base64EncodeUtf8(str) {
  const bytes = new TextEncoder().encode(str);
  let binary = "";
  bytes.forEach((b) => (binary += String.fromCharCode(b)));
  return btoa(binary);
}

// 直接在 branch 上创建文件（用机器人 token，走 Contents API）。
// 网页版只有一个受信任的写入方（这个 Worker 自己），不需要像终端版那样
// 走 fork+PR，直接写主分支就行。
export async function createFile(path, contentStr, message, token, branch = BRANCH) {
  const body = { message, content: base64EncodeUtf8(contentStr), branch };
  const resp = await fetch(`https://api.github.com/repos/${OWNER}/${REPO}/contents/${path}`, {
    method: "PUT",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      Accept: "application/vnd.github+json",
      "User-Agent": "avatar-world-web",
    },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`GitHub write failed (${resp.status}): ${text}`);
  }
  return resp.json();
}
