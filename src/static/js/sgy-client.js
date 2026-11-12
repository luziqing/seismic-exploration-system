// sgy-client.js — SGY slice browsing, navigation, pick points
// Extracted from sam.html — contains slice cache, loading, navigation, and canvas interaction

// ── LRU 缓存 ───────────────────────────────────────
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

// 将后端返回的 (可能嵌套的) 2D 列表展平为一维 Float32Array
function flattenSliceData(data, shape) {
    const total = shape[0] * shape[1];
    const out = new Float32Array(total);
    if (Array.isArray(data) && Array.isArray(data[0])) {
        // 嵌套 2D 列表 (Zarr/VDS 当前返回格式)
        for (let i = 0; i < shape[0]; i++) {
            const row = data[i];
            for (let j = 0; j < shape[1]; j++) {
                out[i * shape[1] + j] = row[j];
            }
        }
    } else {
        // 已经是扁平列表
        for (let i = 0; i < total; i++) out[i] = data[i];
    }
    return out;
}

// ── 当前切片最大索引 ──────────────────────────────
function currentMaxIndex() {
    if (curDir === 'inline')     return volInfo.ilCount;
    if (curDir === 'crossline')  return volInfo.xlCount;
    return volInfo.tsCount;
}
function currentSliceKey() { return `${curDir}:${curIndex}`; }

// ── Y 轴单位计算与切换 ───────────────────────────
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

// 切换 Y 轴单位 (带保存提示)
async function setYAxisUnit(unit) {
    if (unit !== 'time' && unit !== 'depth') return;
    if (unit === yAxisUnit) return;
    // 切换前: 提示保存或自动保存当前拾取
    const total = [...picksBySlice.values()].reduce((s, a) => s + a.length, 0);
    if (total > 0) {
        const ok = window.confirm(
            `当前有 ${total} 个未导出的拾取点。\n` +
            `切换 Y 轴单位会改变显示方式。\n\n` +
            `点击"确定"自动保存到数据库后切换;\n` +
            `点击"取消"中止切换。`
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
    setStatus('ready', `Y轴: ${COORD.yLabel}`);
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
        } catch (e) { console.warn('自动保存失败:', e); }
    }
}

function applyVelocity() {
    const velIn = document.getElementById('velocityInput');
    const v = +velIn.value;
    if (!v || v < 100 || v > 20000) {
        setStatus('error', '速度应在 100~20000 m/s');
        return;
    }
    velocity = v;
    if (yAxisUnit === 'depth') {
        syncYAxis();
        updateAxes();
        setStatus('ready', `速度: ${velocity} m/s (depth 已重算)`);
    } else {
        setStatus('ready', `速度: ${velocity} m/s (切到 Depth 时生效)`);
    }
}

