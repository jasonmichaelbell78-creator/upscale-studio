// ── State ────────────────────────────────────────────────────
let currentJobId = null;
let pollTimer = null;

// ── DOM refs ─────────────────────────────────────────────────
const $ = (sel) => document.querySelector(sel);

const dropZone         = $("#drop-zone");
const fileInput        = $("#file-input");
const uploadSection    = $("#upload-section");
const infoSection      = $("#info-section");
const settingsSection  = $("#settings-section");
const previewSection   = $("#preview-section");
const progressSection  = $("#progress-section");
const doneSection      = $("#done-section");
const errorSection     = $("#error-section");

// Save original drop zone HTML for reset
const dropZoneOriginal = dropZone.innerHTML;

// ── Helpers ──────────────────────────────────────────────────
function show(...sections) { sections.forEach(s => s.classList.remove("hidden")); }
function hide(...sections) { sections.forEach(s => s.classList.add("hidden")); }

function formatBytes(bytes) {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + " KB";
    if (bytes < 1073741824) return (bytes / 1048576).toFixed(1) + " MB";
    return (bytes / 1073741824).toFixed(2) + " GB";
}

function formatDuration(seconds) {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    if (h > 0) return `${h}h ${m}m ${s}s`;
    if (m > 0) return `${m}m ${s}s`;
    return `${s}s`;
}

function formatTime(seconds) {
    if (!seconds || seconds < 0 || !isFinite(seconds)) return "?";
    if (seconds < 60) return Math.round(seconds) + "s";
    if (seconds < 3600) return Math.floor(seconds / 60) + "m " + Math.round(seconds % 60) + "s";
    return Math.floor(seconds / 3600) + "h " + Math.floor((seconds % 3600) / 60) + "m";
}

function resetUI() {
    currentJobId = null;
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
    // Restore drop zone to original state
    dropZone.innerHTML = dropZoneOriginal;
    hide(infoSection, settingsSection, previewSection, progressSection, doneSection, errorSection);
    hide($("#upload-progress-wrap"));
    show(uploadSection);
    // Re-bind click on restored drop zone
    dropZone.addEventListener("click", dropZoneClick);
    // Re-acquire file input ref after innerHTML restore
    const newFileInput = $("#file-input");
    if (newFileInput) {
        newFileInput.addEventListener("change", fileInputChange);
    }
}

function showError(msg) {
    hide(uploadSection, infoSection, settingsSection, previewSection, progressSection, doneSection);
    $("#error-message").textContent = msg;
    show(errorSection);
}

function updateEstimate() {
    const scale = parseInt($("#scale").value);
    const info = window._videoInfo;
    if (!info) return;
    const outW = info.width * scale;
    const outH = info.height * scale;
    $("#output-estimate").textContent = `Output resolution: ${outW} x ${outH}`;

    // Fetch disk space estimate
    fetchDiskEstimate(scale);
}

async function fetchDiskEstimate(scale) {
    if (!currentJobId) return;
    try {
        const resp = await fetch(`/api/disk-space/${currentJobId}?scale=${scale}`);
        if (!resp.ok) return;
        const data = await resp.json();

        const warning = $("#disk-space-warning");
        let text = `Estimated temp disk space: ~${data.estimated_gb} GB`;
        text += ` | Available: ${data.available_gb} GB`;
        text += ` | Processing in ${data.total_chunks} chunks`;
        if (data.est_hours >= 1) {
            text += ` | Estimated time: ~${data.est_hours} hours`;
        } else {
            text += ` | Estimated time: <1 hour`;
        }

        warning.textContent = text;
        if (!data.sufficient) {
            warning.classList.add("danger");
            warning.textContent += " — WARNING: May not have enough disk space!";
        } else {
            warning.classList.remove("danger");
        }
        show(warning);
    } catch (_) {}
}

// ── Upload (drag-and-drop / browse) ─────────────────────────
function dropZoneClick() { $("#file-input").click(); }
function fileInputChange() {
    const fi = $("#file-input");
    if (fi && fi.files.length) uploadFile(fi.files[0]);
}

dropZone.addEventListener("click", dropZoneClick);
dropZone.addEventListener("keydown", (e) => { if (e.key === "Enter") dropZoneClick(); });
dropZone.addEventListener("dragover", (e) => { e.preventDefault(); dropZone.classList.add("dragover"); });
dropZone.addEventListener("dragleave", () => dropZone.classList.remove("dragover"));
dropZone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropZone.classList.remove("dragover");
    if (e.dataTransfer.files.length) uploadFile(e.dataTransfer.files[0]);
});
fileInput.addEventListener("change", fileInputChange);

