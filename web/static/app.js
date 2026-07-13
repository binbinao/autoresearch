const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => [...document.querySelectorAll(sel)];

const logEl = $("#log");
let pollTimer = null;
let logSource = null;
let knownLogCount = 0;
let programLang = "zh";
let programPlatform = "gpu";
let programSnapshot = "";
let programMode = "preview";
let activePreset = null;
let runtimeEnv = null;
let envManualLock = localStorage.getItem("ar_env_manual") === "1";

const PROGRAM_FILE = {
  gpu: { en: "program.md", zh: "program_zh.md" },
  macos: { en: "program_macos.md", zh: "program_macos_zh.md" },
  cpu: { en: "program_cpu.md", zh: "program_cpu_zh.md" },
};

const PRESET_TO_PLATFORM = {
  gpu_default: "gpu",
  macos_small: "macos",
  cpu_tiny: "cpu",
};

const PLATFORM_TO_PRESET = {
  gpu: "gpu_default",
  macos: "macos_small",
  cpu: "cpu_tiny",
};

const PLATFORM_LABEL = {
  gpu: "GPU",
  macos: "macOS",
  cpu: "CPU",
};

function programFileName(platform = programPlatform, lang = programLang) {
  return (PROGRAM_FILE[platform] || PROGRAM_FILE.gpu)[lang] || PROGRAM_FILE.gpu.en;
}

function preferredProgramLang() {
  const saved = localStorage.getItem("ar_program_lang");
  if (saved === "en" || saved === "zh") return saved;
  return (navigator.language || "").toLowerCase().startsWith("zh") ? "zh" : "en";
}

function setEnvManualLock(locked) {
  envManualLock = Boolean(locked);
  if (envManualLock) localStorage.setItem("ar_env_manual", "1");
  else localStorage.removeItem("ar_env_manual");
  const autoBtn = $("#btn-env-auto");
  if (autoBtn) autoBtn.classList.toggle("active", !envManualLock && Boolean(runtimeEnv));
}

function setEnvSenseState(state, { title = "", detail = "", device = "" } = {}) {
  const panel = $("#env-sense");
  if (!panel) return;
  panel.dataset.state = state;
  panel.hidden = state === "ok" || state === "idle";
  panel.classList.toggle("is-error", state === "error");
  panel.classList.toggle("is-detecting", state === "detecting");

  const labelEl = $("#env-sense-label");
  const deviceEl = $("#env-sense-device");
  const reasonEl = $("#env-sense-reason");
  const kicker = $("#env-sense-kicker");
  if (labelEl) labelEl.textContent = title || (state === "detecting" ? "检测中…" : "");
  if (deviceEl) deviceEl.textContent = device;
  if (reasonEl) reasonEl.textContent = detail;
  if (kicker) kicker.textContent = state === "error" ? "环境检测失败" : "本机环境";
}

function updateEnvSenseUI() {
  const autoBtn = $("#btn-env-auto");
  if (autoBtn) autoBtn.classList.toggle("active", !envManualLock && Boolean(runtimeEnv));
  // Success: keep banner hidden. Errors stay visible until retry succeeds.
  if ($("#env-sense")?.dataset.state === "error") return;
  if (runtimeEnv) setEnvSenseState("ok");
}

async function applyDetectedEnvironment({ force = false, syncGuide = true } = {}) {
  if (envManualLock && !force) {
    updateEnvSenseUI();
    return null;
  }
  setEnvSenseState("detecting", {
    title: "检测中…",
    detail: "正在识别：NVIDIA GPU / macOS / CPU…",
  });
  try {
    const res = await api("/api/env/auto", { method: "POST", body: "{}" });
    runtimeEnv = res.runtime_env || res;
    const platform = runtimeEnv?.platform || res.platform;
    const preset = res.preset || runtimeEnv?.recommended_preset;
    // Only three valid outcomes — anything else is a real API bug.
    if (!platform || !["gpu", "macos", "cpu"].includes(platform)) {
      throw new Error(`环境分类异常：${platform || "空"}（应为 gpu / macos / cpu）`);
    }
    fillEnvInputs(res.overrides || {});
    setPresetButtons(preset || PLATFORM_TO_PRESET[platform]);
    if (syncGuide) {
      if (platform !== programPlatform) {
        await loadProgram(programLang, platform, { force: true });
      } else {
        programPlatform = platform;
        localStorage.setItem("ar_program_platform", programPlatform);
        setPlatformButtons(programPlatform);
      }
    }
    if (force) setEnvManualLock(false);
    setEnvSenseState("ok");
    updateEnvSenseUI();
    return { ...res, platform, preset: preset || PLATFORM_TO_PRESET[platform] };
  } catch (err) {
    setEnvSenseState("error", {
      title: "环境检测请求失败",
      detail: err?.message || String(err),
    });
    throw err;
  }
}

