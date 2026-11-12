/**
 * app.js - shared globals and lightweight UI bindings.
 * Load order (index.html): storage.js -> canvas.js -> app.js
 *   -> sgy-client.js -> sam-client.js -> llm-client.js
 */

let volInfo = {
    name: null,
    ilCount: 0,
    xlCount: 0,
    tsCount: 0,
    ilMin: 0,
    ilMax: 0,
    xlMin: 0,
    xlMax: 0,
    tsMin: 0,
    tsMax: 0,
    source: null,
};
let COORD = { crossMin: 0, crossMax: 0, yTop: 0, yRange: 0, yLabel: 'Time (ms)' };
let curDir = 'inline';
let curIndex = 0;
let displayMode = 'vd'; // 'vd' = seismic color, 'wv' = wiggle
let yAxisUnit = 'time';
let velocity = 3000;
let samEnabled = true;
let logitsMode = true;
let pickMode = 'exclude';
let isInferring = false;
let embeddingId = null;
let embeddingImageSize = null;  // [w, h] of the image behind embeddingId
let sliceMode = 'raw';          // 'raw' | 'lowfreq' — which version of the slice is shown (and embedded for SAM)
let compareMode = 'off';        // 'off' | 'lowfreq' (raw vs low-freq) | 'noise' (noisy vs clean pair)
let logitsMap = null;
let logitsWidth = 0;
let logitsHeight = 0;
let currentSessionId = null;

const SLICE_CACHE_SIZE = 20;
let sliceCache = new Map();
let embCache = new Map();

let currentSliceData = null;
let currentSliceShape = null;
let currentClip = 1.0;
let seismicImageData = null;

// Zoom factors: 1.0 = original scale, >1 zoom in, <1 zoom out
let scaleY = 1.0;  // vertical zoom
let scaleX = 1.0;  // horizontal zoom

let loopEnabled = true;
let fps = 4;
let playTimer = null;
let isLoading = false;
let pendingIdx = null;

let picksBySlice = new Map();
let activePicks = [];

let timeRange = { min: 0, max: 1000 };
let depthRange = { min: 0, max: 500 };

const canvas = document.getElementById('seismicCanvas');
const ctx = canvas.getContext('2d');
const infoBox = document.getElementById('infoBox');
const btnLoadSGY = document.getElementById('btnLoadSGY');
const btnGenSlices = document.getElementById('btnGenSlices');
const btnLoadImage = document.getElementById('btnLoadImage');
const btnFirst = document.getElementById('btnFirst');
const btnPrev10 = document.getElementById('btnPrev10');
const btnPrev = document.getElementById('btnPrev');
const btnPlay = document.getElementById('btnPlay');
const btnNext = document.getElementById('btnNext');
const btnNext10 = document.getElementById('btnNext10');
const btnLast = document.getElementById('btnLast');
const loopCb = document.getElementById('loopCb');
const fpsInput = document.getElementById('fpsInput');
const dirSelect = document.getElementById('dirSelect');
const lineNo = document.getElementById('lineNo');
const btnGoLine = document.getElementById('btnGoLine');
const yUnitSelect = document.getElementById('yUnitSelect');
const velocityInput = document.getElementById('velocityInput');
const btnApplyVelocity = document.getElementById('btnApplyVelocity');
const selDisplayMode = document.getElementById('displayMode');
const cbSamMode = document.getElementById('samMode');
const cbLogitsMode = document.getElementById('logitsMode');
const deviceSelect = document.getElementById('deviceSelect');
const btnInclude = document.getElementById('btnInclude');
const btnExclude = document.getElementById('btnExclude');
const btnDelPoints = document.getElementById('btnDelPoints');
const btnClearMask = document.getElementById('btnClearMask');
const btnRunSAM = document.getElementById('btnRunSAM');
const btnExportMask = document.getElementById('btnExportMask');
const btnExport = document.getElementById('btnExport');
const btnImportCSV = document.getElementById('btnImportCSV');
const btnSave = document.getElementById('btnSave');
const btnRestore = document.getElementById('btnRestore');
const btnReset = document.getElementById('btnReset');
const sgyFileInput = document.getElementById('sgyFileInput');
const imageFileInput = document.getElementById('imageFileInput');
const csvFileInput = document.getElementById('csvFileInput');
const slicePanel = document.getElementById('slicePanel');
const lineSlider = document.getElementById('lineSlider');
const slicePosLabel = document.getElementById('slicePosLabel');
const sliceLineNo = document.getElementById('sliceLineNo');
const lineRangeLabel = document.getElementById('lineRangeLabel');
const plotSubtitle = document.getElementById('plotSubtitle');
const yAxisLabel = document.getElementById('yAxisLabel');
const statusIndicator = document.getElementById('statusIndicator');
const statusText = document.getElementById('statusText');
const backupStatus = document.getElementById('backupStatus');

