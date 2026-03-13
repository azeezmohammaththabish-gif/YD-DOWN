// ===== API Configuration (works with Vercel + Render setup) =====
// Automatically detect backend API URL:
// - Local dev: uses relative paths (/api/...)
// - Vercel + Render: uses backend service URL from localStorage
const API_URL = (() => {
  // Check if backend URL is stored in localStorage (set by admin panel)
  const stored = localStorage.getItem("BACKEND_API_URL");
  if (stored) return stored;
  
  // For local dev, use relative paths
  if (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1") {
    return "";
  }
  
  // For Vercel deployment, you can set this in browser or use environment variable
  // Default to same origin (if backend is on same domain)
  return window.location.origin;
})();

const urlInput = document.getElementById("urlInput");
const analyzeBtn = document.getElementById("analyzeBtn");
const qualitySelect = document.getElementById("qualitySelect");
const downloadBtn = document.getElementById("downloadBtn");
const statusLine = document.getElementById("statusLine");
const errorBox = document.getElementById("errorBox");
const videoMeta = document.getElementById("videoMeta");
const preview = document.getElementById("preview");
const thumb = document.getElementById("thumb");
const previewTitle = document.getElementById("previewTitle");
const previewMeta = document.getElementById("previewMeta");

const tabVideo = document.getElementById("tabVideo");
const tabAudio = document.getElementById("tabAudio");
const optionsVideo = document.getElementById("optionsVideo");
const optionsAudio = document.getElementById("optionsAudio");
const playlistList = document.getElementById("playlistList");

let lastAnalyzed = null; // { title, video_id, qualities, options }

function showError(msg) {
  errorBox.textContent = msg;
  errorBox.classList.remove("hidden");
}

function clearError() {
  errorBox.textContent = "";
  errorBox.classList.add("hidden");
}

function setStatus(msg) {
  statusLine.textContent = msg || "";
}

function fmtDate(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleString();
  } catch {
    return iso || "";
  }
}