async function uploadFile(file) {
    const progressWrap = $("#upload-progress-wrap");
    show(progressWrap);
    dropZone.classList.add("hidden");

    const form = new FormData();
    form.append("file", file);

    try {
        // Use XMLHttpRequest for upload progress
        const data = await new Promise((resolve, reject) => {
            const xhr = new XMLHttpRequest();
            xhr.open("POST", "/api/upload");

            xhr.upload.addEventListener("progress", (e) => {
                if (e.lengthComputable) {
                    const pct = Math.round((e.loaded / e.total) * 100);
                    $("#upload-progress-bar").style.width = pct + "%";
                    $("#upload-pct").textContent = pct + "%";
                    $("#upload-label").textContent = `Uploading... ${formatBytes(e.loaded)} / ${formatBytes(e.total)}`;
                }
            });

            xhr.addEventListener("load", () => {
                if (xhr.status >= 200 && xhr.status < 300) {
                    resolve(JSON.parse(xhr.responseText));
                } else {
                    try {
                        const err = JSON.parse(xhr.responseText);
                        reject(new Error(err.detail || "Upload failed"));
                    } catch (_) {
                        reject(new Error("Upload failed (HTTP " + xhr.status + ")"));
                    }
                }
            });

            xhr.addEventListener("error", () => reject(new Error("Network error during upload")));
            xhr.addEventListener("abort", () => reject(new Error("Upload cancelled")));
            xhr.send(form);
        });

        onVideoLoaded(data);
    } catch (err) {
        showError(err.message);
    }
}

// ── Select local file by path ────────────────────────────────
$("#btn-select-file").addEventListener("click", async () => {
    const pathInput = $("#file-path-input");
    const filePath = pathInput.value.trim();
    if (!filePath) return;

    const btn = $("#btn-select-file");
    btn.disabled = true;
    btn.textContent = "Loading...";

    const form = new FormData();
    form.append("path", filePath);

    try {
        const resp = await fetch("/api/select-file", { method: "POST", body: form });
        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.detail || "Failed to open file");
        }
        const data = await resp.json();
        onVideoLoaded(data);
    } catch (err) {
        showError(err.message);
    } finally {
        btn.disabled = false;
        btn.textContent = "Open";
    }
});

// Also allow Enter key in the path input
$("#file-path-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") $("#btn-select-file").click();
});

// ── Shared: after upload or file select ──────────────────────
function onVideoLoaded(data) {
    currentJobId = data.job_id;
    const info = data.video_info;
    window._videoInfo = info;

    $("#info-filename").textContent = data.filename;
    $("#info-resolution").textContent = `${info.width} x ${info.height}`;
    $("#info-duration").textContent = formatDuration(info.duration);
    $("#info-fps").textContent = info.fps;
    $("#info-size").textContent = formatBytes(info.size_bytes);
    $("#info-frames").textContent = info.total_frames.toLocaleString();
    updateEstimate();

    hide(uploadSection);
    show(infoSection, settingsSection);
}

// ── Settings change → update estimate ────────────────────────
$("#scale").addEventListener("change", updateEstimate);

// ── Preview ──────────────────────────────────────────────────
$("#btn-preview").addEventListener("click", async () => {
    const btn = $("#btn-preview");
    btn.disabled = true;
    btn.textContent = "Generating...";

    show(previewSection);
    $("#preview-loading").classList.remove("hidden");
    $("#preview-container").classList.add("hidden");

    const form = new FormData();
    form.append("job_id", currentJobId);
    form.append("scale", $("#scale").value);
    form.append("model", $("#model").value);
    form.append("tile_size", $("#tile-size").value);

    try {
        const resp = await fetch("/api/preview", { method: "POST", body: form });
        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.detail || "Preview failed");
        }
        const data = await resp.json();

        const ts = Date.now();
        $("#preview-original").src = data.original_url + "?t=" + ts;
        $("#preview-upscaled").src = data.upscaled_url + "?t=" + ts;
        $("#preview-original-res").textContent = `(${data.original_res})`;
        $("#preview-upscaled-res").textContent = `(${data.upscaled_res})`;

        $("#preview-loading").classList.add("hidden");
        $("#preview-container").classList.remove("hidden");
    } catch (err) {
        showError(err.message);
    } finally {
        btn.disabled = false;
        btn.textContent = "Preview Frame";
    }
});

