const TYPES = [
  ["color", "颜色"],
  ["word", "词语/概念"],
  ["story", "故事片段"],
  ["rule", "规则"],
  ["creature", "生物"],
  ["place", "地点"],
];

const FACES = ["(｡◕‿◕｡)", "(๑˃ᴗ˂)ﻭ", "( •_•)", "(≧◡≦)", "(⌐■_■)", "(°◡°)", "(ノ◕ヮ◕)ノ", "(◔_◔)"];

const TITLES = [
  [0, "游荡者"],
  [1, "初来者"],
  [3, "贡献者"],
  [6, "建造者"],
  [10, "长居者"],
  [20, "传奇"],
];

function getVisitorId() {
  let id = localStorage.getItem("avatar_world_visitor_id");
  if (!id) {
    id = "web-" + crypto.randomUUID().replace(/-/g, "").slice(0, 20);
    localStorage.setItem("avatar_world_visitor_id", id);
  }
  return id;
}

async function sha256Hex(str) {
  const bytes = new TextEncoder().encode(str);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function titleFor(count) {
  let result = TITLES[0][1];
  for (const [threshold, name] of TITLES) {
    if (count >= threshold) result = name;
  }
  return result;
}

async function faceFor(contributions) {
  if (!contributions.length) return FACES[0];
  const blob = contributions.map((x) => x.content).join("");
  const hex = await sha256Hex(blob);
  const idx = parseInt(hex.slice(0, 8), 16) % FACES.length;
  return FACES[idx];
}

async function avatarCode(contributions) {
  if (!contributions.length) return "AVT-0000";
  const blob = contributions.map((x) => `${x.type}:${x.content}`).join("|");
  const hex = await sha256Hex(blob);
  return "AVT-" + hex.slice(0, 6).toUpperCase();
}

async function buildAvatar(myContributions, worldContributions, visitorId) {
  const count = myContributions.length;
  const colors = myContributions.filter((x) => x.type === "color").map((x) => x.content);
  const creatures = myContributions.filter((x) => x.type === "creature").map((x) => x.content);
  const typesUsed = new Set(myContributions.map((x) => x.type));
  const traits = [];
  if (typesUsed.has("color")) traits.push("调色者");
  if (typesUsed.has("word")) traits.push("命名者");
  if (typesUsed.has("story")) traits.push("说书人");
  if (typesUsed.has("rule")) traits.push("立法者");
  if (typesUsed.has("creature")) traits.push("造物主");
  if (typesUsed.has("place")) traits.push("拓荒者");
  if (typesUsed.size >= 6) traits.push("全能建造者");

  const days = new Set(myContributions.map((x) => x.date));

  const firstAuthors = [];
  for (const item of worldContributions) {
    if (!firstAuthors.includes(item.author)) firstAuthors.push(item.author);
  }
  const rankIdx = firstAuthors.indexOf(visitorId);

  return {
    code: await avatarCode(myContributions),
    face: await faceFor(myContributions),
    title: titleFor(count),
    count,
    days: days.size,
    colors,
    creatures,
    traits: traits.length ? traits : ["尚未定型"],
    rank: rankIdx >= 0 ? rankIdx + 1 : null,
    worldContributors: firstAuthors.length,
    worldTotal: worldContributions.length,
  };
}

function renderCard(avatar) {
  const companion = avatar.creatures.length ? `  同伴: ${avatar.creatures[avatar.creatures.length - 1]}` : "";
  const originStr = avatar.rank ? `第 ${avatar.rank} 位加入此世界的人` : "尚未加入此世界";
  const colorsStr = avatar.colors.length ? avatar.colors.slice(-3).join("、") : "（无）";
  const traitsStr = avatar.traits.join("、");
  return [
    `${avatar.code}`,
    "",
    `      ${avatar.face}`,
    "",
    `称号: ${avatar.title}${companion}`,
    `起源: ${originStr}`,
    `色彩: ${colorsStr}`,
    `特质: ${traitsStr}`,
    `历史: 共 ${avatar.count} 次贡献 · ${avatar.days} 天`,
    "─".repeat(30),
    `世界: ${avatar.worldContributors} 位玩家 · 共 ${avatar.worldTotal} 次贡献`,
  ].join("\n");
}

function typeLabel(type) {
  const found = TYPES.find(([t]) => t === type);
  return found ? found[1] : type;
}

let selectedType = null;
let worldCache = [];

async function loadWorld() {
  const cardEl = document.getElementById("avatar-card");
  try {
    const resp = await fetch("/api/world");
    const data = await resp.json();
    worldCache = data.contributions || [];
  } catch (err) {
    cardEl.textContent = "世界状态加载失败，刷新试试。";
    return;
  }

  const visitorId = getVisitorId();
  const myContributions = worldCache.filter((x) => x.author === visitorId);
  const avatar = await buildAvatar(myContributions, worldCache, visitorId);
  cardEl.textContent = renderCard(avatar);

  const today = new Date().toISOString().slice(0, 10);
  const alreadyToday = myContributions.some((x) => x.date === today);

  document.getElementById("form-section").hidden = alreadyToday;
  document.getElementById("already-section").hidden = !alreadyToday;

  renderHistory();
}

function renderHistory() {
  const list = document.getElementById("history-list");
  list.innerHTML = "";
  if (!worldCache.length) {
    list.innerHTML = "<li>这个世界还什么都没有。</li>";
    return;
  }
  for (const item of worldCache) {
    const li = document.createElement("li");
    li.innerHTML = `${item.date} [${typeLabel(item.type)}] ${escapeHtml(item.content)} —— <span class="author">${escapeHtml(item.author)}</span>`;
    list.appendChild(li);
  }
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function buildTypeGrid() {
  const grid = document.getElementById("type-grid");
  for (const [type, label] of TYPES) {
    const btn = document.createElement("button");
    btn.className = "type-btn";
    btn.textContent = label;
    btn.dataset.type = type;
    btn.addEventListener("click", () => {
      selectedType = type;
      document.querySelectorAll(".type-btn").forEach((b) => b.classList.remove("selected"));
      btn.classList.add("selected");
    });
    grid.appendChild(btn);
  }
}

async function submitContribution() {
  const msgEl = document.getElementById("form-msg");
  const contentEl = document.getElementById("content-input");
  const btn = document.getElementById("submit-btn");
  const content = contentEl.value.trim();

  if (!selectedType) {
    msgEl.textContent = "先选一个类型。";
    msgEl.className = "msg error";
    return;
  }
  if (!content) {
    msgEl.textContent = "写点什么再提交。";
    msgEl.className = "msg error";
    return;
  }

  btn.disabled = true;
  msgEl.textContent = "正在提交...";
  msgEl.className = "msg";

  try {
    const resp = await fetch("/api/contribute", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ visitor_id: getVisitorId(), type: selectedType, content }),
    });
    const data = await resp.json();
    if (!resp.ok) {
      msgEl.textContent = data.error || "提交失败。";
      msgEl.className = "msg error";
      btn.disabled = false;
      return;
    }
    msgEl.textContent = "世界记住了你的贡献！";
    msgEl.className = "msg success";
    contentEl.value = "";
    await loadWorld();
  } catch (err) {
    msgEl.textContent = "网络错误，稍后再试。";
    msgEl.className = "msg error";
    btn.disabled = false;
  }
}

document.getElementById("submit-btn").addEventListener("click", submitContribution);
document.getElementById("toggle-history").addEventListener("click", () => {
  const list = document.getElementById("history-list");
  list.hidden = !list.hidden;
  document.getElementById("toggle-history").textContent = list.hidden ? "查看世界历史" : "收起世界历史";
});

buildTypeGrid();
loadWorld();
