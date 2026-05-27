const state = {
  config: null,
  currentRun: null,
  currentTab: "teaching_plan",
  health: null,
  busy: false,
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

document.addEventListener("DOMContentLoaded", () => {
  $$(".nav-item").forEach((button) => button.addEventListener("click", () => switchPanel(button.dataset.panel)));
  $$(".tab").forEach((button) => button.addEventListener("click", () => switchTab(button.dataset.tab)));
  $("#generate-form").addEventListener("submit", generateRun);
  $("#example-button").addEventListener("click", loadExample);
  $("#config-form").addEventListener("submit", saveConfig);
  $("#test-config-button").addEventListener("click", testConfig);
  $("#render-button").addEventListener("click", renderCurrentRun);
  $("#copy-run-dir-button").addEventListener("click", copyRunDir);
  $("#refresh-runs-button").addEventListener("click", loadRuns);
  $("#refresh-health-button").addEventListener("click", loadRenderHealth);
  $("#provider-id").addEventListener("change", applyPresetSelection);
  $("#use-ai").addEventListener("change", updateGenerationMode);
  $("#settings-button").addEventListener("click", openSettings);
  $("#settings-close").addEventListener("click", closeSettings);
  $("#settings-overlay").addEventListener("click", (e) => { if (e.target === $("#settings-overlay")) closeSettings(); });
  $$(".settings-tab").forEach((btn) => btn.addEventListener("click", () => switchSettingsTab(btn.dataset.settingsTab)));

  loadConfig();
  loadRenderHealth();
  loadRuns();
  updateGenerationMode();

  $$(".stage-card.clickable").forEach((card) => card.addEventListener("click", () => handleStageClick(card)));
});

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) {
    const message = payload?.detail?.message || payload?.message || `HTTP ${response.status}`;
    throw new Error(message);
  }
  return payload;
}

async function loadConfig() {
  try {
    state.config = await api("/api/config");
    renderConfig();
  } catch (error) {
    setNotice(`配置读取失败：${error.message}`, "error");
  }
}

function renderConfig() {
  const providerSelect = $("#provider-id");
  providerSelect.innerHTML = "";
  for (const preset of state.config.presets) {
    const option = document.createElement("option");
    option.value = preset.id;
    option.textContent = preset.name;
    providerSelect.appendChild(option);
  }

  const current = state.config.current;
  providerSelect.value = current.provider_id;
  $("#base-url").value = current.base_url || "";
  $("#model").value = current.model || "";
  $("#api-key").value = "";
  $("#api-key").placeholder = current.has_api_key ? `已保存 ${current.api_key_mask}` : "输入 API Key";
  $("#current-provider").textContent = current.provider_name || current.provider_id || "未配置";
  $("#current-model").textContent = current.model || "-";
  $("#key-status").textContent = current.has_api_key ? `API Key ${current.api_key_mask}` : "API Key 未配置";
  $("#key-status").className = `status-pill ${current.has_api_key ? "ok" : "muted"}`;
  $("#config-status").textContent = current.has_api_key ? "已保存" : "待配置";
  $("#config-status").className = `status-pill ${current.has_api_key ? "ok" : "warn"}`;
}

function applyPresetSelection() {
  const preset = state.config.presets.find((item) => item.id === $("#provider-id").value);
  if (!preset) return;
  $("#base-url").value = preset.base_url;
  $("#model").value = preset.default_model;
}

async function saveConfig(event) {
  event.preventDefault();
  try {
    state.config = await api("/api/config", {
      method: "POST",
      body: JSON.stringify(readConfigForm()),
    });
    renderConfig();
    setNotice("模型配置已保存。", "ok");
  } catch (error) {
    setNotice(`保存失败：${error.message}`, "error");
  }
}

async function testConfig() {
  $("#test-config-button").disabled = true;
  try {
    const result = await api("/api/config/test", {
      method: "POST",
      body: JSON.stringify(readConfigForm()),
    });
    await loadConfig();
    setNotice(result.message || "连接测试完成。", result.status === "ok" ? "ok" : "warn");
  } catch (error) {
    setNotice(`测试失败：${error.message}`, "error");
  } finally {
    $("#test-config-button").disabled = false;
  }
}

function readConfigForm() {
  return {
    provider_id: $("#provider-id").value,
    base_url: $("#base-url").value.trim(),
    model: $("#model").value.trim(),
    api_key: $("#api-key").value.trim(),
  };
}

