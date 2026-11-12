// compare.js — Raw / Low-freq display mode, Noisy ⇄ Clean volume pair, and side-by-side compare view (scope S2).
// Loaded after sgy-client.js and sam-client.js; uses their globals (volInfo, curDir, curIndex, sliceMode,
// compareMode, fetchSlice, loadAndRenderSlice, applyVolumeInfo, estimateClip, scaleX/scaleY, userGainFactor).

const CLEAN_SUFFIX = '_clean';
const compareCanvas = document.getElementById('compareCanvas');
const compareCtx = compareCanvas ? compareCanvas.getContext('2d') : null;
let compareToken = 0;   // drops responses for a slice the user has already left

function availableVolumes() {
    const sel = document.getElementById('volumeSelect');
    return sel ? [...sel.options].map(o => o.value).filter(Boolean) : [];
}

// The other member of a noisy / clean pair, or null. Pairs are `<name>` and `<name>_clean`.
function pairedVolumeName(name) {
    if (!name) return null;
    const vols = availableVolumes();
    const other = name.endsWith(CLEAN_SUFFIX) ? name.slice(0, -CLEAN_SUFFIX.length) : name + CLEAN_SUFFIX;
    return vols.includes(other) ? other : null;
}

function isCleanVolume(name) { return !!name && name.endsWith(CLEAN_SUFFIX); }

function panelLabel(volName, mode) {
    const noise = isCleanVolume(volName) ? 'Clean' : (pairedVolumeName(volName) ? 'Noisy' : '');
    return [mode === 'lowfreq' ? 'Low-freq' : 'Raw', noise, volName].filter(Boolean).join(' · ');
}

// What the right-hand panel shows for the current compare mode, or null.
function compareTarget() {
    if (compareMode === 'lowfreq') return { vol: volInfo.name, mode: sliceMode === 'raw' ? 'lowfreq' : 'raw' };
    if (compareMode === 'noise') {
        const other = pairedVolumeName(volInfo.name);
        return other ? { vol: other, mode: sliceMode } : null;
    }
    return null;
}

// ── Canvas sizing: main canvas alone, or main + compare side by side ──────────
function sizeSectionCanvases() {
    const on = compareMode !== 'off' && !!compareTarget();
    const ws = document.querySelector('.workspace');
    compareCanvas.style.display = on ? 'block' : 'none';
    ws.classList.toggle('comparing', on);
    const total = ws.clientWidth, h = ws.clientHeight;
    const mainW = on ? Math.floor(total / 2) : total;
    canvas.width = mainW; canvas.height = h;
    canvas.style.width = mainW + 'px';
    if (on) {
        compareCanvas.width = total - mainW; compareCanvas.height = h;
        compareCanvas.style.width = (total - mainW) + 'px';
    }
}

function renderCompareSlice(data, rows, cols) {
    const w = compareCanvas.width, h = compareCanvas.height;
    if (!w || !h) return;
    const clip = (estimateClip(data) || 1.0) * userGainFactor;   // own auto gain, same user gain offset as the main panel
    const off = document.createElement('canvas');
    off.width = w; off.height = h;
    const octx = off.getContext('2d');
    const id = octx.createImageData(w, h);
    const px = id.data;
    for (let y = 0; y < h; y++) {
        const fy = y / h * (rows - 1), sy0 = Math.floor(fy), sy1 = Math.min(rows - 1, sy0 + 1), dy = fy - sy0;
        for (let x = 0; x < w; x++) {
            const fx = x / w * (cols - 1), sx0 = Math.floor(fx), sx1 = Math.min(cols - 1, sx0 + 1), dx = fx - sx0;
            const v = (data[sy0 * cols + sx0] * (1 - dx) * (1 - dy) + data[sy0 * cols + sx1] * dx * (1 - dy) +
                       data[sy1 * cols + sx0] * (1 - dx) * dy + data[sy1 * cols + sx1] * dx * dy) / clip;
            const t = Math.max(-1, Math.min(1, v));
            const o = (y * w + x) * 4;
            if (t >= 0) { px[o] = 255; px[o + 1] = Math.floor(255 * (1 - t)); px[o + 2] = Math.floor(255 * (1 - t)); }
            else { px[o] = Math.floor(255 * (1 + t)); px[o + 1] = Math.floor(255 * (1 + t)); px[o + 2] = 255; }
            px[o + 3] = 255;
        }
    }
    octx.putImageData(id, 0, 0);
    compareCtx.clearRect(0, 0, w, h);
    compareCtx.save();                                   // same zoom as the main panel (drawSeismic)
    compareCtx.translate(w / 2, h / 2);
    compareCtx.scale(scaleX, scaleY);
    compareCtx.translate(-w / 2, -h / 2);
    compareCtx.drawImage(off, 0, 0, w, h);
    compareCtx.restore();
}

