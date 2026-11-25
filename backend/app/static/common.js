
async function getJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(url + " " + r.status);
  return r.json();
}
async function postJSON(url, body) {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? "{}" : JSON.stringify(body),
  });
  const t = await r.text();
  let data;
  try { data = JSON.parse(t); } catch { data = { 原文: t }; }
  if (!r.ok) throw new Error((data && (data.错误 || data.detail)) || t || String(r.status));
  return data;
}
function 行(html) {
  const tr = document.createElement("tr");
  tr.innerHTML = html;
  return tr;
}
function 徽章(文, 类) {
  const tone = 类 || 命运色(文);
  return `<span class="徽章 ${tone || ""}">${安全文本(文)}</span>`;
}
function 空态(文) { return `<p class="说明">${安全文本(文)}</p>`; }
function 安全文本(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[c]);
}
const 分流词 = {
  "本指标门槛": "本指标·过门槛",
  "本指标越界": "本指标·越界坏点",
  "错指标门槛": "错指标·仅影子归档",
  "无门槛-放行": "无门槛·显式放行",
  "过门槛-影子草稿": "影子草稿·不计正式",
};
function 分流中文(v) {
  if (!v) return "—";
  return 分流词[v] || v;
}
function 命运色(f) {
  if (["已入栏", "在栏", "已汇总", "对齐"].includes(f)) return "ok";
  if (["已坏点", "撕裂"].includes(f)) return "warn";
  return "";
}
function 渲染水位(el, o) {
  if (!el) return;
  el.innerHTML = "";
  for (const [标, 键] of [["观测报文","观测报文"],["在栏","在栏"],["站点汇总","站点汇总"],["坏点","坏点"],["影子归档","影子归档"]]) {
    const d = document.createElement("div");
    d.className = "水卡";
    d.innerHTML = `<div class="数">${o[键] ?? 0}</div><div class="标">${标}</div>`;
    el.appendChild(d);
  }
}
function 渲染门槛(el, 规) {
  if (!el) return;
  const r = 规 || {};
  const 门 = [];
  for (const [k, v] of Object.entries(r)) {
    if (!k.startsWith("门槛:")) continue;
    const 段 = k.split(":");
    if (段.length !== 3) continue;
    let 卡 = 门.find((x) => x.指标 === 段[1]);
    if (!卡) { 卡 = { 指标: 段[1], 下限: "—", 上限: "—" }; 门.push(卡); }
    if (段[2] === "下限") 卡.下限 = v; else if (段[2] === "上限") 卡.上限 = v;
  }
  if (!门.length) {
    门.push({ 指标: "PM25", 下限: r["PM25下限"] || "—", 上限: r["PM25上限"] || "—" });
  }
  const 门卡 = 门.map((x) =>
    `<div class="门槛卡"><div class="k">${安全文本(x.指标)} 门槛</div>` +
    `<div class="v">${安全文本(x.下限)} ~ ${安全文本(x.上限)}</div>` +
    `<div class="k">本指标·同票裁决</div></div>`
  ).join("");
  el.innerHTML = `
    <div class="门槛卡"><div class="k">当前栏</div><div class="v">${安全文本(r["当前栏号"] || "—")}</div></div>
    <div class="门槛卡"><div class="k">账册版本</div><div class="v">${安全文本(r["账册版本"] || "1")}</div></div>
    ${门卡}
  `;
}
function 渲染门槛表(el, 门) {
  if (!el || !门) return;
  const rows = Object.entries(门).map(([k, v]) =>
    `<tr><td>${安全文本(k)}</td><td>${安全文本(v.下限)}</td><td>${安全文本(v.上限)}</td>` +
    `<td><code>${安全文本(v.指纹 || "—")}</code></td><td>${v.受控 === false ? "无门槛·显式放行" : "本指标·同票裁决"}</td></tr>`
  ).join("");
  el.innerHTML = rows || `<tr><td colspan="5">${空态("尚无分指标门槛。")}</td></tr>`;
}
function 渲染批次表(el, rows, cols) {
  if (!el) return;
  if (!rows || !rows.length) {
    el.innerHTML = `<tr><td colspan="${cols.length}">${空态("尚无批次。")}</td></tr>`;
    return;
  }
  el.innerHTML = "";
  for (const r of rows) {
    const cells = cols.map((c) => `<td>${安全文本(r[c])}</td>`).join("");
    el.appendChild(行(cells));
  }
}
function 装载摘要文(r) {
  if (!r) return "";
  return `入流 ${r["入流"]||0} · 入栏 ${r["入栏"]||0} · 坏点 ${r["坏点"]||0} · 驳回 ${r["驳回"]||0}`;
}
function 结栏摘要文(r) {
  if (!r) return "";
  return `栏 ${r["栏号"]||"?"} · 汇总 ${r["汇总数"]||0} · 缓冲消耗 ${r["缓冲消耗"]||0}`;
}
function 贯验摘要文(r) {
  if (!r) return "";
  return `${r["是否对齐"]?"对齐":"撕裂"} · 在栏 ${r["在栏"]} · 汇总报文 ${r["汇总报文"]} · 坏点 ${r["坏点"]}`;
}
function 填命运字典(el, dict) {
  if (!el || !dict) return;
  el.innerHTML = Object.entries(dict).map(([k, v]) =>
    `<div class="只读框 上距8"><b class="铜字">${安全文本(k)}</b> · ${安全文本(v)}</div>`
  ).join("");
}
window.探栏 = {
  getJSON, postJSON, 行, 徽章, 空态, 安全文本, 命运色, 分流中文,
  渲染水位, 渲染门槛, 渲染门槛表, 渲染批次表,
  装载摘要文, 结栏摘要文, 贯验摘要文, 填命运字典,
};