async function loadRenderHealth() {
  try {
    state.health = await api("/api/health/render");
    renderHealth();
  } catch (error) {
    setNotice(`依赖检查失败：${error.message}`, "error");
  }
}

function renderHealth() {
  const summary = $("#health-summary");
  const grid = $("#health-grid");
  summary.innerHTML = "";
  grid.innerHTML = "";

  for (const [name, tool] of Object.entries(state.health.tools)) {
    const line = document.createElement("div");
    line.className = "health-line";
    const label = tool.available ? "可用" : (tool.required ? "缺失" : "可选·未安装");
    const hint = (!tool.available && !tool.required) ? " — 公式自动用纯文本渲染" : "";
    const statusClass = tool.available ? "ok" : (tool.required ? "warn" : "info");
    line.innerHTML = `<span>${name}</span><strong class="${statusClass}">${label}${hint}</strong>`;
    summary.appendChild(line);

    const card = document.createElement("article");
    card.className = "tool-card";
    const pillClass = tool.available ? "ok" : (tool.required ? "warn" : "info");
    card.innerHTML = `
      <div class="tool-title">
        <strong>${name}</strong>
        <span>${tool.path || tool.help}</span>
      </div>
      <span class="status-pill ${pillClass}">${label}</span>
    `;
    grid.appendChild(card);
  }
  updateRenderButton();
}

async function generateRun(event) {
  event.preventDefault();
  state.busy = true;
  const useAi = $("#use-ai").checked;
  $("#generate-button").disabled = true;
  setStageState("生成中", "生成中", "生成中", "待渲染");
  setNotice(useAi ? "正在调用模型深度生成动画方案。" : "正在使用本地快速模式生成动画方案。", "muted");

  const startTime = Date.now();
  const stageCards = $$(".stage-card");
  stageCards.forEach((card) => card.classList.add("generating"));
  const timer = setInterval(() => {
    const elapsed = Math.floor((Date.now() - startTime) / 1000);
    setNotice(`${useAi ? "模型深度生成" : "本地快速生成"}进行中 (${elapsed}s)...`, "muted");
  }, 1000);

  try {
    const run = await api("/api/generate", {
      method: "POST",
      body: JSON.stringify({
        prompt: $("#prompt").value.trim(),
        audience_level: $("#audience-level").value,
        desired_duration: Number($("#desired-duration").value),
        style: $("#style").value,
        deterministic: !useAi,
        use_ai: useAi,
      }),
    });
    clearInterval(timer);
    stageCards.forEach((card) => card.classList.remove("generating"));
    renderRun(run);
    await loadRuns();
    const elapsed = Math.floor((Date.now() - startTime) / 1000);
    if (run.notice) {
      setNotice(run.notice.message, run.notice.level || "warn");
    } else {
      setNotice(`请前往渲染动画 (${elapsed}s)。`, "ok");
    }
  } catch (error) {
    clearInterval(timer);
    stageCards.forEach((card) => card.classList.remove("generating"));
    setStageState("失败", "未完成", "未完成", "未完成");
    setNotice(`生成失败：${error.message}`, "error");
  } finally {
    state.busy = false;
    $("#generate-button").disabled = false;
  }
}

function updateGenerationMode() {
  const useAi = $("#use-ai")?.checked;
  const chip = $(".mode-chip");
  if (chip) {
    chip.textContent = useAi ? "AI 深度生成" : "本地快速生成";
  }
}

async function renderCurrentRun() {
  if (!state.currentRun) return;
  const targetRunId = state.currentRun.run_id;
  state.busy = true;
  $("#render-button").disabled = true;
  $("#render-state").textContent = "渲染中";
  $("#render-state").className = "status-pill warn";
  setNotice("Manim 正在渲染低清预览。", "warn");

  const startTime = Date.now();
  const timer = setInterval(() => {
    const elapsed = Math.floor((Date.now() - startTime) / 1000);
    setNotice(`Manim 正在渲染低清预览 (${elapsed}s)...`, "warn");
  }, 1000);

  try {
    const run = await api(`/api/runs/${encodeURIComponent(targetRunId)}/render`, { method: "POST" });
    clearInterval(timer);
    // Only update UI if we're still looking at the same run
    if (state.currentRun?.run_id !== targetRunId) return;
    renderRun(run);
    await loadRuns();
    if (run.video_url) {
      const elapsed = Math.floor((Date.now() - startTime) / 1000);
      setNotice(`渲染完成 (${elapsed}s)。`, "ok");
    } else {
      const errMsg = run.error ? `: ${run.error.message}` : "";
      setNotice(`渲染失败${errMsg}`, "error");
    }
  } catch (error) {
    clearInterval(timer);
    setNotice(`渲染失败：${error.message}`, "error");
  } finally {
    state.busy = false;
    updateRenderButton();
  }
}