function setLangButtons(lang) {
  $$(".lang-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.lang === lang);
  });
  updateProgramFileLabel();
}

function setPlatformButtons(platform) {
  $$(".platform-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.platform === platform);
  });
  updateProgramFileLabel();
}

function setPresetButtons(presetName) {
  activePreset = presetName || null;
  $$("[data-preset]").forEach((btn) => {
    const on = btn.dataset.preset === activePreset;
    btn.classList.toggle("active", on);
    btn.setAttribute("aria-pressed", on ? "true" : "false");
  });
}

function updateProgramFileLabel() {
  const label = $("#program-file-label");
  if (label) label.textContent = programFileName();
}

function setProgramMode(mode) {
  programMode = mode === "edit" ? "edit" : "preview";
  const editing = programMode === "edit";
  $$(".mode-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.mode === programMode);
  });
  $("#program-preview").hidden = editing;
  $("#program-editor").hidden = !editing;
  $("#program-edit-actions").hidden = !editing;
  if (!editing) renderProgramPreview($("#program-editor").value);
}

function renderProgramPreview(markdown) {
  const preview = $("#program-preview");
  if (!preview) return;
  const parseMd =
    typeof marked !== "undefined" && typeof (marked.parse || marked) === "function"
      ? marked.parse || marked
      : null;
  if (!parseMd || typeof DOMPurify === "undefined") {
    preview.textContent = markdown || "";
    return;
  }
  const raw = parseMd(markdown || "");
  const clean = DOMPurify.sanitize(String(raw), {
    USE_PROFILES: { html: true },
  });
  const doc = new DOMParser().parseFromString(clean, "text/html");
  preview.replaceChildren(...Array.from(doc.body.childNodes));
}

async function loadProgram(lang, platform, { force = false } = {}) {
  const nextLang = lang || programLang;
  const nextPlatform = platform || programPlatform;
  const editor = $("#program-editor");
  if (!force && editor.value !== programSnapshot) {
    const ok = window.confirm("当前指引有未保存修改，切换将丢弃这些修改。继续？");
    if (!ok) return false;
  }
  const prog = await api(
    `/api/program?lang=${encodeURIComponent(nextLang)}&platform=${encodeURIComponent(nextPlatform)}`
  );
  programLang = prog.lang || nextLang;
  programPlatform = prog.platform || nextPlatform;
  editor.value = prog.content || "";
  programSnapshot = editor.value;
  localStorage.setItem("ar_program_lang", programLang);
  localStorage.setItem("ar_program_platform", programPlatform);
  setLangButtons(programLang);
  setPlatformButtons(programPlatform);
  renderProgramPreview(editor.value);
  setProgramMode("preview");
  return true;
}

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

function enhanceKnobTooltips() {
  $$("#knobs .knob-hint").forEach((el) => {
    const text = (el.textContent || "").replace(/\s+/g, " ").trim();
    if (text) el.title = text;
  });
  $$("#knobs .knob-name code").forEach((el) => {
    const text = (el.textContent || "").trim();
    if (text) el.title = text;
  });
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

function chartColors() {
  return {
    axis: "rgba(93, 107, 117, 0.55)",
    grid: "rgba(21, 32, 40, 0.06)",
    text: "#5d6b75",
    lime: "#0f7a72",
    keep: "#1f8f6a",
    discard: "#c0452e",
    line: "rgba(15, 122, 114, 0.95)",
    fill: "rgba(15, 122, 114, 0.10)",
  };
}

function fitCanvas(canvas) {
  const dpr = window.devicePixelRatio || 1;
  const cssW = Math.max(1, canvas.clientWidth || canvas.width || 320);
  const cssH = Math.max(
    280,
    canvas.clientHeight || Math.round(cssW * 0.42)
  );
  canvas.width = Math.floor(cssW * dpr);
  canvas.height = Math.floor(cssH * dpr);
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { ctx, w: cssW, h: cssH };
}

function drawEmpty(ctx, w, h, message) {
  const c = chartColors();
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = c.text;
  ctx.font = "12px IBM Plex Mono, monospace";
  ctx.fillText(message, 16, h / 2);
}

function drawAxes(ctx, pad, w, h, c) {
  ctx.strokeStyle = c.grid;
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i += 1) {
    const y = pad.t + ((h - pad.t - pad.b) * i) / 4;
    ctx.beginPath();
    ctx.moveTo(pad.l, y);
    ctx.lineTo(w - pad.r, y);
    ctx.stroke();
  }
  ctx.strokeStyle = c.axis;
  ctx.beginPath();
  ctx.moveTo(pad.l, pad.t);
  ctx.lineTo(pad.l, h - pad.b);
  ctx.lineTo(w - pad.r, h - pad.b);
  ctx.stroke();
}