// ── 坐标轴动态更新（支持缩放） ─────────────────────
function updateAxes() {
    // Y 轴标签动态更新
    const yLabelEl = document.getElementById('yAxisLabel');
    if (yLabelEl) yLabelEl.textContent = COORD.yLabel;

    // 缩放时: 以画布中心为原点，scaleX/scaleY 放大后，
    // 可见范围 = 原始范围 / scale，中心偏移 50%
    // 可见起始 = 0.5 - 0.5/scale, 可见终止 = 0.5 + 0.5/scale (归一化坐标)
    const xVis0 = 0.5 - 0.5 / scaleX;
    const xVis1 = 0.5 + 0.5 / scaleX;
    const yVis0 = 0.5 - 0.5 / scaleY;
    const yVis1 = 0.5 + 0.5 / scaleY;

    // 顶部 X 轴：根据 curDir 决定横轴显示什么
    const topAxis = document.getElementById('topAxis');
    topAxis.innerHTML = '';
    const nTicks = 6;

    let xLabel = '';
    for (let i = 0; i < nTicks; i++) {
        // 在可见范围内均匀分布刻度
        const t = nTicks > 1 ? i / (nTicks - 1) : 0.5;
        const frac = xVis0 + t * (xVis1 - xVis0);  // 归一化 [0,1] 内的可见位置
        const pct = t * 100;  // 刻度在轴容器上的显示位置百分比
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

    // 左侧 Y 轴：根据 curDir 决定纵轴显示什么
    const leftAxis = document.getElementById('leftAxis');
    leftAxis.querySelectorAll('.tick-label').forEach(el => el.remove());
    const nDepth = 8;

    if (curDir === 'timeslice') {
        // TimeSlice: 纵轴 = Inline
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
        // Inline/Crossline: 纵轴 = Time 或 Depth
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
}

// 后端切片 URL 适配: Zarr 与 VDS 接口一致
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
    setStatus('ready', `SGY: ${info.filename}  IL ${volInfo.ilMin}~${volInfo.ilMax}  当前 Inline ${volInfo.ilMin + curIndex}`);
    return true;
}

async function fetchSlice(source, name, dir, index) {
    const resp = await fetch(sliceApiUrl(source, name, dir, index));
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    // 二进制 float32 响应: shape 从响应头读取
    const rows = parseInt(resp.headers.get('X-Rows') || '0');
    const cols = parseInt(resp.headers.get('X-Cols') || '0');
    const buf = await resp.arrayBuffer();
    const data = new Float32Array(buf);
    if (rows && cols) {
        return { shape: [rows, cols], data };
    }
    // fallback: JSON 响应 (兼容旧 zarr 端点)
    try {
        const json = JSON.parse(new TextDecoder().decode(buf));
        return json;
    } catch { return { shape: [data.length, 1], data }; }
}

// 主入口: 加载并渲染一条切片
async function loadAndRenderSlice(dir, index) {
    if (!volInfo.name) {
        setStatus('idle', '请先加载 SGY/VDS');
        return;
    }
    if (isLoading) { pendingIdx = {dir, index}; return; }
    isLoading = true;
    setStatus('loading', `加载 ${dir} ${index}...`);

    const key = `${dir}:${index}`;
    try {
        let payload = cacheGet(sliceCache, key);
        if (!payload) {
            payload = await fetchSlice(volInfo.source, volInfo.name, dir, index);
            cachePut(sliceCache, key, payload, SLICE_CACHE_SIZE);
        }
        const rows = payload.shape[0], cols = payload.shape[1];
        // 二进制响应已直接是 Float32Array, 无需 flatten
        const data = (payload.data instanceof Float32Array && payload.data.length === rows * cols)
            ? payload.data
            : flattenSliceData(payload.data, payload.shape);
        renderSliceToCanvas(data, rows, cols);
        // 同步坐标范围 (用于 mousemove 拾取坐标显示)
        syncCoordFromSlice(dir, index);
        updateAxes();  // 更新坐标轴标注，确保 IL/XL 范围正确显示
        // logits 切换: 新切片清旧 mask 和 embedding
        logitsMap = null; logitsWidth = 0; logitsHeight = 0;
        embeddingId = null;  // 新切片需要重新计算 embedding
        drawSeismic();
        loadVolumeMaskOverlay(dir, index);  // 若该切片已有体 mask (含传播结果) 则叠加显示
        updateSubtitle(dir, index);
        updateLineControls(index);
        // 创建新拾取会话
        currentSessionId = null;
        fetch('/api/db/session?slice_id=0', {method: 'POST'})
            .then(r => r.json()).then(d => { currentSessionId = d.session_id; })
            .catch(() => {});
        setStatus('ready', `${dir} ${index}  缓存 ${sliceCache.size}/${SLICE_CACHE_SIZE}  [${rows}×${cols}] clip=${currentClip.toFixed(0)}`);
    } catch (e) {
        setStatus('error', `加载失败: ${e.message}`);
    } finally {
        isLoading = false;
        if (pendingIdx) {
            const p = pendingIdx; pendingIdx = null;
            loadAndRenderSlice(p.dir, p.index);
        }
    }
}

// 同步 COORD 以便拾取时正确反算 IL/XL/Depth
function syncCoordFromSlice(dir, index) {
    if (dir === 'inline') {
        // Inline 剖面：index 是 IL 下标，横轴是 Crossline 范围
        COORD.ilMin = volInfo.ilMin;
        COORD.ilMax = volInfo.ilMax;
        COORD.xl = volInfo.ilMin + index;  // 当前 Inline 编号
        COORD.crossMin = volInfo.xlMin;
        COORD.crossMax = volInfo.xlMax;
    } else if (dir === 'crossline') {
        // Crossline 剖面：index 是 XL 下标，横轴是 Inline 范围
        COORD.ilMin = volInfo.ilMin;
        COORD.ilMax = volInfo.ilMax;
        COORD.xl = volInfo.xlMin + index;  // 当前 Crossline 编号
        COORD.crossMin = volInfo.ilMin;
        COORD.crossMax = volInfo.ilMax;
    } else {
        // TimeSlice: 横轴 XL, 纵轴 IL, depth 固定
        COORD.crossMin = volInfo.xlMin;
        COORD.crossMax = volInfo.xlMax;
    }
    syncYAxis();
}

// ════════════════════════════════════════════════════
// 导航
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
// 播放控制
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
// UI 更新
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
    sub.textContent = `${labels[dir]} ${coordVal}  (vol=${volName})  本切片 ${n} 点 / 累计 ${total}`;
}
function updateLineControls(idx) {
    const slider = document.getElementById('lineSlider');
    if (slider && +slider.value !== idx) slider.value = idx;
    const lineNo = document.getElementById('lineNo');
    if (lineNo && document.activeElement !== lineNo) lineNo.value = idx;
    const max = currentMaxIndex();
    const posLabel = document.getElementById('slicePosLabel');
    // 显示方向 + 当前线号 (实际 IL/XL/TS 值)
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
// 交互事件
// ════════════════════════════════════════════════════

canvas.addEventListener('mousemove', e => {
    const r = canvas.getBoundingClientRect();
    const x = e.clientX - r.left, y = e.clientY - r.top;
    const w = canvas.width, h = canvas.height;
    // 横轴坐标: inline→XL, crossline→IL, timeslice→XL
    const crossVal = Math.round(COORD.crossMin + (x/w)*(COORD.crossMax-COORD.crossMin));
    // 纵轴: 剖面→Time/Depth, timeslice→IL
    const yVal = (COORD.yTop + (y/h)*COORD.yRange).toFixed(1);
    // 振幅值
    let amp = 'N/A';
    if (currentSliceData && currentSliceShape) {
        const [rows, cols] = currentSliceShape;
        const sy = Math.min(rows-1, Math.floor(y/h*rows));
        const sx = Math.min(cols-1, Math.floor(x/w*cols));
        amp = currentSliceData[sy*cols+sx].toFixed(1);
    }
    // Logits 值
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
    const x = e.clientX - r.left, y = e.clientY - r.top;
    // 反算 IL/XL/Y (基于当前 COORD, Y 跟随 yAxisUnit)
    let il, xl, yVal;
    let time_ms = 0, depth_m = 0;
    if (curDir === 'inline') {
        const crossPct = x / canvas.width;
        const yPct = y / canvas.height;
        xl = (COORD.crossMin + crossPct * (COORD.crossMax - COORD.crossMin)).toFixed(2);
        il = (volInfo.ilMin + curIndex).toFixed(0);
        time_ms = +(COORD.yTop - yPct * COORD.yRange).toFixed(2);
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
        time_ms = +(COORD.yTop - yPct * COORD.yRange).toFixed(2);
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
    const nx = x / canvas.width, ny = y / canvas.height;  // 归一化坐标, 跟随缩放
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

    // 存入数据库 (depth 字段跟随当前单位,便于后续分析)
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

// ── 底部备份状态更新 ─────────────────────────────────
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
        const ageStr = age < 60000 ? '刚刚'
                     : age < 3600000 ? Math.floor(age / 60000) + '分钟前'
                     : Math.floor(age / 3600000) + '小时前';
        const vol = snap.volName ? ` [${snap.volName}]` : '';
        el.textContent = `💾 ${total} 点${vol} · ${ageStr}`;
    } catch { el.textContent = ''; }
}

// ════════════════════════════════════════════════════
// SGY 加载 & 切片生成
// ════════════════════════════════════════════════════

btnLoadSGY.onclick = () => sgyFileInput.click();
sgyFileInput.onchange = async e => {
    const file = e.target.files[0]; if (!file) return;
    setStatus('loading', '上传 SGY 中...');
    const form = new FormData(); form.append('file', file);
    try {
        const resp = await fetch('/api/sgy/upload', {method: 'POST', body: form});
        if (!resp.ok) throw new Error((await resp.json()).detail);
        const info = await resp.json();
        // 填充卷信息
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
        // 默认渲染中间一条 inline
        curDir = 'inline';
        curIndex = Math.floor(volInfo.ilCount / 2);
        // dirSelect / fpsInput / loopCb / yUnitSelect 同步
        const dirSel = document.getElementById('dirSelect');
        if (dirSel) dirSel.value = curDir;
        const fpsIn = document.getElementById('fpsInput');
        if (fpsIn) fpsIn.value = fps;
        const loopChk = document.getElementById('loopCb');
        if (loopChk) loopChk.checked = loopEnabled;
        updateLineRangeLabel();
        // 打开 SGY 后立即显示滚动浏览条
        slicePanel.classList.add('visible');
        // 清旧拾取
        picksBySlice.clear();
        clearBackup();
        // 触发首次加载：默认渲染中间一条 inline
        await loadAndRenderSlice(curDir, curIndex);
        btnGenSlices.disabled = false;
        setStatus('ready', `SGY: ${info.filename}  IL ${volInfo.ilMin}~${volInfo.ilMax}  当前 Inline ${volInfo.ilMin + curIndex}`);
    } catch (e) { setStatus('error', 'SGY 加载失败: ' + e.message); }
    e.target.value = '';
};

// 加载本地图片
btnLoadImage.onclick = () => imageFileInput.click();
imageFileInput.onchange = e => {
    const file = e.target.files[0];
    if (!file) return;
    const url = URL.createObjectURL(file);
    window.open(url, '_blank', 'noopener');
    e.target.value = '';
};

// ── 加载 VDS 卷数据（OpenVDS） ─────────────────────────────
const btnLoadVDS = document.getElementById('btnLoadVDS');
const vdsFileInput = document.getElementById('vdsFileInput');

// 启动时检查 OpenVDS 是否可用；不可用则禁用按钮并给出提示
(async function checkVdsAvailability() {
    if (!btnLoadVDS) return;
    try {
        const resp = await fetch('/api/vds/status');
        const data = await resp.json();
        if (!data.available) {
            btnLoadVDS.disabled = true;
            btnLoadVDS.title = 'OpenVDS 未安装 (pip install openvds)，暂不可用';
            btnLoadVDS.style.opacity = '0.5';
        }
    } catch { /* 状态检查失败时不禁用，交由上传时反馈 */ }
})();

if (btnLoadVDS) btnLoadVDS.onclick = () => vdsFileInput.click();
if (vdsFileInput) vdsFileInput.onchange = async e => {
    const file = e.target.files[0];
    if (!file) return;
    setStatus('loading', '上传 VDS 中...');
    const form = new FormData();
    form.append('file', file);
    try {
        const resp = await fetch('/api/vds/upload', { method: 'POST', body: form });
        if (!resp.ok) throw new Error((await resp.json()).detail || `HTTP ${resp.status}`);
        const info = await resp.json();
        // 复用通用卷激活流程，source 指定为 api/vds（切片读取走 /api/vds/{name}/slice/...）
        await activateVolume(info, info.filename, { source: 'api/vds' });
        setStatus('ready', `VDS: ${info.filename}  IL ${volInfo.ilMin}~${volInfo.ilMax}  当前 Inline ${volInfo.ilMin + curIndex}`);
    } catch (err) {
        setStatus('error', 'VDS 加载失败: ' + err.message);
    } finally {
        e.target.value = '';
    }
};

// ── 生成切片弹窗逻辑 ─────────────────────────────────
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

// 按间隔 + 范围生成索引列表
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
            `${ilMin}~${ilMax}, 共 ${indices.length} 条`;
        total += indices.length;
    } else {
        document.getElementById('genILPreview').textContent = '';
    }
    // Crossline
    if (xlOn) {
        const xlMin = volInfo.xlMin, xlMax = volInfo.xlMax;
        const indices = buildIndices(xlMin, xlMax, xlStep, genXLFrom.value, genXLTo.value);
        document.getElementById('genXLPreview').textContent =
            `${xlMin}~${xlMax}, 共 ${indices.length} 条`;
        total += indices.length;
    } else {
        document.getElementById('genXLPreview').textContent = '';
    }
    // TimeSlice
    if (tsOn) {
        const tsMin = 0, tsMax = Math.round((volInfo.tsCount - 1) * (volInfo.dtUs || 1000) / 1000);
        const indices = buildIndices(tsMin, tsMax, tsStep, genTSFrom.value, genTSTo.value);
        document.getElementById('genTSPreview').textContent =
            `${tsMin}~${tsMax}ms, 共 ${indices.length} 条`;
        total += indices.length;
    } else {
        document.getElementById('genTSPreview').textContent = '';
    }

    document.getElementById('genTotalPreview').textContent =
        total > 0 ? `合计: ${total} 张切片` : '请至少选择一种切片类型';
    document.getElementById('genModalOK').disabled = total === 0;
}

