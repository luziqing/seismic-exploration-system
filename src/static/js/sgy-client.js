// sgy-client.js — SGY slice browsing, navigation, pick points
// Extracted from sam.html — contains slice cache, loading, navigation, and canvas interaction

// ── LRU cache ───────────────────────────────────────
function cacheGet(map, key) {
    if (!map.has(key)) return null;
    const v = map.get(key);
    map.delete(key); map.set(key, v);
    return v;
}
function cachePut(map, key, val, maxSize) {
    if (map.size >= maxSize) {
        const firstKey = map.keys().next().value;
        map.delete(firstKey);
    }
    map.set(key, val);
}

// Flatten the (possibly nested) 2D list from the backend into a 1D Float32Array
function flattenSliceData(data, shape) {
    const total = shape[0] * shape[1];
    const out = new Float32Array(total);
    if (Array.isArray(data) && Array.isArray(data[0])) {
        // Nested 2D list (current Zarr/VDS response format)
        for (let i = 0; i < shape[0]; i++) {
            const row = data[i];
            for (let j = 0; j < shape[1]; j++) {
                out[i * shape[1] + j] = row[j];
            }
        }
    } else {
        // Already a flat list
        for (let i = 0; i < total; i++) out[i] = data[i];
    }
    return out;
}

// ── Max index for current slice ──────────────────────────────
function currentMaxIndex() {
    if (curDir === 'inline')     return volInfo.ilCount;
    if (curDir === 'crossline')  return volInfo.xlCount;
    return volInfo.tsCount;
}
function currentSliceKey() { return `${curDir}:${curIndex}`; }

// ── Y-axis unit calculation and switching ───────────────────────────
function computeYRange() {
    const t_ms = (volInfo.tsCount || 0) * (volInfo.dtUs || 1000) / 1000;
    if (yAxisUnit === 'depth') return t_ms * velocity / 2 / 1000;  // depth = v * t / 2, t in ms → m
    return t_ms;
}
function computeYLabel() {
    return yAxisUnit === 'depth' ? 'Depth (m)' : 'Time (ms)';
}
function syncYAxis() {
    COORD.yTop = 0;
    COORD.yRange = computeYRange();
    COORD.yLabel = computeYLabel();
}

// Switch Y-axis unit (with save prompt)
async function setYAxisUnit(unit) {
    if (unit !== 'time' && unit !== 'depth') return;
    if (unit === yAxisUnit) return;
    // Before switching: prompt to save or auto-save current picks
    const total = [...picksBySlice.values()].reduce((s, a) => s + a.length, 0);
    if (total > 0) {
        const ok = window.confirm(
            `There are ${total} unexported pick points.\n` +
            `Switching the Y-axis unit changes how they are displayed.\n\n` +
            `Click "OK" to auto-save to the database and switch;\n` +
            `click "Cancel" to abort.`
        );
        if (!ok) {
            const sel = document.getElementById('yUnitSelect');
            if (sel) sel.value = yAxisUnit;
            return;
        }
        await autoSavePicks();
    }
    yAxisUnit = unit;
    const sel = document.getElementById('yUnitSelect');
    if (sel) sel.value = unit;
    syncYAxis();
    updateAxes();
    drawSeismic();
    setStatus('ready', `Y axis: ${COORD.yLabel}`);
}

async function autoSavePicks() {
    if (!currentSessionId) return;
    const allPts = [];
    picksBySlice.forEach((pts) => {
        pts.forEach(p => {
            const yVal = p.yUnit === 'depth' ? p.depth_m : p.time_ms;
            allPts.push({
                il: p.il, xl: p.xl,
                depth: yVal,
                px_x: p.x, px_y: p.y, label: p.label,
            });
        });
    });
    if (allPts.length) {
        try {
            await fetch(`/api/db/session/${currentSessionId}/points`, {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({session_id: currentSessionId, points: allPts}),
            });
        } catch (e) { console.warn('Auto-save failed:', e); }
    }
}

function applyVelocity() {
    const velIn = document.getElementById('velocityInput');
    const v = +velIn.value;
    if (!v || v < 100 || v > 20000) {
        setStatus('error', 'Velocity must be 100~20000 m/s');
        return;
    }
    velocity = v;
    if (yAxisUnit === 'depth') {
        syncYAxis();
        updateAxes();
        setStatus('ready', `Velocity: ${velocity} m/s (depth recalculated)`);
    } else {
        setStatus('ready', `Velocity: ${velocity} m/s (applies when switched to Depth)`);
    }
}