function renderLossChart(series) {
  const canvas = $("#chart-loss");
  const { ctx, w, h } = fitCanvas(canvas);
  const c = chartColors();
  const points = series || [];
  if (!points.length) {
    drawEmpty(ctx, w, h, "尚无本轮 loss — 启动训练或点「演示」");
    $("#progress-fill").style.width = "0%";
    $("#live-progress-label").textContent = "等待 step / loss 日志…";
    return;
  }

  const pad = { t: 18, r: 18, b: 34, l: 52 };
  const xs = points.map((p) => p.step);
  const ys = points.map((p) => p.loss);
  const minX = xs[0];
  const maxX = xs[xs.length - 1] === minX ? minX + 1 : xs[xs.length - 1];
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const spanY = maxY - minY || 1;
  const y0 = minY - spanY * 0.08;
  const y1 = maxY + spanY * 0.08;

  const xMap = (x) => pad.l + ((x - minX) / (maxX - minX)) * (w - pad.l - pad.r);
  const yMap = (y) => pad.t + (1 - (y - y0) / (y1 - y0)) * (h - pad.t - pad.b);

  ctx.clearRect(0, 0, w, h);
  drawAxes(ctx, pad, w, h, c);

  ctx.beginPath();
  points.forEach((p, i) => {
    const x = xMap(p.step);
    const y = yMap(p.loss);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.strokeStyle = c.line;
  ctx.lineWidth = 2;
  ctx.stroke();

  // area fill
  ctx.lineTo(xMap(points[points.length - 1].step), h - pad.b);
  ctx.lineTo(xMap(points[0].step), h - pad.b);
  ctx.closePath();
  ctx.fillStyle = c.fill;
  ctx.fill();

  ctx.fillStyle = c.text;
  ctx.font = "11px IBM Plex Mono, monospace";
  ctx.fillText(y1.toFixed(3), 8, pad.t + 4);
  ctx.fillText(y0.toFixed(3), 8, h - pad.b);
  ctx.fillText(`step ${minX}`, pad.l, h - 10);
  ctx.fillText(`step ${maxX}`, w - pad.r - 64, h - 10);

  const latest = points[points.length - 1];
  const pct = Math.max(0, Math.min(100, Number(latest.pct) || 0));
  $("#progress-fill").style.width = `${pct}%`;
  const tok = latest.tok_per_sec != null ? ` · ${latest.tok_per_sec.toLocaleString()} tok/s` : "";
  $("#live-progress-label").textContent =
    `step ${latest.step} · ${pct.toFixed(1)}% · loss ${Number(latest.loss).toFixed(4)}${tok}`;
}

function renderHistoryChart(rows) {
  const canvas = $("#chart-history");
  const { ctx, w, h } = fitCanvas(canvas);
  const c = chartColors();
  const parsed = (rows || [])
    .map((row, idx) => {
      const val = Number(row.val_bpb);
      if (!Number.isFinite(val) || val <= 0) return null;
      return { i: idx, val, status: row.status || "", desc: row.description || "" };
    })
    .filter(Boolean);

  if (!parsed.length) {
    drawEmpty(ctx, w, h, "尚无历史 val_bpb — 完成几轮实验后这里会画出趋势");
    return;
  }

  const pad = { t: 18, r: 18, b: 34, l: 52 };
  const minX = 0;
  const maxX = Math.max(parsed.length - 1, 1);
  const vals = parsed.map((p) => p.val);
  const minY = Math.min(...vals);
  const maxY = Math.max(...vals);
  const spanY = maxY - minY || 1;
  const y0 = minY - spanY * 0.12;
  const y1 = maxY + spanY * 0.12;
  const xMap = (i) => pad.l + (i / maxX) * (w - pad.l - pad.r);
  const yMap = (y) => pad.t + (1 - (y - y0) / (y1 - y0)) * (h - pad.t - pad.b);

  ctx.clearRect(0, 0, w, h);
  drawAxes(ctx, pad, w, h, c);

  // best line
  let best = Infinity;
  const bestPts = parsed.map((p) => {
    best = Math.min(best, p.val);
    return best;
  });
  ctx.beginPath();
  bestPts.forEach((v, i) => {
    const x = xMap(i);
    const y = yMap(v);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.setLineDash([5, 4]);
  ctx.strokeStyle = "rgba(31, 143, 106, 0.65)";
  ctx.lineWidth = 1.5;
  ctx.stroke();
  ctx.setLineDash([]);

  ctx.beginPath();
  parsed.forEach((p, i) => {
    const x = xMap(i);
    const y = yMap(p.val);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.strokeStyle = "rgba(21, 32, 40, 0.35)";
  ctx.lineWidth = 1.5;
  ctx.stroke();

  parsed.forEach((p, i) => {
    const x = xMap(i);
    const y = yMap(p.val);
    const keep = p.status === "keep";
    ctx.beginPath();
    ctx.arc(x, y, keep ? 4.5 : 3.5, 0, Math.PI * 2);
    if (keep) {
      ctx.fillStyle = c.keep;
      ctx.fill();
    } else {
      ctx.strokeStyle = p.status === "crash" ? c.discard : "rgba(192, 69, 46, 0.75)";
      ctx.lineWidth = 1.5;
      ctx.stroke();
    }
  });

  ctx.fillStyle = c.text;
  ctx.font = "11px IBM Plex Mono, monospace";
  ctx.fillText(y1.toFixed(4), 6, pad.t + 4);
  ctx.fillText(y0.toFixed(4), 6, h - pad.b);
  ctx.fillText("exp #1", pad.l, h - 10);
  ctx.fillText(`#${parsed.length}`, w - pad.r - 28, h - 10);
  ctx.fillText(`best ${best.toFixed(4)}`, w - pad.r - 110, pad.t + 4);
}

function renderCharts(status) {
  renderLossChart(status.progress_series || []);
  renderHistoryChart(status.history || []);
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
  if (s.runtime_env) {
    runtimeEnv = s.runtime_env;
    if ($("#env-sense")?.dataset.state !== "error") {
      setEnvSenseState("ok");
    }
    updateEnvSenseUI();
  }
  if (s.active_preset) setPresetButtons(s.active_preset);
  else if (!activePreset && s.detected_platform) {
    setPresetButtons(PLATFORM_TO_PRESET[s.detected_platform]);
  }
  setLoopState(s.state);
  renderCheckpoints(s.checkpoints || []);
  renderResults(s.history || []);
  fillEnvInputs(s.env_overrides || {});
  renderMetrics(s.last_result);
  renderCharts(s);

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

$("#btn-refresh").addEventListener("click", async () => {
  try {
    await refresh();
    toast("状态已刷新");
  } catch (e) {
    toast(e.message);
  }
});

$("#btn-env-setup").addEventListener("click", async () => {
  try {
    knownLogCount = 0;
    logEl.textContent = "";
    const res = await api("/api/env-setup", { method: "POST", body: "{}" });
    startLogStream();
    fillEnvInputs(
      (await api("/api/status")).env_overrides || {}
    );
    if (res.platform) {
      setPresetButtons(res.preset || PLATFORM_TO_PRESET[res.platform]);
      if (res.platform !== programPlatform) {
        await loadProgram(programLang, res.platform, { force: true });
      }
    }
    toast(`开始环境准备（${res.label || res.platform || "本机"}）…`);
    await refresh();
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
    const res = await api("/api/program", {
      method: "PUT",
      body: JSON.stringify({
        content: $("#program-editor").value,
        lang: programLang,
        platform: programPlatform,
      }),
    });
    programSnapshot = $("#program-editor").value;
    renderProgramPreview(programSnapshot);
    setProgramMode("preview");
    toast(`${res.path || programFileName()} 已保存`);
  } catch (e) {
    toast(e.message);
  }
});

$("#btn-cancel-edit").addEventListener("click", () => {
  $("#program-editor").value = programSnapshot;
  setProgramMode("preview");
});

$$(".mode-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    const mode = btn.dataset.mode;
    if (!mode || mode === programMode) return;
    if (mode === "preview" && $("#program-editor").value !== programSnapshot) {
      const ok = window.confirm("放弃未保存的编辑并返回预览？");
      if (!ok) return;
      $("#program-editor").value = programSnapshot;
    }
    setProgramMode(mode);
  });
});

$$(".lang-btn").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const next = btn.dataset.lang;
    if (!next || next === programLang) return;
    try {
      const ok = await loadProgram(next, programPlatform);
      if (!ok) setLangButtons(programLang);
      else toast(next === "zh" ? "已切换到中文指引" : "Switched to English guidance");
    } catch (e) {
      setLangButtons(programLang);
      toast(e.message);
    }
  });
});