function fmtBytes(n) {
  if (typeof n !== "number" || !isFinite(n)) return "";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let v = n;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(v >= 10 || i === 0 ? 0 : 1)} ${units[i]}`;
}

function fmtDuration(sec) {
  if (typeof sec !== "number" || !isFinite(sec) || sec <= 0) return "";
  const s = Math.floor(sec);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const r = s % 60;
  const mm = String(m).padStart(2, "0");
  const rr = String(r).padStart(2, "0");
  return h > 0 ? `${h}:${mm}:${rr}` : `${m}:${rr.padStart(2, "0")}`;
}

function statusPill(status) {
  const s = status || "";
  if (s === "completed") return `<span class="pill pillOk">completed</span>`;
  if (s === "failed") return `<span class="pill pillBad">failed</span>`;
  if (s === "downloading") return `<span class="pill">downloading</span>`;
  return `<span class="pill">pending</span>`;
}

async function api(path, opts = {}) {
  // Use API_URL prefix for all API calls
  const fullPath = `${API_URL}${path}`;
  
  const res = await fetch(fullPath, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  const isJson = (res.headers.get("content-type") || "").includes("application/json");
  const data = isJson ? await res.json() : await res.text();
  if (!res.ok) {
    const detail = data && data.detail ? data.detail : data;
    throw new Error(detail || `Request failed (${res.status})`);
  }
  return data;
}

function fillOptions(analyzeData) {
  qualitySelect.innerHTML = "";
  const opts = (analyzeData && analyzeData.options) || [];
  if (!opts.length) {
    const fallback = document.createElement("option");
    fallback.value = "auto";
    fallback.textContent = "Auto (best available)";
    fallback.dataset.formatSelector = "";
    qualitySelect.appendChild(fallback);
  }

  for (const o of opts) {
    const opt = document.createElement("option");
    opt.value = o.quality || o.type || "auto";
    opt.textContent = o.label || opt.value;
    opt.dataset.formatSelector = o.formatSelector || "";
    qualitySelect.appendChild(opt);
  }
  qualitySelect.disabled = false;
  downloadBtn.disabled = false;
}

function setActiveTab(tab) {
  const isVideo = tab === "video";
  tabVideo.classList.toggle("tabActive", isVideo);
  tabAudio.classList.toggle("tabActive", !isVideo);
  optionsVideo.classList.toggle("hidden", !isVideo);
  optionsAudio.classList.toggle("hidden", isVideo);
}

function optionRowHtml(o, kind) {
  const size = o.filesize || (typeof o.filesize_bytes === "number" ? fmtBytes(o.filesize_bytes) : "");
  const leftTitle = o.quality && o.quality !== "audio" ? `${o.quality}` : (o.label || "audio");

  const metaParts = [];
  if (kind === "video") {
    if (o.ext) metaParts.push(String(o.ext).toUpperCase());
    if (o.fps) metaParts.push(`${o.fps}fps`);
  } else {
    if (o.ext) metaParts.push(String(o.ext).toUpperCase());
    if (o.abr) metaParts.push(`${o.abr}kbps`);
  }
  if (size) metaParts.push(size);

  const meta = metaParts.join(" • ");
  const label = o.label || leftTitle;
  const formatSelector = o.formatSelector || "";

  return `
    <div class="optionRow">
      <div>
        <div class="optionTitle">${label}</div>
        <div class="optionMeta">${meta}</div>
      </div>
      <button class="smallBtn" type="button"
        data-download-selector="${encodeURIComponent(formatSelector)}"
        data-download-quality="${encodeURIComponent(o.quality || kind)}"
        data-download-output="${encodeURIComponent(kind === 'audio' ? 'mp3' : 'mp4')}">
        Download
      </button>
    </div>
  `;
}

function renderOptions(analyzeData) {
  const isPlaylist = !!(analyzeData && analyzeData.is_playlist);
  const v = (analyzeData && analyzeData.video_options) || [];
  const a = (analyzeData && analyzeData.audio_options) || [];

  if (isPlaylist) {
    // Hide quality tabs for playlist; show playlist items instead.
    tabVideo.classList.add("hidden");
    tabAudio.classList.add("hidden");
    optionsVideo.classList.add("hidden");
    optionsAudio.classList.add("hidden");

    const items = analyzeData.items || [];
    if (!items.length) {
      playlistList.innerHTML = `<div class="meta">No videos found in playlist.</div>`;
    } else {
      playlistList.innerHTML = items
        .map((it) => {
          const dur = it.duration_seconds ? fmtDuration(it.duration_seconds) : "";
          const idx = it.index || "";
          const meta = [idx ? `#${idx}` : "", dur].filter(Boolean).join(" • ");
          const safeTitle = (it.title || "").replace(/</g, "&lt;").replace(/>/g, "&gt;");
          const urlEnc = encodeURIComponent(it.url);
          return `
            <div class="playlistItem" data-pl-url="${urlEnc}">
              <div class="playlistInfo">
                <div class="playlistTitle">${safeTitle}</div>
                <div class="playlistMeta">${meta}</div>
              </div>
              <div class="actionRow">
                <button class="smallBtn" type="button" data-pl-dl="${urlEnc}" data-pl-output="mp4">MP4</button>
                <button class="smallBtn" type="button" data-pl-dl="${urlEnc}" data-pl-output="mp3">MP3</button>
              </div>
            </div>
          `;
        })
        .join("");
    }
    playlistList.classList.remove("hidden");
    return;
  }

  // Single video: show tabs and options.
  playlistList.classList.add("hidden");
  tabVideo.classList.remove("hidden");
  tabAudio.classList.remove("hidden");

  optionsVideo.innerHTML = v.length
    ? v.map((o) => optionRowHtml(o, "video")).join("")
    : `<div class="meta">No video formats found.</div>`;

  optionsAudio.innerHTML = a.length
    ? a.map((o) => optionRowHtml(o, "audio")).join("")
    : `<div class="meta">No audio formats found.</div>`;
}