function handleStageClick(card) {
  if (state.busy) {
    setNotice("请等待当前操作完成后再点击。", "muted");
    return;
  }
  const stage = card.dataset.stage;
  const statusEl = card.querySelector("strong");
  if (!statusEl || !stage) return;
  const status = statusEl.textContent.trim();

  if (!state.currentRun) {
    setNotice("请先填写教学主题并点击「生成动画方案」。", "muted");
    return;
  }

  if (status === "已完成") {
    const tab = card.dataset.tab;
    if (tab) switchTab(tab);
    return;
  }

  if (stage === "render") {
    if (status === "待渲染") {
      renderCurrentRun();
      return;
    }
    if (status !== "已渲染" && status !== "渲染中") {
      setNotice("当前没有可渲染的内容，请先生成动画方案。", "warn");
      return;
    }
    return;
  }

  // intent / storyboard / codegen — regenerate stage
  if (status === "已完成") return;
  restageStage(stage);
}

async function restageStage(stage) {
  if (!state.currentRun) return;
  const stageLabels = { intent: "意图分析", storyboard: "分镜", codegen: "代码生成" };
  const label = stageLabels[stage] || stage;
  setNotice(`正在重新生成 ${label} 阶段...`, "warn");
  try {
    const result = await api(`/api/runs/${encodeURIComponent(state.currentRun.run_id)}/restage`, {
      method: "POST",
      body: JSON.stringify({ stage }),
    });
    if (result.error) {
      setNotice(`重新生成失败：${result.error}`, "error");
      return;
    }
    renderRun(result);
    await loadRuns();
    setNotice(`${label} 阶段重新生成完成。`, "ok");
  } catch (error) {
    setNotice(`重新生成失败：${error.message}`, "error");
  }
}

async function loadRuns() {
  try {
    const payload = await api("/api/runs");
    const list = $("#run-list");
    list.innerHTML = "";
    for (const run of payload.runs) {
      const item = document.createElement("article");
      item.className = "run-item";
      item.innerHTML = `
        <div class="run-title">
          <strong>${escapeHtml(run.prompt || run.run_id)}</strong>
          <span>${run.run_id}</span>
        </div>
        <button class="secondary-action compact" type="button">打开</button>
      `;
      item.querySelector("button").addEventListener("click", () => openRun(run.run_id));
      list.appendChild(item);
    }
    if (!payload.runs.length) {
      list.innerHTML = `<div class="notice">暂无历史运行。</div>`;
    }
  } catch (error) {
    setNotice(`历史读取失败：${error.message}`, "error");
  }
}

async function openRun(runId) {
  try {
    const run = await api(`/api/runs/${encodeURIComponent(runId)}`);
    renderRun(run);
    switchPanel("generate");
  } catch (error) {
    setNotice(`打开运行失败：${error.message}`, "error");
  }
}

function renderRun(run) {
  state.currentRun = run;
  $("#run-dir").textContent = run.run_dir || "-";
  $("#copy-run-dir-button").disabled = !run.run_dir;
  setStageState(
    run.status.validation === "passed" ? "完成" : "待生成",
    run.sections?.storyboard ? "完成" : "待生成",
    run.sections?.manim_code ? "完成" : "待生成",
    renderLabel(run.status.render),
  );
  $("#render-state").textContent = renderLabel(run.status.render);
  $("#render-state").className = `status-pill ${run.video_url ? "ok" : "muted"}`;
  if (run.video_url) {
    $("#video-frame").innerHTML = `<video controls src="${run.video_url}?t=${Date.now()}"></video>`;
  } else if (run.error) {
    const details = run.error.details ? `\n\n详情：${escapeHtml(formatDetails(run.error.details)).slice(0, 800)}` : "";
    $("#video-frame").innerHTML = `<span class="error-detail">${escapeHtml(run.error.stage || "错误")}: ${escapeHtml(run.error.message)}${details}</span>`;
  } else {
    $("#video-frame").innerHTML = `<span>等待渲染</span>`;
  }
  switchTab(state.currentTab);
  updateRenderButton();
}