function setStatus(type, msg) {
    statusIndicator.className = 'status-' + type;
    statusText.textContent = msg;
}

// Plain-English error text for the status bar (scope S7 / E3)
function errText(e) {
    const m = (e && e.message) || String(e);
    if (e instanceof TypeError && /fetch|network/i.test(m))
        return `server not reachable at ${location.origin}. Start it with: python src/server.py`;
    return m;
}

// Error from a non-OK fetch response; works when the body is not JSON (e.g. a proxy page)
async function respError(resp) {
    let msg = `HTTP ${resp.status}`;
    try { const j = await resp.json(); if (j && j.detail) msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail); }
    catch (_) { /* not JSON */ }
    return new Error(msg);
}
// SAM3 state badge (scope S7). samState is read by the SAM paths to show a CPU encoding notice.
let samState = { weights: true, device: 'cuda' };
function updateSamBadge(s) {
    const el = document.getElementById('samBadge');
    samState = { weights: !!s.weights_exists, device: s.sam_device || (s.gpu_available ? 'cuda' : 'cpu') };
    if (!el) return;
    if (!s.weights_exists) {
        el.className = 'sam-badge missing';
        el.textContent = 'SAM3: weights missing';
        el.title = `Download sam3.pt from ${s.weights_source} (request access, Meta SAM License), ` +
                   `place it at ${s.weights_path} and restart the server. See README, Run it, step 4.`;
    } else if (samState.device === 'cpu') {
        el.className = 'sam-badge cpu';
        el.textContent = 'SAM3: CPU';
        el.title = 'No GPU in use: each new slice takes about 15 s to encode.';
    } else {
        el.className = 'sam-badge gpu';
        el.textContent = 'SAM3: GPU';
        el.title = s.gpu_name || 'CUDA GPU';
    }
}

// Status text while a slice is encoded for SAM
function encodingStatus() {
    return samState.device === 'cpu' ? 'Encoding slice on CPU (about 15 s)...' : 'Encoding slice for SAM...';
}

function updateModeButtons() {
    btnInclude.classList.toggle('active', pickMode === 'include');
    btnExclude.classList.toggle('active', pickMode === 'exclude');
}

function currentSliceKey() {
    return `${curDir}:${curIndex}`;
}

async function loadDeviceList() {
    try {
        const resp = await fetch('/api/devices');
        if (!resp.ok) return;
        const data = await resp.json();
        deviceSelect.innerHTML = '';
        (data.devices || []).forEach(device => {
            const opt = document.createElement('option');
            opt.value = device.id;
            opt.textContent = device.name + (device.id === data.selected ? ' (Current)' : '');
            if (device.id === data.selected) opt.selected = true;
            deviceSelect.appendChild(opt);
        });
    } catch (err) {
        console.warn('Failed to load device list:', err);
    }
}

if (selDisplayMode) {
    selDisplayMode.onchange = e => {
        const newMode = e.target.value;
        // Wiggle display is not supported on time slices
        if (newMode === 'wv' && curDir === 'timeslice') {
            e.target.value = 'vd';
            setStatus('ready', 'Wiggle is not available for time slices; kept Seismic Color');
            return;
        }
        displayMode = newMode;
        if (currentSliceData && currentSliceShape) {
            renderSliceToCanvas(currentSliceData, currentSliceShape[0], currentSliceShape[1]);
        }
        drawSeismic();
    };
}

if (cbSamMode) {
    cbSamMode.onchange = e => {
        samEnabled = e.target.checked;
    };
}

if (cbLogitsMode) {
    cbLogitsMode.onchange = e => {
        logitsMode = e.target.checked;
        drawSeismic();
    };
}

if (btnInclude) {
    btnInclude.onclick = () => {
        pickMode = 'include';
        updateModeButtons();
    };
}