async function analyze() {
  clearError();
  const url = (urlInput.value || "").trim();
  if (!url) {
    showError("Paste a YouTube URL first.");
    return;
  }
  analyzeBtn.disabled = true;
  downloadBtn.disabled = true;
  qualitySelect.disabled = true;
  setStatus("Analyzing...");
  try {
    const data = await api("/api/analyze", {
      method: "POST",
      body: JSON.stringify({ url }),
    });
    lastAnalyzed = data;
    // Preview
    if (data.thumbnail_url) {
      thumb.src = data.thumbnail_url;
      thumb.classList.remove("hidden");
    } else {
      thumb.removeAttribute("src");
    }
    previewTitle.textContent = data.title || "";
    const dur = fmtDuration(data.duration_seconds);
    previewMeta.textContent = [data.video_id ? `ID: ${data.video_id}` : "", dur ? `Duration: ${dur}` : ""]
      .filter(Boolean)
      .join(" • ");
    preview.classList.remove("hidden");

    renderOptions(data);
    if (!data.is_playlist) {
      setActiveTab("video");
      // keep legacy select filled (hidden)
      fillOptions(data);
    } else {
      setStatus("Playlist detected. Choose a video to download.");
    }
    setStatus("Ready.");
  } catch (e) {
    showError(e.message || String(e));
    setStatus("");
  } finally {
    analyzeBtn.disabled = false;
  }
}

function calcProgressText(item) {
  const pct =
    typeof item.progress_percent === "number" ? Math.max(0, Math.min(100, item.progress_percent)) : null;
  const dl = fmtBytes(item.downloaded_bytes);
  const tt = fmtBytes(item.total_bytes);
  if (pct != null) return `${pct.toFixed(1)}%${dl && tt ? ` (${dl}/${tt})` : ""}`;
  if (dl && tt) return `${dl}/${tt}`;
  return "";
}

async function createDownload() {
  clearError();
  const url = (urlInput.value || "").trim();
  if (!url) {
    showError("Paste a YouTube URL first.");
    return;
  }
  const qs = new URLSearchParams({ url });
  const downloadUrl = `${API_URL}/direct-download?${qs.toString()}`;
  window.open(downloadUrl, "_blank", "noopener");
  setStatus("Download started in browser.");
}

async function createDownloadWithSelector(formatSelector, preferredQuality, output) {
  clearError();
  const url = (urlInput.value || "").trim();
  if (!url) {
    showError("Paste a YouTube URL first.");
    return;
  }
  const params = new URLSearchParams();
  params.set("url", url);
  if (formatSelector) params.set("formatSelector", formatSelector);
  if (output) params.set("output", output);
  const href = `${API_URL}/direct-download?${params.toString()}`;
  window.open(href, "_blank", "noopener");
  setStatus("Download started in browser.");
}

function rowHtml(item) {
  const progress = calcProgressText(item);
  const titleSafe = (item.title || "").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const status = item.status;

  // Only show a Download button once the file is ready.
  const dlPart =
    item.download_url && status === "completed"
      ? `<a class="linkBtn" href="${item.download_url}" target="_blank" rel="noreferrer">Download</a>`
      : "";

  // While downloading/pending/paused/failed we allow pause/resume/cancel.
  let pauseBtn = "";
  let resumeBtn = "";
  let cancelBtn = "";

  if (status === "pending" || status === "downloading") {
    pauseBtn = `<button class="linkBtn" type="button" data-pause="${item.id}">Pause</button>`;
    cancelBtn = `<button class="linkBtn linkBtnDanger" type="button" data-cancel="${item.id}">Cancel</button>`;
  } else if (status === "paused") {
    resumeBtn = `<button class="linkBtn" type="button" data-resume="${item.id}">Resume</button>`;
    cancelBtn = `<button class="linkBtn linkBtnDanger" type="button" data-cancel="${item.id}">Cancel</button>`;
  } else if (status === "failed") {
    // Allow retry via Resume on failed items.
    resumeBtn = `<button class="linkBtn" type="button" data-resume="${item.id}">Retry</button>`;
  }
  // When completed or cancelled, we hide pause/resume/cancel buttons (only keep Download/Save/Delete).
  if (status === "completed" || status === "cancelled") {
    pauseBtn = "";
    resumeBtn = "";
    cancelBtn = "";
  }

  const editBox = `<input class="inlineInput" value="${titleSafe}" data-edit-title="${item.id}" placeholder="(optional) title" />`;
  const delBtn = `<button class="linkBtn linkBtnDanger" type="button" data-delete="${item.id}">Delete</button>`;

  return `
    <tr data-id="${item.id}">
      <td>
        <div style="min-width: 260px;">
          ${editBox}
        </div>
      </td>
      <td>${item.quality_label || "auto"}</td>
      <td>${statusPill(item.status)}</td>
      <td>${progress}</td>
      <td>${fmtDate(item.created_at)}</td>
      <td>
        <div class="actionRow">
          ${dlPart}
          ${pauseBtn}
          ${resumeBtn}
          ${cancelBtn}
          ${delBtn}
        </div>
      </td>
    </tr>
  `;
}