// 绑定预览更新
[genIL, genXL, genTS, genILStep, genXLStep, genTSStep,
 genILFrom, genILTo, genXLFrom, genXLTo, genTSFrom, genTSTo
].forEach(el => el.addEventListener('input', updateGenPreview));

// 打开弹窗
btnGenSlices.onclick = () => {
    if (!volInfo.name) { setStatus('error', '请先加载 SGY'); return; }
    // 用当前卷范围填充默认值
    genILFrom.placeholder = String(volInfo.ilMin);
    genILTo.placeholder = String(volInfo.ilMax);
    genXLFrom.placeholder = String(volInfo.xlMin);
    genXLTo.placeholder = String(volInfo.xlMax);
    const tsMax = Math.round((volInfo.tsCount - 1) * (volInfo.dtUs || 1000) / 1000);
    genTSFrom.placeholder = '0';
    genTSTo.placeholder = String(tsMax);
    // 清空自定义范围 (保留上次的间隔设置)
    genILFrom.value = ''; genILTo.value = '';
    genXLFrom.value = ''; genXLTo.value = '';
    genTSFrom.value = ''; genTSTo.value = '';
    updateGenPreview();
    genModal.style.display = 'flex';
};

// 关闭弹窗
document.getElementById('genModalClose').onclick = () => genModal.style.display = 'none';
document.getElementById('genModalCancel').onclick = () => genModal.style.display = 'none';
genModal.addEventListener('click', e => {
    if (e.target === genModal) genModal.style.display = 'none';
});