// ── Dynamic axis update (zoom aware) ─────────────────────
function updateAxes() {
    // Update Y-axis label
    const yLabelEl = document.getElementById('yAxisLabel');
    if (yLabelEl) yLabelEl.textContent = COORD.yLabel;

    // When zoomed: origin is the canvas center; after scaling by scaleX/scaleY,
    // visible range = original range / scale, centered at 50%
    // visible start = 0.5 - 0.5/scale, visible end = 0.5 + 0.5/scale (normalized coords)
    const xVis0 = 0.5 - 0.5 / scaleX;
    const xVis1 = 0.5 + 0.5 / scaleX;
    const yVis0 = 0.5 - 0.5 / scaleY;
    const yVis1 = 0.5 + 0.5 / scaleY;

    // Top X axis: content depends on curDir
    const topAxis = document.getElementById('topAxis');
    topAxis.innerHTML = '';
    const nTicks = 6;

    let xLabel = '';
    for (let i = 0; i < nTicks; i++) {
        // Spread ticks evenly over the visible range
        const t = nTicks > 1 ? i / (nTicks - 1) : 0.5;
        const frac = xVis0 + t * (xVis1 - xVis0);  // visible position in normalized [0,1]
        const pct = t * 100;  // tick position on the axis container, in percent
        let val = 0;
        if (curDir === 'inline') {
            val = (COORD.crossMin + frac * (COORD.crossMax - COORD.crossMin)).toFixed(0);
            xLabel = 'XL';
        } else if (curDir === 'crossline') {
            val = (COORD.crossMin + frac * (COORD.crossMax - COORD.crossMin)).toFixed(0);
            xLabel = 'IL';
        } else {
            val = (COORD.crossMin + frac * (COORD.crossMax - COORD.crossMin)).toFixed(0);
            xLabel = 'XL';
        }
        const div = document.createElement('div');
        div.style.cssText = `position:absolute;left:${pct}%;bottom:2px;transform:translateX(-50%);text-align:center;font-size:11px;`;
        div.textContent = val;
        topAxis.appendChild(div);
    }

    // Left Y axis: content depends on curDir
    const leftAxis = document.getElementById('leftAxis');
    leftAxis.querySelectorAll('.tick-label').forEach(el => el.remove());
    const nDepth = 8;

    if (curDir === 'timeslice') {
        // TimeSlice: vertical axis = Inline
        for (let i = 0; i < nDepth; i++) {
            const t = nDepth > 1 ? i / (nDepth - 1) : 0.5;
            const frac = yVis0 + t * (yVis1 - yVis0);
            const pct = t * 100;
            const il = (volInfo.ilMin + frac * (volInfo.ilMax - volInfo.ilMin)).toFixed(0);
            const div = document.createElement('div');
            div.className = 'tick-label';
            div.style.cssText = `position:absolute;top:${pct}%;transform:translateY(-50%);right:8px;font-size:11px;`;
            div.textContent = il;
            leftAxis.appendChild(div);
        }
    } else {
        // Inline/Crossline: vertical axis = Time or Depth
        for (let i = 0; i < nDepth; i++) {
            const t = nDepth > 1 ? i / (nDepth - 1) : 0.5;
            const frac = yVis0 + t * (yVis1 - yVis0);
            const pct = t * 100;
            const depth = (COORD.yTop + frac * COORD.yRange).toFixed(0);
            const div = document.createElement('div');
            div.className = 'tick-label';
            div.style.cssText = `position:absolute;top:${pct}%;transform:translateY(-50%);right:8px;font-size:11px;`;
            div.textContent = depth;
            leftAxis.appendChild(div);
        }
    }
    if (typeof compareAdjustAxes === 'function') compareAdjustAxes();
}

// Backend slice URL: Zarr and VDS share the same API
function sliceApiUrl(source, name, dir, index) {
    return `/${source}/${name}/slice/${dir}/${index}`;
}

function applyVolumeInfo(info, fallbackName, source = 'api/npy') {
    const inferredName = info.npy_name
        || info.zarr_name
        || (info.filename ? info.filename.replace(/\.sgy$/i, '') : '')
        || fallbackName
        || null;

    volInfo = {
        source: source,
        name: inferredName,
        ilCount: info.n_inlines || 0,
        xlCount: info.n_crosslines || 0,
        tsCount: info.n_samples || 0,
        ilMin: (info.il_range && info.il_range[0]) || 0,
        ilMax: (info.il_range && info.il_range[1]) || 0,
        xlMin: (info.xl_range && info.xl_range[0]) || 0,
        xlMax: (info.xl_range && info.xl_range[1]) || 0,
        tsMin: 0,
        tsMax: Math.max(0, (info.n_samples || 0) - 1),
        dtUs: info.dt_us || 0,
    };

    COORD.ilMin = volInfo.ilMin;
    COORD.ilMax = volInfo.ilMax;
    COORD.xl = volInfo.xlMin;
    syncYAxis();
    updateAxes();
}

async function activateVolume(info, fallbackName, options = {}) {
    const { preserveBackup = false, source = 'api/npy' } = options;
    applyVolumeInfo(info, fallbackName, source);

    curDir = 'inline';
    curIndex = Math.floor(volInfo.ilCount / 2);

    const dirSel = document.getElementById('dirSelect');
    if (dirSel) dirSel.value = curDir;
    const fpsIn = document.getElementById('fpsInput');
    if (fpsIn) fpsIn.value = fps;
    const loopChk = document.getElementById('loopCb');
    if (loopChk) loopChk.checked = loopEnabled;

    updateLineRangeLabel();
    slicePanel.classList.add('visible');
    picksBySlice.clear();
    if (!preserveBackup) clearBackup();
    await loadAndRenderSlice(curDir, curIndex);
    btnGenSlices.disabled = false;
}

async function restoreCurrentSgyIfLoaded() {
    const resp = await fetch('/api/sgy/info');
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

    const info = await resp.json();
    if (!info.loaded) return false;

    await activateVolume(
        info,
        info.filename ? info.filename.replace(/\.sgy$/i, '') : null,
        { preserveBackup: true }
    );
    setStatus('ready', `SGY: ${info.filename}  IL ${volInfo.ilMin}~${volInfo.ilMax}  current Inline ${volInfo.ilMin + curIndex}`);
    return true;
}

async function fetchSlice(source, name, dir, index, mode = 'raw') {
    let url = sliceApiUrl(source, name, dir, index);
    if (source === 'api/npy' && mode && mode !== 'raw') url += `?mode=${encodeURIComponent(mode)}`;
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    // Binary float32 response: shape is read from response headers
    const rows = parseInt(resp.headers.get('X-Rows') || '0');
    const cols = parseInt(resp.headers.get('X-Cols') || '0');
    const buf = await resp.arrayBuffer();
    const data = new Float32Array(buf);
    if (rows && cols) {
        return { shape: [rows, cols], data };
    }
    // fallback: JSON response (legacy zarr endpoint)
    try {
        const json = JSON.parse(new TextDecoder().decode(buf));
        return json;
    } catch { return { shape: [data.length, 1], data }; }
}

