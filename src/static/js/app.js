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

// 缩放因子: 1.0 = 原始比例, >1 放大, <1 缩小
let scaleY = 1.0;  // 上下纵向缩放
let scaleX = 1.0;  // 横向缩放

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
        // TimeSlice 水平切片不支持 Wiggle 波形显示
        if (newMode === 'wv' && curDir === 'timeslice') {
            e.target.value = 'vd';
            setStatus('ready', 'TimeSlice 不支持 Wiggle 模式, 已保持 Seismic Color');
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

// 增益/减益按钮
const btnGainUp = document.getElementById('btnGainUp');
const btnGainDown = document.getElementById('btnGainDown');
if (btnGainUp) btnGainUp.onclick = () => adjustGain('up');
if (btnGainDown) btnGainDown.onclick = () => adjustGain('down');

// 缩放按钮
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

// Save 按钮：手动保存拾取到 localStorage
if (btnSave) {
    btnSave.onclick = () => {
        const total = [...picksBySlice.values()].reduce((s, a) => s + a.length, 0);
        if (total === 0) { setStatus('ready', '没有拾取点可保存'); return; }
        saveToLocalStorage();
        setStatus('ready', `💾 已保存 ${total} 个拾取点到浏览器本地`);
    };
}

// Restore 按钮：从 localStorage 恢复拾取
if (btnRestore) {
    btnRestore.onclick = () => {
        const backup = checkForBackup();
        if (!backup) {
            alert('没有找到本地备份的拾取数据。');
            return;
        }
        showRecoveryDialog(backup);
    };
}

// Reset 按钮：恢复到初始状态
if (btnReset) {
    btnReset.onclick = () => {
        if (!confirm('确定要重置所有状态吗？这将清除所有拾取点和缓存。')) return;

        // 停止播放
        if (playTimer) { clearInterval(playTimer); playTimer = null; }

        // 清空拾取点和 mask
        picksBySlice.clear();
        logitsMap = null; logitsWidth = 0; logitsHeight = 0;
        embeddingId = null;
        currentSessionId = null;
        clearBackup();

        // 清空缓存
        sliceCache.clear();
        embCache.clear();

        // 重置状态变量
        curDir = 'inline';
        curIndex = 0;
        yAxisUnit = 'time';
        velocity = 3000;
        loopEnabled = true;
        fps = 4;
        pickMode = 'exclude';
        userGainFactor = 1.0;  // 重置增益偏移
        scaleY = 1.0;
        scaleX = 1.0;

        // 同步 UI 控件
        if (dirSelect) dirSelect.value = 'inline';
        if (yUnitSelect) yUnitSelect.value = 'time';
        if (velocityInput) velocityInput.value = 3000;
        if (fpsInput) fpsInput.value = 4;
        if (loopCb) loopCb.checked = true;
        updateModeButtons();

        // 如果有加载的数据，重新渲染第一张
        if (volInfo.name) {
            syncYAxis();
            updateAxes();
            updateLineRangeLabel();
            loadAndRenderSlice(curDir, curIndex);
        } else {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            setStatus('idle', '已重置');
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
    canvas.width = canvas.parentElement.clientWidth;
    canvas.height = canvas.parentElement.clientHeight;
    if (currentSliceData && currentSliceShape) {
        renderSliceToCanvas(currentSliceData, currentSliceShape[0], currentSliceShape[1]);
    }
    drawSeismic();
};

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
            sel.innerHTML = '<option value="">(无预置数据体)</option>';
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

        // 默认自动激活第一个数据体 (如 synthetic_deep_v1)
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
            if (s.model_loaded) {
                setStatus('ready', 'SAM3 ready (' + (s.gpu_name || 'CPU') + ')');
            } else if (s.model_loading) {
                setStatus('loading', 'SAM3 loading...');
            } else if (s.weights_exists) {
                setStatus('ready', 'SGY browse ready | SAM lazy-load on first inference');
            } else {
                setStatus('ready', 'SGY browse ready | weights missing');
            }
            updateBackupStatus();
            const backup = checkForBackup();
            if (backup) showRecoveryDialog(backup);
        })
        .catch(() => setStatus('error', 'Backend disconnected'));
};

seismicImage.onload = () => {
    drawSeismic();
};