// 确定生成
document.getElementById('genModalOK').onclick = async () => {
    genModal.style.display = 'none';
    setStatus('loading', '生成切片中...');

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
        if (!resp.ok) throw new Error((await resp.json()).detail);
        const data = await resp.json();
        const parts = [];
        if (data.slices.inline) parts.push(`IL×${data.slices.inline.length}`);
        if (data.slices.crossline) parts.push(`XL×${data.slices.crossline.length}`);
        if (data.slices.timeslice) parts.push(`TS×${data.slices.timeslice.length}`);
        setStatus('ready', `已生成 ${data.generated} 张切片 (${parts.join(' + ')})`);
        slicePanel.classList.add('visible');
    } catch(e) { setStatus('error', '切片生成失败: ' + e.message); }
};

// ── 📥 Import CSV — 导入之前导出的 CSV 文件 ──────────
document.getElementById('btnImportCSV').onclick = () => csvFileInput.click();
csvFileInput.onchange = async e => {
    const file = e.target.files[0];
    if (!file) return;
    try {
        const text = await file.text();
        const lines = text.trim().split('\n');
        if (lines.length < 2) throw new Error('CSV 为空');

        // 解析表头, 确定列索引
        const header = lines[0].split(',').map(h => h.trim());
        const colIdx = {};
        header.forEach((h, i) => { colIdx[h.toLowerCase()] = i; });

        // 必需列检查
        const required = ['slicekey', 'inline', 'crossline', 'label', 'color'];
        for (const col of required) {
            if (!(col in colIdx)) throw new Error(`CSV 缺少必需列: ${col}`);
        }

        // 确定 Y 值列: 优先 Depth_m, 其次 Time_ms
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

            // Y 值解析
            const unit = yUnitCol >= 0 ? cols[yUnitCol] : (hasDepth ? 'depth' : 'time');
            let time_ms = 0, depth_m = 0;
            if (yCol >= 0) {
                const yVal = parseFloat(cols[yCol]) || 0;
                if (unit === 'depth') { depth_m = yVal; time_ms = depth_m * 2000 / velocity; }
                else { time_ms = yVal; depth_m = time_ms * velocity / 2 / 1000; }
            }

            // 解析切片方向和索引
            const parts = sliceKey.split(':');
            const dir = parts[0] || 'inline';
            const idx = parseInt(parts[1]) || 0;

            const point = {
                x: 0, y: 0,  // 像素坐标无法从 CSV 恢复, 标记为 0
                il: String(il), xl: String(xl),
                time_ms, depth_m,
                yUnit: unit, color, label, sliceKey,
            };
            if (!imported.has(sliceKey)) imported.set(sliceKey, []);
            imported.get(sliceKey).push(point);
        }

        // 确认导入
        const total = [...imported.values()].reduce((s, a) => s + a.length, 0);
        if (total === 0) throw new Error('CSV 中没有有效数据行');

        const msg = `即将导入 ${total} 个拾取点 (${imported.size} 条切片)` +
                    (skipped > 0 ? `\n跳过 ${skipped} 行格式异常` : '') +
                    `\n\n这将替换当前所有拾取点，是否继续？`;
        if (!confirm(msg)) return;

        // 替换 picksBySlice
        picksBySlice.clear();
        imported.forEach((pts, key) => picksBySlice.set(key, pts));
        saveToLocalStorage();
        drawSeismic();
        updateSubtitle(curDir, curIndex);
        setStatus('ready', `📥 已导入 ${total} 个拾取点`);
    } catch (e) {
        setStatus('error', 'CSV 导入失败: ' + e.message);
    }
    e.target.value = '';
};

// ════════════════════════════════════════════════════
// 浏览控制事件绑定 (按钮 / 滑块 / 方向 / 键盘)
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

// Y 轴单位切换 & 速度
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
    // TimeSlice 不支持 Wiggle 波形显示，自动切回 Seismic Color
    if (curDir === 'timeslice' && displayMode === 'wv') {
        displayMode = 'vd';
        const dmSel = document.getElementById('displayMode');
        if (dmSel) dmSel.value = 'vd';
    }
    updateLineRangeLabel();
    loadAndRenderSlice(curDir, curIndex);
    updateAxes();  // 方向切换后立即更新坐标轴标注
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

// 滑块: 80ms 去抖,避免快速拖动触发请求风暴
const slider = document.getElementById('lineSlider');
let sliderDebounce = null;
if (slider) {
    slider.oninput = e => {
        if (sliderDebounce) clearTimeout(sliderDebounce);
        const v = +e.target.value;
        sliderDebounce = setTimeout(() => gotoSlice(v), 80);
    };
}

// 键盘: 方向键 / PageUp/PageDown / Home/End / Space
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
        console.warn('SGY 自动恢复失败:', err);
    });
});