// Main entry: load and render one slice
async function loadAndRenderSlice(dir, index) {
    if (!volInfo.name) {
        setStatus('idle', 'Load an SGY/VDS first');
        return;
    }
    if (isLoading) { pendingIdx = {dir, index}; return; }
    isLoading = true;
    setStatus('loading', `Loading ${dir} ${index}...`);

    const mode = volInfo.source === 'api/npy' ? sliceMode : 'raw';
    // Key includes volume and mode: the noisy/clean pair and raw/low-freq share directions and indices
    const key = `${volInfo.name}:${mode}:${dir}:${index}`;
    try {
        let payload = cacheGet(sliceCache, key);
        if (!payload) {
            payload = await fetchSlice(volInfo.source, volInfo.name, dir, index, mode);
            cachePut(sliceCache, key, payload, SLICE_CACHE_SIZE);
        }
        const rows = payload.shape[0], cols = payload.shape[1];
        // Binary response is already a Float32Array, no flatten needed
        const data = (payload.data instanceof Float32Array && payload.data.length === rows * cols)
            ? payload.data
            : flattenSliceData(payload.data, payload.shape);
        renderSliceToCanvas(data, rows, cols);
        // Sync coordinate ranges (for mousemove pick coordinate display)
        syncCoordFromSlice(dir, index);
        updateAxes();  // update axis labels so IL/XL ranges show correctly
        // logits: a new slice clears the old mask and embedding
        logitsMap = null; logitsWidth = 0; logitsHeight = 0;
        embeddingId = null; embeddingImageSize = null;  // new slice needs a fresh embedding
        drawSeismic();
        loadVolumeMaskOverlay(dir, index);  // overlay the volume mask (incl. propagation results) if this slice has one
        updateSubtitle(dir, index);
        updateLineControls(index);
        if (typeof updateSurveyMap === 'function') updateSurveyMap();
        if (typeof updateAutoRefineControl === 'function') updateAutoRefineControl();
        if (typeof syncCompareControls === 'function') syncCompareControls();
        if (typeof updateCompareView === 'function') updateCompareView();
        // Create a new pick session
        currentSessionId = null;
        fetch('/api/db/session?slice_id=0', {method: 'POST'})
            .then(r => r.json()).then(d => { currentSessionId = d.session_id; })
            .catch(() => {});
        setStatus('ready', `${dir} ${index}  cache ${sliceCache.size}/${SLICE_CACHE_SIZE}  [${rows}×${cols}] clip=${currentClip.toPrecision(3)}`);
    } catch (e) {
        setStatus('error', `Load failed: ${errText(e)}`);
    } finally {
        isLoading = false;
        if (pendingIdx) {
            const p = pendingIdx; pendingIdx = null;
            loadAndRenderSlice(p.dir, p.index);
        }
    }
}

// Sync COORD so picks map back to the correct IL/XL/Depth
function syncCoordFromSlice(dir, index) {
    if (dir === 'inline') {
        // Inline section: index is the IL offset, horizontal axis is the Crossline range
        COORD.ilMin = volInfo.ilMin;
        COORD.ilMax = volInfo.ilMax;
        COORD.xl = volInfo.ilMin + index;  // current Inline number
        COORD.crossMin = volInfo.xlMin;
        COORD.crossMax = volInfo.xlMax;
    } else if (dir === 'crossline') {
        // Crossline section: index is the XL offset, horizontal axis is the Inline range
        COORD.ilMin = volInfo.ilMin;
        COORD.ilMax = volInfo.ilMax;
        COORD.xl = volInfo.xlMin + index;  // current Crossline number
        COORD.crossMin = volInfo.ilMin;
        COORD.crossMax = volInfo.ilMax;
    } else {
        // TimeSlice: horizontal XL, vertical IL, fixed depth
        COORD.crossMin = volInfo.xlMin;
        COORD.crossMax = volInfo.xlMax;
    }
    syncYAxis();
}

// ════════════════════════════════════════════════════
// Navigation
// ════════════════════════════════════════════════════

function stepSlice(delta) {
    const max = currentMaxIndex();
    if (max === 0) return;
    let next = curIndex + delta;
    if (next < 0) {
        if (loopEnabled) next = max - 1; else return;
    }
    if (next >= max) {
        if (loopEnabled) next = 0; else { stopPlay(); return; }
    }
    curIndex = next;
    loadAndRenderSlice(curDir, curIndex);
}
function gotoSlice(idx) {
    const max = currentMaxIndex();
    if (max === 0) return;
    const v = +idx;
    if (Number.isNaN(v)) return;
    curIndex = Math.max(0, Math.min(max - 1, v));
    loadAndRenderSlice(curDir, curIndex);
}
function gotoFirst() { gotoSlice(0); }
function gotoLast()  { gotoSlice(currentMaxIndex() - 1); }

// ════════════════════════════════════════════════════
// Playback control
// ════════════════════════════════════════════════════

function startPlay() {
    if (playTimer) return;
    const interval = 1000 / Math.max(1, fps);
    playTimer = setInterval(() => stepSlice(+1), interval);
    const btn = document.getElementById('btnPlay');
    if (btn) btn.textContent = '❚❚';
}
function stopPlay() {
    if (playTimer) clearInterval(playTimer);
    playTimer = null;
    const btn = document.getElementById('btnPlay');
    if (btn) btn.textContent = '▶';
}
function togglePlay() { playTimer ? stopPlay() : startPlay(); }

// ════════════════════════════════════════════════════
// UI update
// ════════════════════════════════════════════════════