if (btnExclude) {
    btnExclude.onclick = () => {
        pickMode = 'exclude';
        updateModeButtons();
    };
}

if (btnRunSAM) btnRunSAM.onclick = () => runSAMInference();
if (btnExportMask) btnExportMask.onclick = () => exportMaskAsContour();
if (btnValidate) btnValidate.onclick = () => validateSegmentation();

// Gain up / gain down buttons
const btnGainUp = document.getElementById('btnGainUp');
const btnGainDown = document.getElementById('btnGainDown');
if (btnGainUp) btnGainUp.onclick = () => adjustGain('up');
if (btnGainDown) btnGainDown.onclick = () => adjustGain('down');

// Zoom buttons
const btnScaleYUp = document.getElementById('btnScaleYUp');
const btnScaleYDown = document.getElementById('btnScaleYDown');
const btnScaleXUp = document.getElementById('btnScaleXUp');
const btnScaleXDown = document.getElementById('btnScaleXDown');
if (btnScaleYUp) btnScaleYUp.onclick = () => adjustScale('y', 'up');
if (btnScaleYDown) btnScaleYDown.onclick = () => adjustScale('y', 'down');
if (btnScaleXUp) btnScaleXUp.onclick = () => adjustScale('x', 'up');
if (btnScaleXDown) btnScaleXDown.onclick = () => adjustScale('x', 'down');

const btnFitWindow = document.getElementById('btnFitWindow');
if (btnFitWindow) btnFitWindow.onclick = () => fitToWindow();

// Save button: save picks to localStorage
if (btnSave) {
    btnSave.onclick = () => {
        const total = [...picksBySlice.values()].reduce((s, a) => s + a.length, 0);
        if (total === 0) { setStatus('ready', 'No picks to save'); return; }
        saveToLocalStorage();
        setStatus('ready', `Saved ${total} picks in this browser`);
    };
}

// Restore button: restore picks from localStorage
if (btnRestore) {
    btnRestore.onclick = () => {
        const backup = checkForBackup();
        if (!backup) {
            alert('No saved picks found in this browser.');
            return;
        }
        showRecoveryDialog(backup);
    };
}

// Reset button: back to the initial state
if (btnReset) {
    btnReset.onclick = () => {
        if (!confirm('Reset everything? This clears all picks and caches.')) return;

        // Stop playback
        if (playTimer) { clearInterval(playTimer); playTimer = null; }

        // Clear picks and mask
        picksBySlice.clear();
        logitsMap = null; logitsWidth = 0; logitsHeight = 0;
        embeddingId = null; embeddingImageSize = null;
        currentSessionId = null;
        clearBackup();

        // Clear caches
        sliceCache.clear();
        embCache.clear();

        // Reset state variables
        curDir = 'inline';
        curIndex = 0;
        yAxisUnit = 'time';
        velocity = 3000;
        loopEnabled = true;
        fps = 4;
        pickMode = 'exclude';
        userGainFactor = 1.0;  // reset gain offset
        scaleY = 1.0;
        scaleX = 1.0;

        // Sync UI controls
        if (dirSelect) dirSelect.value = 'inline';
        if (yUnitSelect) yUnitSelect.value = 'time';
        if (velocityInput) velocityInput.value = 3000;
        if (fpsInput) fpsInput.value = 4;
        if (loopCb) loopCb.checked = true;
        updateModeButtons();

        // If data is loaded, re-render the first slice
        if (volInfo.name) {
            syncYAxis();
            updateAxes();
            updateLineRangeLabel();
            loadAndRenderSlice(curDir, curIndex);
        } else {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            setStatus('idle', 'Reset done');
        }
    };
}

if (btnLoadImage) {
    btnLoadImage.onclick = () => imageFileInput.click();
}

if (deviceSelect) {
    deviceSelect.onchange = async e => {
        const dev = e.target.value;
        try {
            const resp = await fetch(`/api/device?device_id=${encodeURIComponent(dev)}`, { method: 'POST' });
            if (resp.ok) setStatus('ready', `Device switched: ${dev}`);
        } catch (err) {
            setStatus('error', 'Device switch failed: ' + err.message);
        }
    };
}

const seismicImage = new Image();

