const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => [...document.querySelectorAll(sel)];

const logEl = $("#log");
let pollTimer = null;
let logSource = null;
let knownLogCount = 0;

function toast(msg) {
  const el = $("#toast");
  el.hidden = false;
  el.textContent = msg;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => {
    el.hidden = true;
  }, 3200);
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data.detail || res.statusText;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data;
}

function setLoopState(state) {
  $$("#loop-states li").forEach((li) => {
    li.classList.toggle("active", li.dataset.state === state);
  });
}

function renderCheckpoints(list) {
  const ul = $("#checkpoint-list");
  ul.textContent = "";
  (list || [])
    .slice()
    .reverse()
    .forEach((c) => {
      const li = document.createElement("li");
      li.textContent = `${c.at} — ${c.message}`;
      ul.appendChild(li);
    });
}

function renderResults(rows) {
  const body = $("#results-body");
  body.textContent = "";
  (rows || [])
    .slice()
    .reverse()
    .forEach((row) => {
      const tr = document.createElement("tr");
      ["commit", "val_bpb", "memory_gb", "status", "description"].forEach((key) => {
        const td = document.createElement("td");
        td.textContent = row[key] || "";
        tr.appendChild(td);
      });
      body.appendChild(tr);
    });
}

function fillEnvInputs(overrides) {
  $$("#knobs input[data-env]").forEach((input) => {
    const key = input.dataset.env;
    input.value = overrides && key in overrides ? overrides[key] : "";
  });
}

function collectEnv() {
  const overrides = {};
  $$("#knobs input[data-env]").forEach((input) => {
    const v = input.value.trim();
    if (v) overrides[input.dataset.env] = v;
  });
  return overrides;
}

function renderMetrics(last) {
  const box = $("#last-metrics");
  const decide = $("#decide-row");
  if (!last) {
    box.hidden = true;
    return;
  }
  box.hidden = false;
  $("#m-bpb").textContent = last.val_bpb != null ? Number(last.val_bpb).toFixed(6) : "—";
  $("#m-vram").textContent = last.peak_vram_mb != null ? Number(last.peak_vram_mb).toFixed(1) : "—";
  $("#m-steps").textContent = last.num_steps != null ? last.num_steps : "—";
  $("#m-device").textContent = last.device || "—";
  decide.hidden = !["deciding", "error"].includes(window.__state);
}

function appendLogLines(lines) {
  if (!lines || !lines.length) return;
  const atBottom = logEl.scrollTop + logEl.clientHeight >= logEl.scrollHeight - 24;
  const chunk = lines.join("\n");
  logEl.textContent = (logEl.textContent ? `${logEl.textContent}\n` : "") + chunk;
  if (atBottom) logEl.scrollTop = logEl.scrollHeight;
}

async function refresh() {
  const s = await api("/api/status");
  window.__state = s.state;
  $("#st-state").textContent = s.state;
  $("#st-branch").textContent = s.branch || "—";
  $("#st-device").textContent = s.device || "—";
  $("#st-data").textContent = s.data_ready ? "就绪" : "未准备";
  $("#st-message").textContent = s.message || "";
  $("#best-bpb").textContent = s.best_val_bpb != null ? Number(s.best_val_bpb).toFixed(6) : "—";
  setLoopState(s.state);
  renderCheckpoints(s.checkpoints || []);
  renderResults(s.history || []);
  fillEnvInputs(s.env_overrides || {});
  renderMetrics(s.last_result);

  if ((s.log_lines || []).length > knownLogCount) {
    appendLogLines(s.log_lines.slice(knownLogCount));
    knownLogCount = s.log_lines.length;
  }
  return s;
}

function startLogStream() {
  if (logSource) logSource.close();
  logSource = new EventSource(`/api/log/stream?from_index=${knownLogCount}`);
  logSource.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.type === "line") {
      appendLogLines([msg.text]);
      knownLogCount += 1;
    }
    if (msg.type === "done") {
      logSource.close();
      logSource = null;
      refresh();
    }
  };
}