function updateSubtitle(dir, index) {
    const labels = {inline: 'IL', crossline: 'XL', timeslice: 'TS'};
    const curKey = `${dir}:${index}`;
    const n = (picksBySlice.get(curKey) || []).length;
    const total = [...picksBySlice.values()].reduce((s, a) => s + a.length, 0);
    const sub = document.getElementById('plotSubtitle');
    if (!sub) return;
    const volName = volInfo.name || '—';
    const coordVal = curDir === 'inline' ? (volInfo.ilMin + index)
                   : curDir === 'crossline' ? (volInfo.xlMin + index)
                   : index;
    sub.textContent = `${labels[dir]} ${coordVal}  (vol=${volName})  this slice ${n} pts / total ${total}`;
}
function updateLineControls(idx) {
    const slider = document.getElementById('lineSlider');
    if (slider && +slider.value !== idx) slider.value = idx;
    const lineNo = document.getElementById('lineNo');
    if (lineNo && document.activeElement !== lineNo) lineNo.value = idx;
    const max = currentMaxIndex();
    const posLabel = document.getElementById('slicePosLabel');
    // Show direction + current line number (actual IL/XL/TS value)
    let lineVal = idx;
    if (curDir === 'inline') lineVal = volInfo.ilMin + idx;
    else if (curDir === 'crossline') lineVal = volInfo.xlMin + idx;
    const dirLabel = curDir === 'inline' ? 'Inline' : curDir === 'crossline' ? 'Crossline' : 'TimeSlice';
    if (posLabel) posLabel.textContent = `${dirLabel} ${idx + 1} / ${max}`;
    const lineNoSpan = document.getElementById('sliceLineNo');
    if (lineNoSpan) {
        lineNoSpan.textContent = curDir === 'timeslice'
            ? `${lineVal} ms`
            : `${dirLabel.charAt(0)}${dirLabel.slice(1,2).toLowerCase()}=${lineVal}`;
    }
}
function updateLineRangeLabel() {
    const ranges = {
        inline:     `IL ${volInfo.ilMin}~${volInfo.ilMax} (${volInfo.ilCount})`,
        crossline:  `XL ${volInfo.xlMin}~${volInfo.xlMax} (${volInfo.xlCount})`,
        timeslice:  `TS ${volInfo.tsMin}~${volInfo.tsMax} (${volInfo.tsCount})`,
    };
    const lbl = document.getElementById('lineRangeLabel');
    if (lbl) lbl.textContent = ranges[curDir] || '—';
    const slider = document.getElementById('lineSlider');
    if (slider) slider.max = Math.max(0, currentMaxIndex() - 1);
}

// ════════════════════════════════════════════════════
// Interaction events
// ════════════════════════════════════════════════════

canvas.addEventListener('mousemove', e => {
    const r = canvas.getBoundingClientRect();
    const x = e.clientX - r.left, y = e.clientY - r.top;
    const w = r.width, h = r.height;   // displayed size: the backing store can differ from the CSS box
    // Horizontal coord: inline→XL, crossline→IL, timeslice→XL
    const crossVal = Math.round(COORD.crossMin + (x/w)*(COORD.crossMax-COORD.crossMin));
    // Vertical: section→Time/Depth, timeslice→IL
    const yVal = (COORD.yTop + (y/h)*COORD.yRange).toFixed(1);
    // Amplitude value
    let amp = 'N/A';
    if (currentSliceData && currentSliceShape) {
        const [rows, cols] = currentSliceShape;
        const sy = Math.min(rows-1, Math.floor(y/h*rows));
        const sx = Math.min(cols-1, Math.floor(x/w*cols));
        amp = currentSliceData[sy*cols+sx].toFixed(1);
    }
    // Logits value
    let logits = 'N/A';
    if (logitsMap && logitsMode) {
        const ix = Math.floor((x/w)*logitsWidth);
        const iy = Math.floor((y/h)*logitsHeight);
        if (ix>=0 && ix<logitsWidth && iy>=0 && iy<logitsHeight)
            logits = logitsMap[iy*logitsWidth+ix].toFixed(3);
    }
    infoBox.style.display='block';
    infoBox.style.left=(e.clientX+10)+'px'; infoBox.style.top=(e.clientY+10)+'px';
    const crossLabel = curDir==='inline' ? 'XL' : curDir==='crossline' ? 'IL' : 'XL';
    infoBox.innerHTML = `${crossLabel}: ${crossVal}<br>${COORD.yLabel.split(' ')[0]}: ${yVal}<br>Amp: ${amp}<br>Logits: ${logits}`;
});
canvas.addEventListener('mouseleave', () => infoBox.style.display='none');

