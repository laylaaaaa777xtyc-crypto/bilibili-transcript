const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

const state = { job: null, detail: null, pollTimer: null };
const fileDescriptions = {
  "metadata.json": "视频信息",
  "transcript.json": "原始事实源",
  "transcript.txt": "纯文本",
  "transcript.md": "时间分块稿",
  "transcript.srt": "字幕文件",
  "article.md": "可读文稿",
};

function escapeHtml(value = "") {
  return String(value).replace(/[&<>'"]/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;"
  })[char]);
}

function toast(message) {
  const node = $("#toast");
  node.textContent = message;
  node.classList.add("show");
  window.clearTimeout(node._timer);
  node._timer = window.setTimeout(() => node.classList.remove("show"), 2200);
}

async function request(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || "请求失败，请稍后重试");
  return data;
}

function showState(name) {
  $("#empty-state").classList.toggle("hidden", name !== "empty");
  $("#progress-state").classList.toggle("hidden", name !== "progress");
  $("#result-state").classList.toggle("hidden", name !== "result");
}

async function loadHistory() {
  const list = $("#history-list");
  try {
    const data = await request("/api/results");
    if (!data.items.length) {
      list.innerHTML = '<div class="history-empty">还没有文稿，先从一个视频开始。</div>';
      return;
    }
    list.innerHTML = data.items.map((item) => `
      <button class="history-item" type="button" data-video-id="${escapeHtml(item.video_id)}">
        <span class="history-icon">稿</span>
        <span><strong>${escapeHtml(item.title)}</strong><small>${escapeHtml(item.video_id)} · ${item.segments} 段</small></span>
      </button>`).join("");
    $$(".history-item").forEach((button) => button.addEventListener("click", () => openResult(button.dataset.videoId)));
  } catch (error) {
    list.innerHTML = `<div class="history-empty">${escapeHtml(error.message)}</div>`;
  }
}

function updateProgress(job) {
  $("#progress-title").textContent = job.stage || "正在处理";
  $("#progress-video-id").textContent = job.video_id;
  $("#job-logs").textContent = job.logs?.join("\n") || "等待输出…";
  const isAsr = job.stage?.includes("语音识别");
  const isSaving = job.stage?.includes("保存");
  const steps = [$("#step-submit"), $("#step-source"), $("#step-save"), $("#step-done")];
  steps.forEach((step) => step.className = "");
  steps[0].className = "done";
  steps[0].querySelector("i").textContent = "✓";
  if (isSaving) {
    steps[1].className = "done"; steps[1].querySelector("i").textContent = "✓";
    steps[2].className = "active";
    $("#progress-bar").style.width = "78%";
  } else {
    steps[1].className = "active";
    $("#progress-bar").style.width = isAsr ? "54%" : "38%";
  }
}

async function pollJob(jobId) {
  window.clearTimeout(state.pollTimer);
  try {
    const job = await request(`/api/jobs/${jobId}`);
    state.job = job;
    updateProgress(job);
    if (job.status === "completed") {
      $("#progress-bar").style.width = "100%";
      await openResult(job.video_id, job.logs);
      loadHistory();
      $("#submit-button").disabled = false;
      return;
    }
    if (job.status === "failed") {
      $("#submit-button").disabled = false;
      toast(job.error || "处理失败，请查看日志");
      $("#progress-title").textContent = "处理失败";
      $("#failure-message").textContent = job.error || "请展开运行日志查看具体原因。";
      $("#failure-box").classList.remove("hidden");
      $("#job-logs").closest("details").open = true;
      return;
    }
    state.pollTimer = window.setTimeout(() => pollJob(jobId), 1200);
  } catch (error) {
    $("#submit-button").disabled = false;
    toast(error.message);
  }
}

function renderMarkdownPreview(markdown) {
  const lines = String(markdown || "").split(/\n/);
  return lines.map((line) => {
    if (line.startsWith("# ")) return `<h1>${escapeHtml(line.slice(2))}</h1>`;
    if (!line.trim()) return "";
    return `<p>${escapeHtml(line)}</p>`;
  }).join("");
}

async function openResult(videoId, logs = null) {
  try {
    const detail = await request(`/api/results/${encodeURIComponent(videoId)}`);
    state.detail = detail;
    $("#result-title").textContent = detail.title;
    $("#result-id").textContent = detail.video_id;
    const source = detail.part_sources?.map((item) => item.mode).filter(Boolean).join(" + ") || "缓存";
    $("#result-source").textContent = source;
    $("#result-segments").textContent = `${detail.segments} 段字幕`;
    $("#article-preview").innerHTML = renderMarkdownPreview(detail.preview) || "<p>暂无正文预览。</p>";
    $("#file-grid").innerHTML = detail.files.map((filename) => `
      <div class="file-card">
        <span><strong>${escapeHtml(filename)}</strong><small>${escapeHtml(fileDescriptions[filename] || "结果文件")}</small></span>
        <a href="/api/results/${encodeURIComponent(videoId)}/files/${encodeURIComponent(filename)}" download>下载</a>
      </div>`).join("");
    $("#result-logs").textContent = (logs || state.job?.logs || []).join("\n") || "此结果来自历史缓存，没有本次运行日志。";
    showState("result");
    activateTab("preview");
  } catch (error) {
    toast(error.message);
  }
}

function activateTab(name) {
  $$(".tab").forEach((tab) => tab.classList.toggle("active", tab.dataset.tab === name));
  $$(".tab-panel").forEach((panel) => panel.classList.toggle("active", panel.id === `tab-${name}`));
}

$("#job-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const url = $("#video-url").value.trim();
  if (!url) return toast("请先粘贴 Bilibili 视频链接");
  const payload = {
    url,
    article: $("#article").checked,
    refresh: $("#refresh").checked,
    force_asr: $("#force-asr").checked,
    model: $("#model").value,
    device: $("#device").value,
    cookies_from_browser: $("#cookies").value,
  };
  $("#submit-button").disabled = true;
  $("#failure-box").classList.add("hidden");
  try {
    const job = await request("/api/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    state.job = job;
    localStorage.setItem("biliscribe:last-url", url);
    showState("progress");
    updateProgress(job);
    pollJob(job.id);
  } catch (error) {
    $("#submit-button").disabled = false;
    toast(error.message);
  }
});

$("#paste-button").addEventListener("click", async () => {
  try {
    $("#video-url").value = await navigator.clipboard.readText();
  } catch (_) {
    toast("浏览器未授权读取剪贴板，请手动粘贴");
  }
});
$("#refresh-history").addEventListener("click", loadHistory);
$("#new-task").addEventListener("click", () => { showState("empty"); $("#video-url").focus(); });
$("#edit-job").addEventListener("click", () => { showState("empty"); $("#video-url").focus(); });
$("#retry-job").addEventListener("click", () => $("#job-form").requestSubmit());
$("#copy-result").addEventListener("click", async () => {
  if (!state.detail?.preview) return;
  try { await navigator.clipboard.writeText(state.detail.preview); toast("正文已复制"); }
  catch (_) { toast("复制失败，请在正文中手动选择"); }
});
$$(".tab").forEach((tab) => tab.addEventListener("click", () => activateTab(tab.dataset.tab)));

const rememberedUrl = localStorage.getItem("biliscribe:last-url");
if (rememberedUrl) $("#video-url").value = rememberedUrl;
loadHistory();
