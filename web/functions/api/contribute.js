import { fetchWorldAuthoritative, computeHash, createFile, jsonResponse, sha256Hex } from "../_lib/github.js";

const TYPES = new Set(["color", "word", "story", "rule", "creature", "place"]);
const MAX_LEN = 200;
const IP_SALT = "avatar-world-anti-spam-v1";

export async function onRequestPost(context) {
  const { request, env } = context;

  let body;
  try {
    body = await request.json();
  } catch (_) {
    return jsonResponse({ error: "请求体不是合法 JSON" }, 400);
  }

  const visitorId = String(body.visitor_id || "").trim();
  const type = String(body.type || "").trim();
  const content = String(body.content || "").trim();

  if (!visitorId || visitorId.length < 8 || visitorId.length > 64) {
    return jsonResponse({ error: "visitor_id 不合法" }, 400);
  }
  if (!TYPES.has(type)) {
    return jsonResponse({ error: "type 不合法" }, 400);
  }
  if (!content) {
    return jsonResponse({ error: "内容不能为空" }, 400);
  }
  if (content.length > MAX_LEN) {
    return jsonResponse({ error: `内容太长，最多 ${MAX_LEN} 字` }, 400);
  }
  if (!env.GITHUB_TOKEN) {
    return jsonResponse({ error: "服务器没配置 GITHUB_TOKEN" }, 500);
  }

  const ip = request.headers.get("CF-Connecting-IP") || "unknown";
  const ipHash = (await sha256Hex(IP_SALT + ip)).slice(0, 16);

  const world = await fetchWorldAuthoritative(env.GITHUB_TOKEN);
  const today = new Date().toISOString().slice(0, 10);

  if (world.some((x) => x.author === visitorId && x.date === today)) {
    return jsonResponse({ error: "今天已经贡献过了，明天再来", world }, 409);
  }
  // 轻量防刷：同一个 IP 今天已经贡献过（哪怕换了 visitor_id）也拒绝。
  // 不是强安全边界，只是防止清一下 localStorage 就能刷无限次。
  if (world.some((x) => x.ip_hash === ipHash && x.date === today)) {
    return jsonResponse({ error: "这个网络今天已经贡献过了，明天再来", world }, 409);
  }

  const lastHash = world.length ? world[world.length - 1].hash : null;
  const entry = {
    type,
    content,
    author: visitorId,
    date: today,
    timestamp: new Date().toISOString().slice(0, 19),
    prev_hash: lastHash,
    ip_hash: ipHash,
  };
  entry.hash = await computeHash(entry);

  const filename = `${entry.date}-${entry.author}-${entry.hash.slice(0, 8)}.json`;
  const path = `contributions/${filename}`;

  await createFile(
    path,
    JSON.stringify(entry, null, 2),
    `contribute(${type}) via web by ${visitorId.slice(0, 8)}`,
    env.GITHUB_TOKEN
  );

  const newWorld = [...world, entry];
  return jsonResponse({ ok: true, entry, world: newWorld });
}

export async function onRequestOptions() {
  return new Response(null, {
    headers: {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
    },
  });
}