async function updateCompareView() {
    const mainTag = document.getElementById('mainPanelTag');
    const cmpTag = document.getElementById('comparePanelTag');
    if (mainTag) mainTag.textContent = volInfo.name ? panelLabel(volInfo.name, sliceMode) : '';
    const target = compareTarget();
    if (!target || !compareCanvas) { if (cmpTag) cmpTag.style.display = 'none'; return; }
    cmpTag.style.display = 'block';
    cmpTag.textContent = panelLabel(target.vol, target.mode);
    const token = ++compareToken;
    try {
        const payload = await fetchSlice('api/npy', target.vol, curDir, curIndex, target.mode);
        if (token !== compareToken) return;
        renderCompareSlice(payload.data, payload.shape[0], payload.shape[1]);
    } catch (e) {
        if (token !== compareToken) return;
        compareCtx.clearRect(0, 0, compareCanvas.width, compareCanvas.height);
        cmpTag.textContent += ` — failed to load (${e.message})`;
    }
}

// Duplicate the top-axis ticks over the compare panel (both panels show the same slice position).
function compareAdjustAxes() {
    if (compareMode === 'off' || !compareTarget()) return;
    const topAxis = document.getElementById('topAxis');
    [...topAxis.children].forEach(div => {
        const pct = parseFloat(div.style.left);
        if (Number.isNaN(pct)) return;
        div.style.left = (pct / 2) + '%';
        const twin = div.cloneNode(true);
        twin.style.left = (50 + pct / 2) + '%';
        topAxis.appendChild(twin);
    });
}

// ── Controls ─────────────────────────────────────────────────────────────────
function syncCompareControls() {
    const npy = volInfo.source === 'api/npy' && !!volInfo.name;
    if (!npy && sliceMode !== 'raw') { sliceMode = 'raw'; embeddingId = null; embeddingImageSize = null; }
    const pair = npy ? pairedVolumeName(volInfo.name) : null;
    const raw = document.getElementById('btnModeRaw'), low = document.getElementById('btnModeLow');
    raw.classList.toggle('active', sliceMode === 'raw');
    low.classList.toggle('active', sliceMode === 'lowfreq');
    low.disabled = !npy;
    low.title = npy ? 'Low-frequency view: spectral weighting along time (≤14 Hz kept, ≥30 Hz attenuated). The stored volume is not changed.'
                    : 'Low-frequency view needs a NumPy volume';
    const pairBtn = document.getElementById('btnNoisePair');
    pairBtn.disabled = !pair;
    pairBtn.textContent = isCleanVolume(volInfo.name) ? 'Clean ⇄ Noisy' : 'Noisy ⇄ Clean';
    pairBtn.title = pair ? `Switch to ${pair} at the same slice` : 'No noisy / clean pair for this volume';
    const sel = document.getElementById('compareSelect');
    [...sel.options].forEach(o => {
        if (o.value === 'lowfreq') o.disabled = !npy;
        if (o.value === 'noise') o.disabled = !pair;
    });
    if ((compareMode === 'lowfreq' && !npy) || (compareMode === 'noise' && !pair)) setCompareMode('off');
    sel.value = compareMode;
}

function setSliceMode(mode) {
    if (mode === sliceMode) return;
    sliceMode = mode;
    embeddingId = null; embeddingImageSize = null;   // SAM must embed the image that is shown
    syncCompareControls();
    loadAndRenderSlice(curDir, curIndex);
}

async function switchNoisePair() {
    const target = pairedVolumeName(volInfo.name);
    if (!target) return;
    const r = await fetch(`/api/npy/${encodeURIComponent(target)}/meta`);
    if (!r.ok) { setStatus('error', `Cannot open ${target}: HTTP ${r.status}`); return; }
    applyVolumeInfo(await r.json(), target, 'api/npy');   // keeps direction, index and picks: same model, same position
    const sel = document.getElementById('volumeSelect');
    if (sel) sel.value = target;
    embeddingId = null; embeddingImageSize = null;
    if (typeof updateLineRangeLabel === 'function') updateLineRangeLabel();
    syncCompareControls();
    await loadAndRenderSlice(curDir, curIndex);
}

function setCompareMode(mode) {
    compareMode = mode;
    const sel = document.getElementById('compareSelect');
    if (sel) sel.value = mode;
    sizeSectionCanvases();
    if (currentSliceData && currentSliceShape) renderSliceToCanvas(currentSliceData, currentSliceShape[0], currentSliceShape[1]);
    drawSeismic();
    if (typeof updateAxes === 'function') updateAxes();
    updateCompareView();
}

document.getElementById('btnModeRaw').onclick = () => setSliceMode('raw');
document.getElementById('btnModeLow').onclick = () => setSliceMode('lowfreq');
document.getElementById('btnNoisePair').onclick = () => switchNoisePair();
document.getElementById('compareSelect').onchange = e => setCompareMode(e.target.value);
syncCompareControls();