function switchPanel(panel) {
  $$(".nav-item").forEach((button) => button.classList.toggle("active", button.dataset.panel === panel));
  $$(".panel").forEach((section) => section.classList.toggle("active", section.id === `panel-${panel}`));
}

function switchTab(tab) {
  state.currentTab = tab;
  $$(".tab").forEach((button) => button.classList.toggle("active", button.dataset.tab === tab));
  const content = state.currentRun?.sections?.[tab] || "等待生成。";
  $("#artifact-content").textContent = content;
}

function updateRenderButton() {
  const hasRun = Boolean(state.currentRun);
  const validationPassed = state.currentRun?.status?.validation === "passed";
  const healthReady = Boolean(state.health?.ready);
  $("#render-button").disabled = !(hasRun && validationPassed && healthReady);
}

function setStageState(intent, storyboard, code, render) {
  // Normalise stage names for click handler consistency
  const norm = (v) => (v === "完成" ? "已完成" : v);
  $("#stage-intent").textContent = norm(intent);
  $("#stage-storyboard").textContent = norm(storyboard);
  $("#stage-code").textContent = norm(code);
  $("#stage-render").textContent = render;
}

function renderLabel(status) {
  if (status === "succeeded") return "已渲染";
  if (status === "failed") return "待渲染";
  if (status === "running") return "渲染中";
  return "待渲染";
}

function setNotice(message, level = "muted") {
  const notice = $("#notice");
  notice.textContent = message;
  notice.className = `notice ${level}`;
}

const EXAMPLES = [
  { label: "勾股定理面积证明", prompt: "用面积动画直观展示勾股定理 a\u00b2 + b\u00b2 = c\u00b2，通过正方形面积拼接展示证明过程，适合初中生理解。", audience_level: "middle_school", desired_duration: "60", style: "minimal geometric" },
  { label: "圆柱体体积公式", prompt: "用三维动画展示圆柱体体积 V = \u03c0r\u00b2h 的推导过程，通过切割和叠加圆片的方法帮助初中生理解。", audience_level: "middle_school", desired_duration: "45", style: "clean classroom" },
  { label: "一次函数图像", prompt: "用平面直角坐标系展示一次函数 y = kx + b 的图像变化，拖动参数 k 和 b 观察直线如何变化。", audience_level: "middle_school", desired_duration: "60", style: "clean classroom" },
  { label: "相似三角形判定", prompt: "用几何动画直观展示相似三角形的三种判定方法，通过角度和边长的对比帮助学生理解相似原理。", audience_level: "middle_school", desired_duration: "60", style: "blackboard" },
];

let exampleIndex = 0;

function loadExample() {
  const ex = EXAMPLES[exampleIndex];
  $("#prompt").value = ex.prompt;
  $("#audience-level").value = ex.audience_level;
  $("#desired-duration").value = ex.desired_duration;
  $("#style").value = ex.style;
  setNotice(`已载入示例：${ex.label}。`, "ok");
  exampleIndex = (exampleIndex + 1) % EXAMPLES.length;
  setTimeout(() => { if ($("#notice").textContent.startsWith("已载入示例")) setNotice("", "muted"); }, 3000);
}

async function copyRunDir() {
  if (!state.currentRun?.run_dir) return;
  try {
    await navigator.clipboard.writeText(state.currentRun.run_dir);
    setNotice("运行目录已复制。", "ok");
  } catch (error) {
    setNotice(state.currentRun.run_dir, "muted");
  }
}

function openSettings() {
  $("#settings-overlay").classList.add("open");
  switchSettingsTab("config");
}

function closeSettings() {
  $("#settings-overlay").classList.remove("open");
}

function switchSettingsTab(tab) {
  $$(".settings-tab").forEach((btn) => btn.classList.toggle("active", btn.dataset.settingsTab === tab));
  $$(".settings-section").forEach((sec) => sec.classList.toggle("active", sec.id === `settings-${tab}`));
}

function formatDetails(value) {
  if (Array.isArray(value)) {
    return value.map((item) => {
      if (typeof item === "object" && item !== null) {
        return item.message || item.code || JSON.stringify(item);
      }
      return String(item);
    }).join("; ");
  }
  if (typeof value === "object" && value !== null) {
    return value.message || JSON.stringify(value);
  }
  return String(value);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