window.onresize = () => {
    if (typeof sizeSectionCanvases === 'function') sizeSectionCanvases();
    else {
        canvas.width = canvas.parentElement.clientWidth;
        canvas.height = canvas.parentElement.clientHeight;
    }
    if (currentSliceData && currentSliceShape) {
        renderSliceToCanvas(currentSliceData, currentSliceShape[0], currentSliceShape[1]);
    }
    drawSeismic();
    if (typeof updateCompareView === 'function') updateCompareView();
};

// Keep the canvas backing store equal to its displayed box when the layout settles or changes
if (typeof ResizeObserver === 'function') {
    let _rsPending = false;
    new ResizeObserver(() => {
        if (_rsPending) return;
        _rsPending = true;
        requestAnimationFrame(() => { _rsPending = false; window.onresize(); });
    }).observe(document.querySelector('.workspace'));
}

window.addEventListener('beforeunload', () => {
    const total = [...picksBySlice.values()].reduce((sum, arr) => sum + arr.length, 0);
    if (total > 0) saveToLocalStorage();
});

async function loadVolumeList() {
    const sel = document.getElementById('volumeSelect');
    if (!sel) return;
    try {
        const resp = await fetch('/api/npy/list');
        if (!resp.ok) return;
        const data = await resp.json();
        const volumes = data.volumes || [];
        sel.innerHTML = '';
        if (volumes.length === 0) {
            sel.innerHTML = '<option value="">(no preset volumes)</option>';
            return;
        }
        volumes.forEach(v => {
            const opt = document.createElement('option');
            opt.value = v.name;
            opt.textContent = `${v.name} (${v.n_inlines}×${v.n_crosslines}×${v.n_samples})`;
            sel.appendChild(opt);
        });

        sel.onchange = async () => {
            const selected = sel.value;
            if (!selected) return;
            const metaResp = await fetch(`/api/npy/${selected}/meta`);
            if (metaResp.ok) {
                const meta = await metaResp.json();
                await activateVolume(meta, selected, { source: 'api/npy' });
            }
        };

        // Activate the first volume by default (e.g. synthetic_deep_v1)
        const defaultVol = volumes[0].name;
        sel.value = defaultVol;
        const metaResp = await fetch(`/api/npy/${defaultVol}/meta`);
        if (metaResp.ok) {
            const meta = await metaResp.json();
            await activateVolume(meta, defaultVol, { source: 'api/npy' });
        }
    } catch (err) {
        console.warn('loadVolumeList failed:', err);
    }
}

window.onload = () => {
    canvas.width = canvas.parentElement.clientWidth;
    canvas.height = canvas.parentElement.clientHeight;
    updateModeButtons();
    drawSeismic();
    loadDeviceList();
    loadVolumeList();

    fetch('/api/status')
        .then(r => r.json())
        .then(s => {
            updateSamBadge(s);
            if (!s.weights_exists) {
                setStatus('error', `SAM3 weights missing: put sam3.pt at ${s.weights_path} (from ${s.weights_source}). ` +
                                   'Browsing, Low-freq, Compare and Export work without it.');
            } else if (s.model_loaded) {
                setStatus('ready', 'SAM3 ready (' + (s.sam_device === 'cuda' ? s.gpu_name : 'CPU') + ')');
            } else if (s.model_loading) {
                setStatus('loading', 'SAM3 loading...');
            } else {
                setStatus('ready', 'Ready. SAM3 loads on the first SAM run (about 10-20 s).');
            }
            updateBackupStatus();
            const backup = checkForBackup();
            if (backup) showRecoveryDialog(backup);
        })
        .catch(() => setStatus('error', `Server not reachable at ${location.origin}. Start it with: python src/server.py`));
};

seismicImage.onload = () => {
    drawSeismic();
};

// "More" menu (scope S8): controls the demo does not need. The button toggles it;
// a click outside or Escape closes it. The controls keep their ids and handlers.
(function initMoreMenu() {
    const wrap = document.getElementById('moreWrap');
    const btn = document.getElementById('btnMore');
    const menu = document.getElementById('moreMenu');
    if (!wrap || !btn || !menu) return;
    const setOpen = open => {
        menu.classList.toggle('open', open);
        btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    };
    btn.addEventListener('click', () => setOpen(!menu.classList.contains('open')));
    document.addEventListener('mousedown', e => {
        if (menu.classList.contains('open') && !wrap.contains(e.target)) setOpen(false);
    });
    window.addEventListener('keydown', e => {
        if (e.key === 'Escape' && menu.classList.contains('open')) setOpen(false);
    });
})();
