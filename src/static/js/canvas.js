// canvas.js - simple seismic rendering

function estimateClip(data, sampleSize = 5000) {
    const n = data.length;
    const step = Math.max(1, Math.floor(n / sampleSize));
    const samples = [];
    for (let i = 0; i < n; i += step) samples.push(Math.abs(data[i]));
    samples.sort((a, b) => a - b);
    return samples[Math.floor(samples.length * 0.99)] || 1.0;
}

let _fpsFrames = 0, _fpsLast = 0, _fpsValue = 0;

// 增益/减益控制: clip 越小 → 波形越大(增益), clip 越大 → 波形越小(减益)
const GAIN_STEP = 0.7;  // 每次增益/减益倍率
const SCALE_STEP = 1.2; // 每次缩放倍率

// 用户增益偏移倍率: 1.0 = 无偏移, <1 = 已增益, >1 = 已减益
let userGainFactor = 1.0;

function adjustGain(direction) {
    if (!currentSliceData) return;
    const oldFactor = userGainFactor;
    if (direction === 'up') {
        userGainFactor = Math.max(0.001, userGainFactor * GAIN_STEP);
    } else {
        userGainFactor = userGainFactor / GAIN_STEP;
    }
    // 重算 clip = 自动估值 × 用户偏移
    const baseClip = estimateClip(currentSliceData) || 1.0;
    currentClip = baseClip * userGainFactor;
    redrawAll();
    const gainDb = 20 * Math.log10(1.0 / userGainFactor);
    setStatus('ready', `增益 ${direction === 'up' ? '+' : ''}${gainDb.toFixed(1)} dB  clip=${currentClip.toFixed(2)}`);
}

function adjustScale(axis, direction) {
    if (!currentSliceData) return;
    const factor = direction === 'up' ? SCALE_STEP : (1 / SCALE_STEP);
    if (axis === 'y') {
        scaleY = Math.max(0.1, Math.min(10, scaleY * factor));
        setStatus('ready', `纵向缩放 ×${scaleY.toFixed(2)}`);
    } else {
        scaleX = Math.max(0.1, Math.min(10, scaleX * factor));
        setStatus('ready', `横向缩放 ×${scaleX.toFixed(2)}`);
    }
    redrawAll();
    if (typeof updateAxes === 'function') updateAxes();
}

function fitToWindow() {
    scaleY = 1.0;
    scaleX = 1.0;
    redrawAll();
    if (typeof updateAxes === 'function') updateAxes();
    setStatus('ready', '🔲 自适应窗口 ×1.00');
}

function redrawAll() {
    if (displayMode === 'wv') {
        drawSeismic();
    } else if (currentSliceData && currentSliceShape) {
        _renderSliceCanvas2D(currentSliceData, currentSliceShape[0], currentSliceShape[1]);
        drawSeismic();
    }
}
function _fpsTick() {
    _fpsFrames++;
    const now = performance.now();
    if (now - _fpsLast >= 1000) {
        _fpsValue = _fpsFrames;
        _fpsFrames = 0;
        _fpsLast = now;
        const el = document.getElementById('fpsCounter');
        if (el) el.textContent = `${_fpsValue} fps`;
    }
}

function _renderSliceCanvas2D(data, rows, cols) {
    const w = canvas.width, h = canvas.height;
    const clip = currentClip || 1.0;
    const id = ctx.createImageData(w, h);
    const px = id.data;

    for (let y = 0; y < h; y++) {
        const fy = y / h * (rows - 1);
        const sy0 = Math.floor(fy);
        const sy1 = Math.min(rows - 1, sy0 + 1);
        const dy = fy - sy0;
        for (let x = 0; x < w; x++) {
            const fx = x / w * (cols - 1);
            const sx0 = Math.floor(fx);
            const sx1 = Math.min(cols - 1, sx0 + 1);
            const dx = fx - sx0;
            const v = (data[sy0 * cols + sx0] * (1 - dx) * (1 - dy) +
                       data[sy0 * cols + sx1] * dx * (1 - dy) +
                       data[sy1 * cols + sx0] * (1 - dx) * dy +
                       data[sy1 * cols + sx1] * dx * dy) / clip;
            const t = Math.max(-1, Math.min(1, v));
            const off = (y * w + x) * 4;
            if (t >= 0) {
                px[off] = 255;
                px[off + 1] = Math.floor(255 * (1 - t));
                px[off + 2] = Math.floor(255 * (1 - t));
            } else {
                px[off] = Math.floor(255 * (1 + t));
                px[off + 1] = Math.floor(255 * (1 + t));
                px[off + 2] = 255;
            }
            px[off + 3] = 255;
        }
    }

    ctx.putImageData(id, 0, 0);
    seismicImageData = id;
}