function updateCurrentStatus(item) {
  if (!item) return;
  const pct =
    typeof item.progress_percent === "number" ? Math.max(0, Math.min(100, item.progress_percent)) : null;
  const progress = calcProgressText(item);
  const status = item.status;

  // Build a small animated-looking progress bar.
  const barWidth = pct != null ? `${pct}%` : "0%";
  let barHtml = `
    <div class="progressBar">
      <div class="progressFill" style="width: ${barWidth};"></div>
    </div>
    <div class="progressText">${progress || ""}</div>
  `;

  if (status === "completed" && item.download_url) {
    statusLine.innerHTML = `
      <div>Completed.</div>
      ${barHtml}
      <button class="linkBtn" type="button" data-current-save="1">Save to device</button>
    `;
    statusLine.dataset.downloadUrl = item.download_url;
  } else if (status === "failed") {
    statusLine.innerHTML = `<div>Failed: ${item.error_message || "unknown error"}</div>`;
  } else if (status === "paused") {
    statusLine.innerHTML = `
      <div>Paused.</div>
      ${barHtml}
    `;
  } else if (status === "cancelled") {
    statusLine.innerHTML = `<div>Cancelled.</div>`;
  } else {
    statusLine.innerHTML = `
      <div>Downloading...</div>
      ${barHtml}
    `;
  }
}

async function pollCurrentOnce() {
  if (!currentDownloadId) return;
  try {
    const item = await api(`/api/downloads/${currentDownloadId}`);
    updateCurrentStatus(item);
    if (item.status === "completed" || item.status === "failed" || item.status === "cancelled") {
      stopPollingCurrent();
    }
  } catch (e) {
    // ignore transient errors
  }
}

function startPollingCurrent() {
  if (pollTimer) return;
  pollTimer = setInterval(pollCurrentOnce, 2000);
}

function stopPollingCurrent() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

analyzeBtn.addEventListener("click", analyze);
downloadBtn.addEventListener("click", createDownload);

tabVideo.addEventListener("click", () => setActiveTab("video"));
tabAudio.addEventListener("click", () => setActiveTab("audio"));

function handleOptionClick(e) {
  const t = e.target;
  if (!t) return;
  const sel = t.getAttribute("data-download-selector");
  const q = t.getAttribute("data-download-quality");
  const out = t.getAttribute("data-download-output");
  if (!sel) return;
  const formatSelector = decodeURIComponent(sel);
  const preferredQuality = q ? decodeURIComponent(q) : null;
  const output = out ? decodeURIComponent(out) : null;
  createDownloadWithSelector(formatSelector, preferredQuality, output);
}

optionsVideo.addEventListener("click", handleOptionClick);
optionsAudio.addEventListener("click", handleOptionClick);

playlistList.addEventListener("click", (e) => {
  const t = e.target;
  if (!t) return;
  const pl = t.getAttribute("data-pl-dl");
  const out = t.getAttribute("data-pl-output") || "mp4";
  if (!pl) return;
  const url = decodeURIComponent(pl);
  const params = new URLSearchParams();
  params.set("url", url);
  params.set("output", out);
  const href = `${API_URL}/direct-download?${params.toString()}`;
  window.open(href, "_blank", "noopener");
  setStatus("Playlist item download started in browser.");
});

urlInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") analyze();
});

(async function init() {
  // If there was a download in progress when the page was last open,
  // you could restore it here by reading from localStorage and polling again.
  // For now we start clean on each load.
})();

statusLine.addEventListener("click", (e) => {
  const t = e.target;
  if (!t) return;
  if (t.getAttribute("data-current-save") === "1") {
    const url = statusLine.dataset.downloadUrl;
    if (url) {
      window.open(url, "_blank", "noopener");
    }
    // After user triggers save, clear the UI.
    statusLine.innerHTML = "";
  }
});