// ── Upscale ──────────────────────────────────────────────────
$("#btn-upscale").addEventListener("click", async () => {
    const form = new FormData();
    form.append("job_id", currentJobId);
    form.append("scale", $("#scale").value);
    form.append("model", $("#model").value);
    form.append("codec", $("#codec").value);
    form.append("tile_size", $("#tile-size").value);

    try {
        const resp = await fetch("/api/upscale", { method: "POST", body: form });
        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.detail || "Failed to start upscale");
        }

        hide(settingsSection, previewSection, doneSection, errorSection);
        show(progressSection);
        startPolling();
    } catch (err) {
        showError(err.message);
    }
});

// ── Progress Polling ─────────────────────────────────────────
function startPolling() {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(pollStatus, 1000);
    pollStatus();
}

async function pollStatus() {
    if (!currentJobId) return;

    try {
        const resp = await fetch(`/api/status/${currentJobId}`);
        if (!resp.ok) return;
        const data = await resp.json();

        $("#phase-label").textContent = data.phase;

        const pct = data.total_frames > 0
            ? Math.round((data.current_frame / data.total_frames) * 100)
            : 0;

        // During reassembly/encoding, clamp display percentage
        let displayPct = pct;
        if (data.status === "reassembling") displayPct = Math.max(pct, 95);
        if (data.status === "encoding") displayPct = Math.min(pct, 98);

        $("#progress-bar").style.width = Math.min(displayPct, 100) + "%";
        $("#stat-frames").textContent = `${data.current_frame.toLocaleString()} / ${data.total_frames.toLocaleString()} frames`;
        $("#stat-percent").textContent = displayPct + "%";
        $("#stat-elapsed").textContent = "Elapsed: " + formatTime(data.elapsed);

        // ETA based on upscaling-phase-only timing for accuracy
        if (data.current_frame > 0 && data.total_frames > 0 &&
            (data.status === "upscaling" || data.status === "extracting" || data.status === "encoding")) {
            const upscaleRate = data.upscale_elapsed > 0 ? data.current_frame / data.upscale_elapsed : 0;
            if (upscaleRate > 0) {
                const remaining = (data.total_frames - data.current_frame) / upscaleRate;
                $("#stat-eta").textContent = "ETA: ~" + formatTime(remaining);
            } else {
                $("#stat-eta").textContent = "ETA: calculating...";
            }
        } else if (data.status === "reassembling") {
            $("#stat-eta").textContent = "ETA: finalizing...";
        } else {
            $("#stat-eta").textContent = "ETA: calculating...";
        }

        // Show chunk info
        const chunkEl = $("#stat-chunk");
        if (data.total_chunks > 1) {
            chunkEl.textContent = `Chunk ${data.current_chunk} / ${data.total_chunks}`;
        } else {
            chunkEl.textContent = "";
        }

        if (data.status === "done") {
            clearInterval(pollTimer);
            pollTimer = null;
            hide(progressSection);
            $("#done-message").textContent = `Finished in ${formatTime(data.elapsed)}. Your upscaled video is ready.`;
            show(doneSection);
        } else if (data.status === "error") {
            clearInterval(pollTimer);
            pollTimer = null;
            showError(data.error || "An unknown error occurred during processing.");
        } else if (data.status === "cancelled") {
            clearInterval(pollTimer);
            pollTimer = null;
            hide(progressSection);
            show(settingsSection);
        }
    } catch (err) {
        // Network error — keep polling
    }
}

// ── Cancel ───────────────────────────────────────────────────
$("#btn-cancel").addEventListener("click", async () => {
    if (!currentJobId) return;
    try {
        await fetch(`/api/cancel/${currentJobId}`, { method: "POST" });
    } catch (_) {}
});

// ── Download ─────────────────────────────────────────────────
$("#btn-download").addEventListener("click", () => {
    if (currentJobId) {
        window.location.href = `/api/download/${currentJobId}`;
    }
});

// ── New Job ──────────────────────────────────────────────────
$("#btn-new").addEventListener("click", () => resetUI());
$("#btn-retry").addEventListener("click", () => resetUI());