canvas.addEventListener('click', async e => {
    const r = canvas.getBoundingClientRect();
    // Position in backing-store pixels: the canvas's internal size can differ from its displayed size
    const x = (e.clientX - r.left) * canvas.width / r.width, y = (e.clientY - r.top) * canvas.height / r.height;
    // Map back to IL/XL/Y (from current COORD, Y follows yAxisUnit)
    let il, xl, yVal;
    let time_ms = 0, depth_m = 0;
    if (curDir === 'inline') {
        const crossPct = x / canvas.width;
        const yPct = y / canvas.height;
        xl = (COORD.crossMin + crossPct * (COORD.crossMax - COORD.crossMin)).toFixed(2);
        il = (volInfo.ilMin + curIndex).toFixed(0);
        time_ms = +(COORD.yTop + yPct * COORD.yRange).toFixed(2);
        if (yAxisUnit === 'time') {
            yVal = time_ms;
        } else {
            depth_m = +(time_ms * velocity / 2 / 1000).toFixed(2);
            yVal = depth_m;
        }
    } else if (curDir === 'crossline') {
        const ilPct = x / canvas.width;
        const yPct = y / canvas.height;
        il = (COORD.crossMin + ilPct * (COORD.crossMax - COORD.crossMin)).toFixed(2);
        xl = (volInfo.xlMin + curIndex).toFixed(0);
        time_ms = +(COORD.yTop + yPct * COORD.yRange).toFixed(2);
        if (yAxisUnit === 'time') {
            yVal = time_ms;
        } else {
            depth_m = +(time_ms * velocity / 2 / 1000).toFixed(2);
            yVal = depth_m;
        }
    } else {
        // TimeSlice
        const xlPct = x / canvas.width;
        const ilPct = y / canvas.height;
        xl = (COORD.crossMin + xlPct * (COORD.crossMax - COORD.crossMin)).toFixed(2);
        il = (volInfo.ilMin + ilPct * (volInfo.ilMax - volInfo.ilMin)).toFixed(2);
        time_ms = +(curIndex * (volInfo.dtUs || 1000) / 1000).toFixed(2);
        depth_m = +(time_ms * velocity / 2 / 1000).toFixed(2);
        yVal = yAxisUnit === 'depth' ? depth_m : time_ms;
    }
    const color = pickMode === 'include' ? 'green' : 'red';
    const label = pickMode === 'include' ? 1 : 0;
    const sliceKey = currentSliceKey();
    const nx = x / canvas.width, ny = y / canvas.height;  // normalized coords, zoom aware
    const point = {
        x, y, nx, ny, il, xl,
        time_ms, depth_m,
        yUnit: yAxisUnit,
        color, label, sliceKey,
    };
    if (!picksBySlice.has(sliceKey)) picksBySlice.set(sliceKey, []);
    picksBySlice.get(sliceKey).push(point);
    activePicks = picksBySlice.get(sliceKey);
    saveToLocalStorage();
    drawSeismic();
    updateSubtitle(curDir, curIndex);

    // Save to database (depth field uses the current unit, for later analysis)
    if (currentSessionId) {
        fetch(`/api/db/session/${currentSessionId}/points`, {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({session_id: currentSessionId, points: [{il, xl, depth: yVal, px_x: x, px_y: y, label}]})
        });
    }
});

btnDelPoints.onclick = async () => {
    const curKey = currentSliceKey();
    const cur = picksBySlice.get(curKey);
    if (!cur || !cur.length) return;
    cur.pop();
    saveToLocalStorage();
    if (currentSessionId) {
        await fetch(`/api/db/session/${currentSessionId}/points/last`, {method: 'DELETE'});
    }
    drawSeismic();
    updateSubtitle(curDir, curIndex);
};

btnClearMask.onclick = e => {
    const curKey = currentSliceKey();
    if (e && e.shiftKey) {
        picksBySlice.clear();
    } else {
        picksBySlice.delete(curKey);
    }
    saveToLocalStorage();
    if (currentSessionId) {
        fetch(`/api/db/session/${currentSessionId}/points`, {method: 'DELETE'});
    }
    logitsMap = null;
    drawSeismic();
    updateSubtitle(curDir, curIndex);
};

btnExport.onclick = () => {
    const total = [...picksBySlice.values()].reduce((s, a) => s + a.length, 0);
    if (total === 0) return;
    const yHeader = yAxisUnit === 'depth' ? 'Depth_m' : 'Time_ms';
    let csv = `SliceKey,Inline,Crossline,${yHeader},YUnit,Label,Color\n`;
    picksBySlice.forEach((pts, sliceKey) => {
        pts.forEach(p => {
            const yVal = yAxisUnit === 'depth' ? p.depth_m : p.time_ms;
            csv += `${sliceKey},${p.il},${p.xl},${yVal},${yAxisUnit},${p.label},${p.color}\n`;
        });
    });
    const blob = new Blob([csv], {type: 'text/csv'});
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `picked_${volInfo.name || 'horizon'}_${yAxisUnit}.csv`;
    a.click();
};

// ── Bottom backup status update ─────────────────────────────────
function updateBackupStatus() {
    const el = document.getElementById('backupStatus');
    if (!el) return;
    try {
        const raw = localStorage.getItem(LS_KEY);
        if (!raw) { el.textContent = ''; return; }
        const snap = JSON.parse(raw);
        const total = Object.values(snap.picks || {})
            .reduce((s, arr) => s + (Array.isArray(arr) ? arr.length : 0), 0);
        if (total === 0) { el.textContent = ''; return; }
        const age = Date.now() - (snap.timestamp || 0);
        const ageStr = age < 60000 ? 'just now'
                     : age < 3600000 ? Math.floor(age / 60000) + ' min ago'
                     : Math.floor(age / 3600000) + ' h ago';
        const vol = snap.volName ? ` [${snap.volName}]` : '';
        el.textContent = `💾 ${total} pts${vol} · ${ageStr}`;
    } catch { el.textContent = ''; }
}

// ════════════════════════════════════════════════════
// SGY loading & slice generation
// ════════════════════════════════════════════════════