function todayTag() {
  const d = new Date();
  const m = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"][d.getMonth()];
  return `${m}${d.getDate()}`;
}

$("#run-tag").value = todayTag();

$("#btn-scroll-setup").addEventListener("click", () => {
  $("#setup").scrollIntoView({ behavior: "smooth" });
});

$("#btn-refresh").addEventListener("click", async () => {
  try {
    await refresh();
    toast("状态已刷新");
  } catch (e) {
    toast(e.message);
  }
});

$("#btn-branch").addEventListener("click", async () => {
  try {
    const tag = $("#run-tag").value.trim();
    const res = await api("/api/branch", { method: "POST", body: JSON.stringify({ tag }) });
    toast(`分支：${res.branch}`);
    await refresh();
  } catch (e) {
    toast(e.message);
  }
});

$("#btn-prepare").addEventListener("click", async () => {
  try {
    knownLogCount = 0;
    logEl.textContent = "";
    await api("/api/prepare", { method: "POST", body: "{}" });
    startLogStream();
    toast("开始 prepare…");
    await refresh();
  } catch (e) {
    toast(e.message);
  }
});

$("#btn-save-program").addEventListener("click", async () => {
  try {
    await api("/api/program", {
      method: "PUT",
      body: JSON.stringify({ content: $("#program-editor").value }),
    });
    toast("program.md 已保存");
  } catch (e) {
    toast(e.message);
  }
});

$$("[data-preset]").forEach((btn) => {
  btn.addEventListener("click", async () => {
    try {
      const res = await api("/api/preset", {
        method: "POST",
        body: JSON.stringify({ name: btn.dataset.preset }),
      });
      fillEnvInputs(res.overrides || {});
      toast(`已应用预设 ${btn.dataset.preset}`);
    } catch (e) {
      toast(e.message);
    }
  });
});

$("#btn-apply-env").addEventListener("click", async () => {
  try {
    await api("/api/env", {
      method: "POST",
      body: JSON.stringify({ overrides: collectEnv() }),
    });
    toast("旋钮已应用");
  } catch (e) {
    toast(e.message);
  }
});

$("#btn-run").addEventListener("click", async () => {
  try {
    await api("/api/env", {
      method: "POST",
      body: JSON.stringify({ overrides: collectEnv() }),
    });
    knownLogCount = 0;
    logEl.textContent = "";
    await api("/api/run", {
      method: "POST",
      body: JSON.stringify({ description: $("#run-desc").value || "experiment" }),
    });
    startLogStream();
    toast("训练已启动");
    await refresh();
  } catch (e) {
    toast(e.message);
  }
});

$("#btn-demo").addEventListener("click", async () => {
  try {
    knownLogCount = 0;
    logEl.textContent = "";
    await api("/api/demo", {
      method: "POST",
      body: JSON.stringify({ description: $("#run-desc").value || "demo walkthrough" }),
    });
    toast("演示结果已生成，请练习保留/丢弃");
    await refresh();
  } catch (e) {
    toast(e.message);
  }
});

$("#btn-stop").addEventListener("click", async () => {
  try {
    await api("/api/stop", { method: "POST", body: "{}" });
    toast("已请求停止");
    await refresh();
  } catch (e) {
    toast(e.message);
  }
});

async function decide(action) {
  try {
    const res = await api("/api/decide", {
      method: "POST",
      body: JSON.stringify({ action }),
    });
    toast(res.message || action);
    await refresh();
  } catch (e) {
    toast(e.message);
  }
}

$("#btn-keep").addEventListener("click", () => decide("keep"));
$("#btn-discard").addEventListener("click", () => decide("discard"));
$("#btn-crash").addEventListener("click", () => decide("crash"));

async function boot() {
  try {
    const prog = await api("/api/program");
    $("#program-editor").value = prog.content || "";
    await refresh();
    pollTimer = setInterval(() => {
      if (["running", "preparing"].includes(window.__state)) refresh().catch(() => {});
    }, 2500);
  } catch (e) {
    toast(`无法连接后端：${e.message}`);
  }
}

boot();