$$(".platform-btn").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const next = btn.dataset.platform;
    if (!next || next === programPlatform) return;
    try {
      const ok = await loadProgram(programLang, next);
      if (!ok) {
        setPlatformButtons(programPlatform);
        return;
      }
      setEnvManualLock(true);
      const preset = PLATFORM_TO_PRESET[next];
      if (preset) {
        const res = await api("/api/preset", {
          method: "POST",
          body: JSON.stringify({ name: preset }),
        });
        fillEnvInputs(res.overrides || {});
        setPresetButtons(preset);
      }
      toast(`已手动切换到 ${PLATFORM_LABEL[next] || next} 指引与预设`);
    } catch (e) {
      setPlatformButtons(programPlatform);
      toast(e.message);
    }
  });
});

$$("[data-preset]").forEach((btn) => {
  btn.addEventListener("click", async () => {
    try {
      const res = await api("/api/preset", {
        method: "POST",
        body: JSON.stringify({ name: btn.dataset.preset }),
      });
      fillEnvInputs(res.overrides || {});
      setEnvManualLock(true);
      setPresetButtons(btn.dataset.preset);
      const nextPlatform = res.platform || PRESET_TO_PLATFORM[btn.dataset.preset];
      if (nextPlatform && nextPlatform !== programPlatform) {
        const ok = await loadProgram(programLang, nextPlatform);
        if (ok) toast(`已手动应用 ${PLATFORM_LABEL[nextPlatform]} 预设与指引`);
        else toast(`已应用预设 ${btn.dataset.preset}（指引未切换）`);
      } else {
        toast(`已应用预设 ${btn.dataset.preset}`);
      }
      updateEnvSenseUI();
    } catch (e) {
      toast(e.message);
    }
  });
});