btnLoadSGY.onclick = () => sgyFileInput.click();
sgyFileInput.onchange = async e => {
    const file = e.target.files[0]; if (!file) return;
    setStatus('loading', 'Uploading SGY...');
    const form = new FormData(); form.append('file', file);
    try {
        const resp = await fetch('/api/sgy/upload', {method: 'POST', body: form});
        if (!resp.ok) throw await respError(resp);
        const info = await resp.json();
        // Fill in volume info
        volInfo = {
            source: 'api/npy',
            name: info.npy_name || info.zarr_name || file.name.replace(/\.sgy$/i, ''),
            ilCount: info.n_inlines || 0,
            xlCount: info.n_crosslines || 0,
            tsCount: info.n_samples || 0,
            ilMin: (info.il_range && info.il_range[0]) || 0,
            ilMax: (info.il_range && info.il_range[1]) || 0,
            xlMin: (info.xl_range && info.xl_range[0]) || 0,
            xlMax: (info.xl_range && info.xl_range[1]) || 0,
            tsMin: 0,
            tsMax: (info.n_samples || 0) - 1,
            dtUs: info.dt_us || 0,
        };
        COORD.ilMin = volInfo.ilMin; COORD.ilMax = volInfo.ilMax;
        COORD.xl = volInfo.xlMin;
        syncYAxis();
        updateAxes();
        // render the middle inline by default
        curDir = 'inline';
        curIndex = Math.floor(volInfo.ilCount / 2);
        // sync dirSelect / fpsInput / loopCb / yUnitSelect
        const dirSel = document.getElementById('dirSelect');
        if (dirSel) dirSel.value = curDir;
        const fpsIn = document.getElementById('fpsInput');
        if (fpsIn) fpsIn.value = fps;
        const loopChk = document.getElementById('loopCb');
        if (loopChk) loopChk.checked = loopEnabled;
        updateLineRangeLabel();
        // Show the scroll bar right after opening the SGY
        slicePanel.classList.add('visible');
        // Clear old picks
        picksBySlice.clear();
        clearBackup();
        // Trigger first load: render the middle inline by default
        await loadAndRenderSlice(curDir, curIndex);
        btnGenSlices.disabled = false;
        setStatus('ready', `SGY: ${info.filename}  IL ${volInfo.ilMin}~${volInfo.ilMax}  current Inline ${volInfo.ilMin + curIndex}`);
    } catch (e) { setStatus('error', 'SGY load failed: ' + e.message); }
    e.target.value = '';
};

// Load a local image
btnLoadImage.onclick = () => imageFileInput.click();
imageFileInput.onchange = e => {
    const file = e.target.files[0];
    if (!file) return;
    const url = URL.createObjectURL(file);
    window.open(url, '_blank', 'noopener');
    e.target.value = '';
};

// ── Load VDS volume (OpenVDS) ─────────────────────────────
const btnLoadVDS = document.getElementById('btnLoadVDS');
const vdsFileInput = document.getElementById('vdsFileInput');

// On startup check whether OpenVDS is available; if not, disable the button with a hint
(async function checkVdsAvailability() {
    if (!btnLoadVDS) return;
    try {
        const resp = await fetch('/api/vds/status');
        const data = await resp.json();
        if (!data.available) {
            btnLoadVDS.disabled = true;
            btnLoadVDS.title = 'OpenVDS not installed (pip install openvds), unavailable';
            btnLoadVDS.style.opacity = '0.5';
        }
    } catch { /* if the status check fails, do not disable; report on upload instead */ }
})();

if (btnLoadVDS) btnLoadVDS.onclick = () => vdsFileInput.click();
if (vdsFileInput) vdsFileInput.onchange = async e => {
    const file = e.target.files[0];
    if (!file) return;
    setStatus('loading', 'Uploading VDS...');
    const form = new FormData();
    form.append('file', file);
    try {
        const resp = await fetch('/api/vds/upload', { method: 'POST', body: form });
        if (!resp.ok) throw new Error((await resp.json()).detail || `HTTP ${resp.status}`);
        const info = await resp.json();
        // Reuse the shared volume activation flow with source api/vds (slices read from /api/vds/{name}/slice/...)
        await activateVolume(info, info.filename, { source: 'api/vds' });
        setStatus('ready', `VDS: ${info.filename}  IL ${volInfo.ilMin}~${volInfo.ilMax}  current Inline ${volInfo.ilMin + curIndex}`);
    } catch (err) {
        setStatus('error', 'VDS load failed: ' + err.message);
    } finally {
        e.target.value = '';
    }
};

// ── Generate-slices dialog logic ─────────────────────────────────
const genModal = document.getElementById('genSlicesModal');
const genIL = document.getElementById('genIL');
const genXL = document.getElementById('genXL');
const genTS = document.getElementById('genTS');
const genILStep = document.getElementById('genILStep');
const genXLStep = document.getElementById('genXLStep');
const genTSStep = document.getElementById('genTSStep');
const genILFrom = document.getElementById('genILFrom');
const genILTo = document.getElementById('genILTo');
const genXLFrom = document.getElementById('genXLFrom');
const genXLTo = document.getElementById('genXLTo');
const genTSFrom = document.getElementById('genTSFrom');
const genTSTo = document.getElementById('genTSTo');

// Build the index list from step + range
function buildIndices(min, max, step, from, to) {
    const lo = (from !== '' && !isNaN(+from)) ? +from : min;
    const hi = (to !== '' && !isNaN(+to)) ? +to : max;
    const indices = [];
    for (let v = lo; v <= hi; v += step) indices.push(v);
    return indices;
}

function updateGenPreview() {
    const ilOn = genIL.checked, xlOn = genXL.checked, tsOn = genTS.checked;
    const ilStep = +genILStep.value || 5;
    const xlStep = +genXLStep.value || 5;
    const tsStep = +genTSStep.value || 50;

    let total = 0;
    // Inline
    if (ilOn) {
        const ilMin = volInfo.ilMin, ilMax = volInfo.ilMax;
        const indices = buildIndices(ilMin, ilMax, ilStep, genILFrom.value, genILTo.value);
        document.getElementById('genILPreview').textContent =
            `${ilMin}~${ilMax}, ${indices.length} lines`;
        total += indices.length;
    } else {
        document.getElementById('genILPreview').textContent = '';
    }
    // Crossline
    if (xlOn) {
        const xlMin = volInfo.xlMin, xlMax = volInfo.xlMax;
        const indices = buildIndices(xlMin, xlMax, xlStep, genXLFrom.value, genXLTo.value);
        document.getElementById('genXLPreview').textContent =
            `${xlMin}~${xlMax}, ${indices.length} lines`;
        total += indices.length;
    } else {
        document.getElementById('genXLPreview').textContent = '';
    }
    // TimeSlice
    if (tsOn) {
        const tsMin = 0, tsMax = Math.round((volInfo.tsCount - 1) * (volInfo.dtUs || 1000) / 1000);
        const indices = buildIndices(tsMin, tsMax, tsStep, genTSFrom.value, genTSTo.value);
        document.getElementById('genTSPreview').textContent =
            `${tsMin}~${tsMax}ms, ${indices.length} slices`;
        total += indices.length;
    } else {
        document.getElementById('genTSPreview').textContent = '';
    }

    document.getElementById('genTotalPreview').textContent =
        total > 0 ? `Total: ${total} slices` : 'Select at least one slice type';
    document.getElementById('genModalOK').disabled = total === 0;
}