function renderSliceToCanvas(data, rows, cols) {
    currentSliceData = data;
    currentSliceShape = [rows, cols];
    // 保留用户增益偏移: 自动估值 × 用户倍率
    const baseClip = estimateClip(data) || 1.0;
    currentClip = baseClip * userGainFactor;

    if (displayMode === 'wv') {
        const w = canvas.width, h = canvas.height;
        const id = ctx.createImageData(w, h);
        for (let i = 0; i < id.data.length; i += 4) {
            id.data[i] = 255;
            id.data[i + 1] = 255;
            id.data[i + 2] = 255;
            id.data[i + 3] = 255;
        }
        ctx.putImageData(id, 0, 0);
        seismicImageData = id;
        return;
    }

    _renderSliceCanvas2D(data, rows, cols);
}

function drawWiggle(ctx, data, rows, cols, w, h, clip) {
    if (!data || !rows || !cols || !clip) return;
    const traceSpacing = w / cols;
    const step = traceSpacing < 1.5 ? Math.ceil(1.5 / traceSpacing) : 1;

    ctx.save();
    ctx.lineWidth = Math.max(0.5, Math.min(1.5, traceSpacing * 0.15));

    for (let tr = 0; tr < cols; tr += step) {
        const cx = (tr + 0.5) * traceSpacing;
        const halfW = Math.min(traceSpacing * 0.45, 10);

        ctx.beginPath();
        for (let sy = 0; sy < rows; sy++) {
            const py = (sy + 0.5) / rows * h;
            ctx.lineTo(cx + Math.max(0, data[sy * cols + tr] / clip) * halfW, py);
        }
        for (let sy = rows - 1; sy >= 0; sy--) ctx.lineTo(cx, (sy + 0.5) / rows * h);
        ctx.closePath();
        ctx.fillStyle = 'rgba(0,0,0,0.85)';
        ctx.fill();

        ctx.beginPath();
        for (let sy = 0; sy < rows; sy++) {
            const py = (sy + 0.5) / rows * h;
            const amp = Math.max(-1, Math.min(1, data[sy * cols + tr] / clip));
            if (sy === 0) ctx.moveTo(cx + amp * halfW, py);
            else ctx.lineTo(cx + amp * halfW, py);
        }
        ctx.strokeStyle = 'rgba(0,0,0,0.85)';
        ctx.stroke();
    }
    ctx.restore();
}

function _drawLogitsCanvas2D(w, h) {
    if (!logitsMap || !logitsMode) return;
    const tc = document.createElement('canvas');
    tc.width = logitsWidth;
    tc.height = logitsHeight;
    const tctx = tc.getContext('2d');
    const id2 = tctx.createImageData(logitsWidth, logitsHeight);
    for (let i = 0; i < logitsMap.length; i++) {
        const v = logitsMap[i];
        if (v > 0.3) {
            const t = Math.pow((v - 0.3) / 0.7, 0.8);
            id2.data[i * 4] = 0;
            id2.data[i * 4 + 1] = Math.floor(255 * t);
            id2.data[i * 4 + 2] = Math.floor(60 * t);
            id2.data[i * 4 + 3] = Math.floor(t * 180);
        }
    }
    tctx.putImageData(id2, 0, 0);
    ctx.drawImage(tc, 0, 0, w, h);
}

function drawSeismic() {
    const w = canvas.width, h = canvas.height;
    ctx.clearRect(0, 0, w, h);

    // 应用缩放: 以画布中心为原点
    ctx.save();
    const cx = w / 2, cy = h / 2;
    ctx.translate(cx, cy);
    ctx.scale(scaleX, scaleY);
    ctx.translate(-cx, -cy);

    if (currentSliceData && currentSliceShape) {
        if (seismicImageData) {
            const tc = document.createElement('canvas');
            tc.width = seismicImageData.width;
            tc.height = seismicImageData.height;
            tc.getContext('2d').putImageData(seismicImageData, 0, 0);
            ctx.drawImage(tc, 0, 0, w, h);
        } else {
            _renderSliceCanvas2D(currentSliceData, currentSliceShape[0], currentSliceShape[1]);
        }
    } else {
        ctx.fillStyle = '#888';
        ctx.fillRect(0, 0, w, h);
        ctx.fillStyle = 'white';
        ctx.font = '14px sans-serif';
        ctx.fillText('请加载 SGY/VDS 数据...', w / 2 - 60, h / 2);
    }

    if (displayMode === 'wv' && currentSliceData && currentSliceShape && curDir !== 'timeslice') {
        drawWiggle(ctx, currentSliceData, currentSliceShape[0], currentSliceShape[1], w, h, currentClip);
    }

    if (logitsMap && logitsMode) {
        _drawLogitsCanvas2D(w, h);
    }

    const curKey = currentSliceKey();
    picksBySlice.forEach((pts, sliceKey) => {
        const isCurrent = sliceKey === curKey;
        pts.forEach(p => {
            const px = (p.nx != null) ? p.nx * w : p.x;
            const py = (p.ny != null) ? p.ny * h : p.y;
            ctx.fillStyle = isCurrent ? p.color : 'rgba(128,128,128,0.35)';
            ctx.fillRect(px - 3, py - 3, 6, 6);
            ctx.strokeStyle = isCurrent ? 'black' : 'rgba(0,0,0,0.3)';
            ctx.lineWidth = 1;
            ctx.strokeRect(px - 3, py - 3, 6, 6);
        });
    });

    ctx.restore();
    _fpsTick();
}