$("#btn-env-auto")?.addEventListener("click", async () => {
  try {
    await applyDetectedEnvironment({ force: true, syncGuide: true });
    toast(`已按本机自动选择 ${runtimeEnv?.label || ""} 环境`);
    await refresh();
  } catch (e) {
    toast(`环境检测失败：${e.message}`);
  }
});

$("#btn-env-retry")?.addEventListener("click", async () => {
  try {
    setEnvManualLock(false);
    await applyDetectedEnvironment({ force: true, syncGuide: true });
    toast(`已自动选择 ${runtimeEnv?.label || ""} 环境`);
    await refresh();
  } catch (e) {
    toast(`环境检测失败：${e.message}`);
  }
});

$("#btn-apply-env").addEventListener("click", async () => {
  try {
    await api("/api/env", {
      method: "POST",
      body: JSON.stringify({ overrides: collectEnv() }),
    });
    setEnvManualLock(true);
    setPresetButtons(null);
    toast("参数已应用（已切换为手动）");
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
  enhanceKnobTooltips();
  setEnvSenseState("detecting", {
    title: "检测中…",
    detail: "正在识别 CUDA / MPS / CPU…",
  });
  try {
    programLang = preferredProgramLang();
    setLangButtons(programLang);
    const status = await api("/api/status");
    runtimeEnv = status.runtime_env || null;
    const detected = status.detected_platform || runtimeEnv?.platform || null;

    if (!runtimeEnv && !detected) {
      throw new Error("后端未返回本机环境信息，请确认服务已重启");
    }

    if (envManualLock) {
      const saved = localStorage.getItem("ar_program_platform");
      programPlatform =
        saved === "gpu" || saved === "macos" || saved === "cpu"
          ? saved
          : detected || "gpu";
      setPlatformButtons(programPlatform);
      await loadProgram(programLang, programPlatform, { force: true });
      setPresetButtons(status.active_preset || PLATFORM_TO_PRESET[programPlatform]);
      setEnvSenseState("ok");
      updateEnvSenseUI();
    } else {
      try {
        await applyDetectedEnvironment({ force: true, syncGuide: true });
        toast(`已自动选择 ${runtimeEnv?.label || PLATFORM_LABEL[detected]} 试验环境`);
      } catch (envErr) {
        toast(`环境检测失败：${envErr.message}`);
        // Fall back to loading a guide so the UI remains usable
        programPlatform = detected || "cpu";
        setPlatformButtons(programPlatform);
        await loadProgram(programLang, programPlatform, { force: true });
      }
    }

    await refresh();
    pollTimer = setInterval(() => {
      if (["running", "preparing", "deciding"].includes(window.__state)) refresh().catch(() => {});
    }, 1200);
    window.addEventListener("resize", () => {
      refresh().catch(() => {});
    });
  } catch (e) {
    setEnvSenseState("error", {
      title: "未检测出可用环境",
      detail: e.message || String(e),
    });
    toast(`环境检测失败：${e.message}`);
  }
}

boot();