// Bind preview updates
[genIL, genXL, genTS, genILStep, genXLStep, genTSStep,
 genILFrom, genILTo, genXLFrom, genXLTo, genTSFrom, genTSTo
].forEach(el => el.addEventListener('input', updateGenPreview));

// Open dialog
btnGenSlices.onclick = () => {
    if (!volInfo.name) { setStatus('error', 'Load an SGY first'); return; }
    // Fill defaults from the current volume range
    genILFrom.placeholder = String(volInfo.ilMin);
    genILTo.placeholder = String(volInfo.ilMax);
    genXLFrom.placeholder = String(volInfo.xlMin);
    genXLTo.placeholder = String(volInfo.xlMax);
    const tsMax = Math.round((volInfo.tsCount - 1) * (volInfo.dtUs || 1000) / 1000);
    genTSFrom.placeholder = '0';
    genTSTo.placeholder = String(tsMax);
    // Clear custom ranges (keep the last step settings)
    genILFrom.value = ''; genILTo.value = '';
    genXLFrom.value = ''; genXLTo.value = '';
    genTSFrom.value = ''; genTSTo.value = '';
    updateGenPreview();
    genModal.style.display = 'flex';
};

// Close dialog
document.getElementById('genModalClose').onclick = () => genModal.style.display = 'none';
document.getElementById('genModalCancel').onclick = () => genModal.style.display = 'none';
genModal.addEventListener('click', e => {
    if (e.target === genModal) genModal.style.display = 'none';
});

// Confirm generation
document.getElementById('genModalOK').onclick = async () => {
    genModal.style.display = 'none';
    setStatus('loading', 'Generating slices...');

    const body = {};
    // Inline
    if (genIL.checked) {
        body.inline_indices = buildIndices(
            volInfo.ilMin, volInfo.ilMax,
            +genILStep.value || 5,
            genILFrom.value, genILTo.value
        );
    }
    // Crossline
    if (genXL.checked) {
        body.crossline_indices = buildIndices(
            volInfo.xlMin, volInfo.xlMax,
            +genXLStep.value || 5,
            genXLFrom.value, genXLTo.value
        );
    }
    // TimeSlice
    if (genTS.checked) {
        const tsMax = Math.round((volInfo.tsCount - 1) * (volInfo.dtUs || 1000) / 1000);
        body.timeslice_indices = buildIndices(
            0, tsMax,
            +genTSStep.value || 50,
            genTSFrom.value, genTSTo.value
        );
    }

    try {
        const resp = await fetch('/api/sgy/generate_slices', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify(body)
        });
        if (!resp.ok) throw await respError(resp);
        const data = await resp.json();
        const parts = [];
        if (data.slices.inline) parts.push(`IL×${data.slices.inline.length}`);
        if (data.slices.crossline) parts.push(`XL×${data.slices.crossline.length}`);
        if (data.slices.timeslice) parts.push(`TS×${data.slices.timeslice.length}`);
        setStatus('ready', `Generated ${data.generated} slices (${parts.join(' + ')})`);
        slicePanel.classList.add('visible');
    } catch(e) { setStatus('error', 'Slice generation failed: ' + e.message); }
};

// ── 📥 Import CSV — import a previously exported CSV file ──────────
document.getElementById('btnImportCSV').onclick = () => csvFileInput.click();
csvFileInput.onchange = async e => {
    const file = e.target.files[0];
    if (!file) return;
    try {
        const text = await file.text();
        const lines = text.trim().split('\n');
        if (lines.length < 2) throw new Error('CSV is empty');

        // Parse header, find column indices
        const header = lines[0].split(',').map(h => h.trim());
        const colIdx = {};
        header.forEach((h, i) => { colIdx[h.toLowerCase()] = i; });

        // Required column check
        const required = ['slicekey', 'inline', 'crossline', 'label', 'color'];
        for (const col of required) {
            if (!(col in colIdx)) throw new Error(`CSV missing required column: ${col}`);
        }

        // Pick the Y column: Depth_m first, then Time_ms
        const hasDepth = 'depth_m' in colIdx;
        const hasTime = 'time_ms' in colIdx;
        const yCol = hasDepth ? colIdx['depth_m'] : (hasTime ? colIdx['time_ms'] : -1);
        const yUnitCol = colIdx['yunit'] ?? -1;

        const imported = new Map();
        let skipped = 0;
        for (let i = 1; i < lines.length; i++) {
            const cols = lines[i].split(',').map(c => c.trim());
            if (cols.length < header.length) { skipped++; continue; }

            const sliceKey = cols[colIdx['slicekey']];
            const il = parseFloat(cols[colIdx['inline']]);
            const xl = parseFloat(cols[colIdx['crossline']]);
            const label = parseInt(cols[colIdx['label']]) || 0;
            const color = cols[colIdx['color']] || (label ? 'green' : 'red');

            // Parse Y value
            const unit = yUnitCol >= 0 ? cols[yUnitCol] : (hasDepth ? 'depth' : 'time');
            let time_ms = 0, depth_m = 0;
            if (yCol >= 0) {
                const yVal = parseFloat(cols[yCol]) || 0;
                if (unit === 'depth') { depth_m = yVal; time_ms = depth_m * 2000 / velocity; }
                else { time_ms = yVal; depth_m = time_ms * velocity / 2 / 1000; }
            }

            // Parse slice direction and index
            const parts = sliceKey.split(':');
            const dir = parts[0] || 'inline';
            const idx = parseInt(parts[1]) || 0;

            const point = {
                x: 0, y: 0,  // pixel coords cannot be restored from CSV, set to 0
                il: String(il), xl: String(xl),
                time_ms, depth_m,
                yUnit: unit, color, label, sliceKey,
            };
            if (!imported.has(sliceKey)) imported.set(sliceKey, []);
            imported.get(sliceKey).push(point);
        }

        // Confirm import
        const total = [...imported.values()].reduce((s, a) => s + a.length, 0);
        if (total === 0) throw new Error('No valid data rows in CSV');

        const msg = `About to import ${total} pick points (${imported.size} slices)` +
                    (skipped > 0 ? `\nSkipping ${skipped} malformed rows` : '') +
                    `\n\nThis replaces all current pick points. Continue?`;
        if (!confirm(msg)) return;

        // Replace picksBySlice
        picksBySlice.clear();
        imported.forEach((pts, key) => picksBySlice.set(key, pts));
        saveToLocalStorage();
        drawSeismic();
        updateSubtitle(curDir, curIndex);
        setStatus('ready', `📥 Imported ${total} pick points`);
    } catch (e) {
        setStatus('error', 'CSV import failed: ' + e.message);
    }
    e.target.value = '';
};

