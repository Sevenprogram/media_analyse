const state = {
  jobs: [],
  selectedJob: null,
  configOptions: { platforms: [], collection_modes: [] },
  lastProviderId: null,
  databaseReady: null,
};

const $ = (id) => document.getElementById(id);

function splitList(value) {
  return String(value || "")
    .split(/[\n,，]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

async function loadConfigOptions() {
  const data = await api("/api/research/config/options");
  state.configOptions = data;
  renderPlatformChecks();
  renderCollectionModes();
}

async function loadSetupStatus() {
  const data = await api("/api/research/setup/status");
  const saveOption = data.database?.save_data_option;
  state.databaseReady = ["sqlite", "postgres", "mysql", "db"].includes(saveOption);
  $("setupStatus").textContent = JSON.stringify(data, null, 2);
  $("setupSummary").innerHTML = [
    summaryItem("存储", data.database?.save_data_option || "-"),
    summaryItem("PostgreSQL", data.database?.postgres?.password_set ? "已配置密码" : "未配置密码"),
    summaryItem("脱敏盐", data.environment?.author_hash_salt_set ? "已设置" : "未设置"),
    summaryItem("研究表", data.database?.research_tables_registered ? "已注册" : "缺失"),
  ].join("");
}

function summaryItem(label, value) {
  return `<div class="stat"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`;
}

function renderCollectionModes() {
  const select = $("collectionMode");
  const current = select.value || state.selectedJob?.collection_mode || "search";
  const modes = state.configOptions.collection_modes?.length
    ? state.configOptions.collection_modes
    : [
        { value: "search", label: "关键词搜索" },
        { value: "detail", label: "指定内容" },
        { value: "creator", label: "作者主页" },
      ];
  select.innerHTML = modes
    .map(
      (mode) =>
        `<option value="${escapeHtml(mode.value)}">${escapeHtml(mode.label)}</option>`
    )
    .join("");
  select.value = current;
}

function renderPlatformChecks(selectedValues) {
  const selected = new Set(selectedValues || state.selectedJob?.platforms || ["wb", "zhihu"]);
  const platforms = state.configOptions.platforms?.length
    ? state.configOptions.platforms
    : [
        { value: "wb", label: "Weibo", backfill_supported: true },
        { value: "zhihu", label: "Zhihu", backfill_supported: true },
      ];
  $("platformChecks").innerHTML = platforms
    .map(
      (platform) => `
      <label class="check">
        <input type="checkbox" name="platform" value="${escapeHtml(platform.value)}" ${
          selected.has(platform.value) ? "checked" : ""
        } />
        ${escapeHtml(platform.label)}
        <span class="badge">${platform.backfill_supported ? "回填" : "仅采集"}</span>
      </label>`
    )
    .join("");
}

function readJobForm() {
  const platforms = [...document.querySelectorAll("input[name='platform']:checked")].map(
    (item) => item.value
  );
  const mode = $("commentMode").value;
  const limit = Number($("commentLimit").value || 100);
  const commentPolicy =
    mode === "full"
      ? {
          enable_comments: true,
          comment_limit_per_post: null,
          enable_sub_comments: true,
          sub_comment_limit_per_comment: null,
          full_comment_crawl: true,
          rate_limit_per_minute: 30,
          max_posts_per_job: 100,
          ethical_note: "Research task requires full comment collection.",
        }
      : {
          enable_comments: true,
          comment_limit_per_post: limit,
          enable_sub_comments: false,
          sub_comment_limit_per_comment: 0,
          full_comment_crawl: false,
        };
  return {
    name: $("jobName").value.trim(),
    topic: $("jobTopic").value.trim(),
    platforms,
    collection_mode: $("collectionMode").value,
    keywords: splitList($("jobKeywords").value),
    target_ids: splitList($("targetIds").value),
    creator_ids: splitList($("creatorIds").value),
    start_date: $("startDate").value,
    end_date: $("endDate").value,
    comment_policy: commentPolicy,
    raw_record_mode: $("rawRecordMode").value,
    anonymize_authors: $("anonymizeAuthors").checked,
  };
}

function writeJobForm(job) {
  $("selectedJobId").textContent = job ? `#${job.id}` : "未保存";
  $("jobName").value = job?.name || "";
  $("jobTopic").value = job?.topic || "";
  $("collectionMode").value = job?.collection_mode || "search";
  $("jobKeywords").value = (job?.keywords || []).join("\n");
  $("targetIds").value = (job?.target_ids || []).join("\n");
  $("creatorIds").value = (job?.creator_ids || []).join("\n");
  $("startDate").value = job?.start_date || "";
  $("endDate").value = job?.end_date || "";
  $("rawRecordMode").value = job?.raw_record_mode || "minimal";
  $("anonymizeAuthors").checked = job?.anonymize_authors ?? true;
  renderCollectionModes();
  renderPlatformChecks(job?.platforms);
  const policy = job?.comment_policy || {};
  $("commentMode").value = policy.full_comment_crawl ? "full" : "limited";
  $("commentLimit").value = policy.comment_limit_per_post || 100;
}

async function loadJobs() {
  if (state.databaseReady === false) {
    state.jobs = [];
    renderJobs();
    return;
  }
  const data = await api("/api/research/jobs");
  state.jobs = data.jobs || [];
  if (state.selectedJob) {
    state.selectedJob = state.jobs.find((job) => job.id === state.selectedJob.id) || null;
  }
  renderJobs();
}

function renderJobs() {
  if (!state.jobs.length && state.databaseReady === false) {
    $("jobList").innerHTML =
      '<div class="job-item"><strong>数据库未启用</strong><div class="muted">请先将 SAVE_DATA_OPTION 设置为 sqlite、postgres、mysql 或 db。</div></div>';
    return;
  }
  $("jobList").innerHTML = state.jobs
    .map((job) => {
      const mode = job.collection_mode || "search";
      const inputs =
        mode === "detail"
          ? job.target_ids || []
          : mode === "creator"
            ? job.creator_ids || []
            : job.keywords || [];
      return `
      <div class="job-item ${state.selectedJob?.id === job.id ? "selected" : ""}" data-id="${job.id}">
        <strong>${escapeHtml(job.name)}</strong>
        <div class="muted">${escapeHtml(job.platforms.join(", "))} | ${escapeHtml(mode)} | ${escapeHtml(inputs.join(" / "))}</div>
        <div class="muted">${escapeHtml(job.start_date)} 至 ${escapeHtml(job.end_date)} | ${escapeHtml(job.status)}</div>
      </div>`;
    })
    .join("");
  document.querySelectorAll(".job-item").forEach((item) => {
    item.addEventListener("click", () => selectJob(Number(item.dataset.id)));
  });
}

function selectJob(id) {
  state.selectedJob = state.jobs.find((job) => job.id === id);
  writeJobForm(state.selectedJob);
  $("statusText").textContent = `当前任务 #${id}`;
  renderJobs();
  refreshSelectedJobViews().catch(() => {});
}

async function saveJob() {
  ensureDatabaseReady();
  const payload = readJobForm();
  const job = state.selectedJob
    ? await api(`/api/research/jobs/${state.selectedJob.id}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      })
    : await api("/api/research/jobs", { method: "POST", body: JSON.stringify(payload) });
  state.selectedJob = job;
  await loadJobs();
  selectJob(job.id);
}

async function previewPlan() {
  ensureSelected();
  const plan = await api(`/api/research/jobs/${state.selectedJob.id}/execution/plan`, {
    method: "POST",
    body: JSON.stringify({ backfill_after_crawl: true }),
  });
  $("executionPlan").textContent = JSON.stringify(plan, null, 2);
}

async function executeJob() {
  ensureSelected();
  const result = await api(`/api/research/jobs/${state.selectedJob.id}/execute`, {
    method: "POST",
    body: JSON.stringify({ backfill_after_crawl: true }),
  });
  $("executionPlan").textContent = JSON.stringify(result, null, 2);
  await loadExecutionStatus();
}

async function loadExecutionStatus() {
  const result = await api("/api/research/execution/status");
  $("executionPlan").textContent = JSON.stringify(result, null, 2);
  if (state.selectedJob) await loadJobs();
}

async function stopExecution() {
  const result = await api("/api/research/execution/stop", { method: "POST" });
  $("executionPlan").textContent = JSON.stringify(result, null, 2);
}

async function loadStats() {
  ensureSelected();
  const stats = await api(`/api/research/jobs/${state.selectedJob.id}/stats`);
  $("statsGrid").innerHTML = ["posts", "comments", "authors", "raw_records"]
    .map((key) => `<div class="stat"><span>${key}</span><strong>${stats[key] || 0}</strong></div>`)
    .join("");
}

async function loadEvents() {
  ensureSelected();
  const data = await api(`/api/research/jobs/${state.selectedJob.id}/events`);
  $("eventList").innerHTML = (data.events || [])
    .map(
      (event) => `
      <div class="event-item">
        <strong>${escapeHtml(event.event_type)}</strong>
        <div>${escapeHtml(event.message)}</div>
        <div class="muted">${escapeHtml(event.platform || "job")} | ${escapeHtml(event.created_at || "")}</div>
      </div>`
    )
    .join("");
}

async function loadCharts() {
  ensureSelected();
  const data = await api(`/api/research/jobs/${state.selectedJob.id}/charts/summary`);
  drawBarChart($("platformChart"), "平台数据量", data.platform_counts || [], "platform", "posts");
  drawBarChart($("postTrendChart"), "发帖趋势", data.post_trend || [], "date", "posts");
  drawBarChart($("keywordChart"), "关键词排行", data.keyword_ranking || [], "keyword", "count");
  drawBarChart($("sentimentChart"), "情绪分布", data.sentiment_distribution || [], "name", "value");
}

async function saveProvider() {
  const payload = {
    name: $("providerName").value.trim(),
    base_url: $("providerBaseUrl").value.trim(),
    api_key: $("providerApiKey").value,
    model: $("providerModel").value.trim(),
  };
  const provider = await api("/api/research/ai/providers", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  state.lastProviderId = provider.id;
  $("analysisProviderId").value = provider.id;
  await loadProviders();
}

async function testProvider() {
  const providerId = Number($("analysisProviderId").value || state.lastProviderId);
  if (!providerId) throw new Error("请先保存或填写 Provider ID");
  const result = await api(`/api/research/ai/providers/${providerId}/test`, { method: "POST" });
  $("executionPlan").textContent = JSON.stringify(result, null, 2);
}

async function savePrompt() {
  const payload = {
    name: $("promptName").value.trim(),
    task_type: $("promptTaskType").value,
    platform: "all",
    prompt_text: $("promptText").value,
    output_schema: {},
    version: "v1",
    enabled: true,
  };
  const prompt = await api("/api/research/ai/prompts", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  $("analysisPromptId").value = prompt.id;
  await loadPrompts();
}

async function createAndRunAnalysis() {
  ensureSelected();
  const payload = {
    research_job_id: state.selectedJob.id,
    task_type: $("promptTaskType").value,
    scope: {
      target_type: $("analysisTargetType").value,
      limit: Number($("analysisLimit").value || 50),
    },
    provider_config_id: Number($("analysisProviderId").value),
    prompt_template_id: Number($("analysisPromptId").value),
  };
  const job = await api("/api/research/ai/analysis-jobs", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  const result = await api(`/api/research/ai/analysis-jobs/${job.id}/run`, {
    method: "POST",
  });
  $("executionPlan").textContent = JSON.stringify(result, null, 2);
  await loadAnalysisJobs();
}

async function loadProviders() {
  if (state.databaseReady === false) {
    $("providerList").innerHTML =
      '<div class="provider-item"><strong>数据库未启用</strong><div class="muted">AI Provider 需要 sqlite、postgres、mysql 或 db 存储。</div></div>';
    return;
  }
  const data = await api("/api/research/ai/providers");
  $("providerList").innerHTML = (data.providers || [])
    .map(
      (provider) => `
        <div class="provider-item">
          <strong>#${provider.id} ${escapeHtml(provider.name)}</strong>
          <div class="muted">${escapeHtml(provider.model)} | ${escapeHtml(provider.base_url)}</div>
        </div>`
    )
    .join("");
  const first = (data.providers || [])[0];
  if (first) {
    state.lastProviderId = first.id;
    if (!$("analysisProviderId").value) $("analysisProviderId").value = first.id;
  }
}

async function loadPrompts() {
  if (state.databaseReady === false) {
    $("promptList").innerHTML =
      '<div class="provider-item"><strong>数据库未启用</strong><div class="muted">Prompt 配置需要 sqlite、postgres、mysql 或 db 存储。</div></div>';
    return;
  }
  const data = await api("/api/research/ai/prompts");
  $("promptList").innerHTML = (data.prompts || [])
    .map(
      (prompt) => `
        <div class="provider-item">
          <strong>#${prompt.id} ${escapeHtml(prompt.name)}</strong>
          <div class="muted">${escapeHtml(prompt.task_type)} | ${escapeHtml(prompt.version)}</div>
        </div>`
    )
    .join("");
  const first = (data.prompts || [])[0];
  if (first && !$("analysisPromptId").value) $("analysisPromptId").value = first.id;
}

async function loadAnalysisJobs() {
  if (!state.selectedJob) return;
  const data = await api(`/api/research/jobs/${state.selectedJob.id}/ai/analysis-jobs`);
  $("analysisJobList").innerHTML = (data.jobs || [])
    .map(
      (job) => `
        <div class="provider-item">
          <strong>#${job.id} ${escapeHtml(job.task_type)}</strong>
          <div class="muted">${escapeHtml(job.status)} | provider ${job.provider_config_id} | prompt ${job.prompt_template_id}</div>
        </div>`
    )
    .join("");
}

async function loadAiResults() {
  ensureSelected();
  const data = await api(`/api/research/jobs/${state.selectedJob.id}/ai/results`);
  $("aiResultList").innerHTML = (data.results || [])
    .slice(0, 20)
    .map(
      (result) => `
        <div class="provider-item">
          <strong>${escapeHtml(result.target_type)} ${escapeHtml(result.target_id)}</strong>
          <pre>${escapeHtml(JSON.stringify(result.result_json, null, 2))}</pre>
        </div>`
    )
    .join("");
}

async function exportJob() {
  ensureSelected();
  const result = await api(`/api/research/jobs/${state.selectedJob.id}/export`, { method: "POST" });
  $("exportResult").textContent = JSON.stringify(result, null, 2);
  await loadExportFiles();
}

async function loadExportFiles() {
  ensureSelected();
  const data = await api(`/api/research/exports/${state.selectedJob.id}/files`);
  $("exportFiles").innerHTML = (data.files || [])
    .map(
      (file) => `
      <a class="file-item" href="${escapeHtml(file.download_url)}" target="_blank" rel="noreferrer">
        <span>${escapeHtml(file.path)}</span>
        <small>${formatBytes(file.size)}</small>
      </a>`
    )
    .join("");
}

async function refreshSelectedJobViews() {
  if (!state.selectedJob) return;
  await Promise.allSettled([loadStats(), loadEvents(), loadAnalysisJobs(), loadAiResults()]);
}

function drawBarChart(canvas, title, rows, labelKey, valueKey) {
  const ctx = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#172326";
  ctx.font = "16px Segoe UI";
  ctx.fillText(title, 18, 28);
  const plotTop = 48;
  const plotHeight = height - 76;
  const max = Math.max(1, ...rows.map((row) => Number(row[valueKey] || 0)));
  const barWidth = rows.length ? Math.max(18, (width - 50) / rows.length - 10) : 18;
  rows.slice(0, 12).forEach((row, index) => {
    const value = Number(row[valueKey] || 0);
    const barHeight = (value / max) * plotHeight;
    const x = 24 + index * (barWidth + 10);
    const y = plotTop + plotHeight - barHeight;
    ctx.fillStyle = index % 2 ? "#8b5d33" : "#2f6f73";
    ctx.fillRect(x, y, barWidth, barHeight);
    ctx.fillStyle = "#4d5a5e";
    ctx.font = "11px Segoe UI";
    ctx.fillText(String(row[labelKey] || "").slice(0, 8), x, height - 12);
  });
}

function ensureSelected() {
  if (!state.selectedJob) throw new Error("请先选择或保存任务");
}

function ensureDatabaseReady() {
  if (state.databaseReady === false) {
    throw new Error("请先将 SAVE_DATA_OPTION 设置为 sqlite、postgres、mysql 或 db");
  }
}

function formatBytes(size) {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function bindEvents() {
  $("refreshBtn").addEventListener("click", () => loadJobs().catch(alert));
  $("setupStatusBtn").addEventListener("click", () => loadSetupStatus().catch(alert));
  $("newJobBtn").addEventListener("click", () => {
    state.selectedJob = null;
    writeJobForm(null);
    $("statusText").textContent = "未选择任务";
    renderJobs();
  });
  $("createBtn").addEventListener("click", () => saveJob().catch(alert));
  $("planBtn").addEventListener("click", () => previewPlan().catch(alert));
  $("executeBtn").addEventListener("click", () => executeJob().catch(alert));
  $("statusBtn").addEventListener("click", () => loadExecutionStatus().catch(alert));
  $("stopBtn").addEventListener("click", () => stopExecution().catch(alert));
  $("loadStatsBtn").addEventListener("click", () => loadStats().catch(alert));
  $("loadEventsBtn").addEventListener("click", () => loadEvents().catch(alert));
  $("loadChartsBtn").addEventListener("click", () => loadCharts().catch(alert));
  $("saveProviderBtn").addEventListener("click", () => saveProvider().catch(alert));
  $("testProviderBtn").addEventListener("click", () => testProvider().catch(alert));
  $("savePromptBtn").addEventListener("click", () => savePrompt().catch(alert));
  $("createAnalysisBtn").addEventListener("click", () => createAndRunAnalysis().catch(alert));
  $("loadAiResultsBtn").addEventListener("click", () => loadAiResults().catch(alert));
  $("exportBtn").addEventListener("click", () => exportJob().catch(alert));
  $("loadExportFilesBtn").addEventListener("click", () => loadExportFiles().catch(alert));
}

bindEvents();
init().catch((error) => {
  $("executionPlan").textContent = error.message;
});
setInterval(() => {
  loadExecutionStatus().catch(() => {});
  refreshSelectedJobViews().catch(() => {});
}, 10000);

async function init() {
  await loadConfigOptions().catch(() => {});
  writeJobForm(null);
  await loadSetupStatus().catch(() => {});
  await Promise.allSettled([loadJobs(), loadProviders(), loadPrompts()]);
}
