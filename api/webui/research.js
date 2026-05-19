const state = {
  jobs: [],
  selectedJob: null,
};

const $ = (id) => document.getElementById(id);

function splitKeywords(value) {
  return value
    .split(/[\n,，]/)
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
    keywords: splitKeywords($("jobKeywords").value),
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
  $("jobKeywords").value = (job?.keywords || []).join("\n");
  $("startDate").value = job?.start_date || "";
  $("endDate").value = job?.end_date || "";
  $("rawRecordMode").value = job?.raw_record_mode || "minimal";
  $("anonymizeAuthors").checked = job?.anonymize_authors ?? true;
  const platforms = new Set(job?.platforms || ["wb", "zhihu"]);
  document.querySelectorAll("input[name='platform']").forEach((item) => {
    item.checked = platforms.has(item.value);
  });
  const policy = job?.comment_policy || {};
  $("commentMode").value = policy.full_comment_crawl ? "full" : "limited";
  $("commentLimit").value = policy.comment_limit_per_post || 100;
}

async function loadJobs() {
  const data = await api("/api/research/jobs");
  state.jobs = data.jobs || [];
  renderJobs();
}

function renderJobs() {
  $("jobList").innerHTML = state.jobs
    .map(
      (job) => `
      <div class="job-item ${state.selectedJob?.id === job.id ? "selected" : ""}" data-id="${job.id}">
        <strong>${escapeHtml(job.name)}</strong>
        <div class="muted">${job.platforms.join(", ")} · ${job.keywords.join(" / ")}</div>
        <div class="muted">${job.start_date} 到 ${job.end_date} · ${job.status}</div>
      </div>`
    )
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
}

async function saveJob() {
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
        <div class="muted">${event.platform || "job"} · ${event.created_at || ""}</div>
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
  await api("/api/research/ai/providers", { method: "POST", body: JSON.stringify(payload) });
  await loadProviders();
}

async function loadProviders() {
  const data = await api("/api/research/ai/providers");
  $("providerList").innerHTML = (data.providers || [])
    .map(
      (provider) => `
        <div class="provider-item">
          <strong>${escapeHtml(provider.name)}</strong>
          <div class="muted">${escapeHtml(provider.model)} · ${escapeHtml(provider.base_url)}</div>
        </div>`
    )
    .join("");
}

async function exportJob() {
  ensureSelected();
  const result = await api(`/api/research/jobs/${state.selectedJob.id}/export`, { method: "POST" });
  $("exportResult").textContent = JSON.stringify(result, null, 2);
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
    ctx.fillText(String(row[labelKey]).slice(0, 8), x, height - 12);
  });
}

function ensureSelected() {
  if (!state.selectedJob) throw new Error("请先选择或保存任务");
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function bindEvents() {
  $("refreshBtn").addEventListener("click", loadJobs);
  $("newJobBtn").addEventListener("click", () => {
    state.selectedJob = null;
    writeJobForm(null);
    renderJobs();
  });
  $("createBtn").addEventListener("click", () => saveJob().catch(alert));
  $("planBtn").addEventListener("click", () => previewPlan().catch(alert));
  $("executeBtn").addEventListener("click", () => executeJob().catch(alert));
  $("loadStatsBtn").addEventListener("click", () => loadStats().catch(alert));
  $("loadEventsBtn").addEventListener("click", () => loadEvents().catch(alert));
  $("loadChartsBtn").addEventListener("click", () => loadCharts().catch(alert));
  $("saveProviderBtn").addEventListener("click", () => saveProvider().catch(alert));
  $("exportBtn").addEventListener("click", () => exportJob().catch(alert));
}

bindEvents();
loadJobs().catch(() => {});
loadProviders().catch(() => {});