// ════════════════════════════════════════════════════
// Browse control bindings (buttons / slider / direction / keyboard)
// ════════════════════════════════════════════════════

document.getElementById('btnFirst').onclick  = gotoFirst;
document.getElementById('btnPrev10').onclick = () => stepSlice(-10);
document.getElementById('btnPrev').onclick   = () => stepSlice(-1);
document.getElementById('btnPlay').onclick   = togglePlay;
document.getElementById('btnNext').onclick   = () => stepSlice(+1);
document.getElementById('btnNext10').onclick = () => stepSlice(+10);
document.getElementById('btnLast').onclick   = gotoLast;

if (loopCb) loopCb.onchange = e => { loopEnabled = e.target.checked; };

const fpsIn = document.getElementById('fpsInput');
if (fpsIn) fpsIn.onchange = e => {
    fps = Math.max(1, Math.min(30, +e.target.value || 4));
    if (playTimer) { stopPlay(); startPlay(); }
};

// Y-axis unit switch & velocity
const yUnitSel = document.getElementById('yUnitSelect');
if (yUnitSel) yUnitSel.onchange = e => setYAxisUnit(e.target.value);
const btnApplyVel = document.getElementById('btnApplyVelocity');
if (btnApplyVel) btnApplyVel.onclick = applyVelocity;
const velIn = document.getElementById('velocityInput');
if (velIn) velIn.onkeydown = e => {
    if (e.key === 'Enter') applyVelocity();
};

const dirSel = document.getElementById('dirSelect');
if (dirSel) dirSel.onchange = e => {
    curDir = e.target.value;
    curIndex = 0;
    // TimeSlice does not support Wiggle display, switch back to Seismic Color
    if (curDir === 'timeslice' && displayMode === 'wv') {
        displayMode = 'vd';
        const dmSel = document.getElementById('displayMode');
        if (dmSel) dmSel.value = 'vd';
    }
    updateLineRangeLabel();
    loadAndRenderSlice(curDir, curIndex);
    updateAxes();  // update axis labels right after a direction change
};

const lineNoIn = document.getElementById('lineNo');
const btnGo = document.getElementById('btnGoLine');
if (btnGo) btnGo.onclick = () => {
    const v = lineNoIn ? lineNoIn.value : 0;
    gotoSlice(v);
};
if (lineNoIn) {
    lineNoIn.onkeydown = e => {
        if (e.key === 'Enter') gotoSlice(e.target.value);
    };
}

// Slider: 80ms debounce to avoid a request storm on fast drags
const slider = document.getElementById('lineSlider');
let sliderDebounce = null;
if (slider) {
    slider.oninput = e => {
        if (sliderDebounce) clearTimeout(sliderDebounce);
        const v = +e.target.value;
        sliderDebounce = setTimeout(() => gotoSlice(v), 80);
    };
}

// Keyboard: arrow keys / PageUp/PageDown / Home/End / Space
window.addEventListener('keydown', e => {
    const tag = (e.target.tagName || '').toUpperCase();
    if (['INPUT', 'TEXTAREA', 'SELECT'].includes(tag)) return;
    const shift = e.shiftKey;
    switch (e.key) {
        case 'ArrowLeft':  stepSlice(-1);  e.preventDefault(); break;
        case 'ArrowRight': stepSlice(+1);  e.preventDefault(); break;
        case 'PageUp':     stepSlice(-10); e.preventDefault(); break;
        case 'PageDown':   stepSlice(+10); e.preventDefault(); break;
        case 'Home':       gotoFirst();    e.preventDefault(); break;
        case 'End':        gotoLast();     e.preventDefault(); break;
        case ' ':          togglePlay();   e.preventDefault(); break;
        case 'q': case 'Q': adjustGain('up');           e.preventDefault(); break;
        case 'w': case 'W': adjustGain('down');         e.preventDefault(); break;
        case 'z': case 'Z': adjustScale('y', shift ? 'down' : 'up'); e.preventDefault(); break;
        case 't': case 'T': adjustScale('x', shift ? 'down' : 'up'); e.preventDefault(); break;
        case 'f': case 'F': if (!shift) { fitToWindow(); e.preventDefault(); } break;
    }
});

window.addEventListener('load', () => {
    restoreCurrentSgyIfLoaded().catch(err => {
        console.warn('SGY auto-restore failed:', err);
    });
});
