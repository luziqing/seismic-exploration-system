// sam-client.js — SAM3 embedding, inference, mask export

// ═══════════════════════════════════════════════════════
// SAM 嵌入 & 推理
// ═══════════════════════════════════════════════════════

async function computeEmbedding() {
    try {
        setStatus('loading', '计算嵌入中...');
        // 用 canvas 当前内容生成 blob (支持任意来源的图片)
        const tempC = document.createElement('canvas');
        tempC.width = seismicImage.naturalWidth || canvas.width;
        tempC.height = seismicImage.naturalHeight || canvas.height;
        tempC.getContext('2d').drawImage(seismicImage, 0, 0, tempC.width, tempC.height);
        const blob = await new Promise(r => tempC.toBlob(r, 'image/png'));
        const form = new FormData();
        form.append('file', blob, 'slice.png');
        const resp = await fetch('/api/embed', {method:'POST', body:form});
        if (!resp.ok) throw new Error((await resp.json()).detail);
        const data = await resp.json();
        embeddingId = data.embedding_id;
        setStatus('ready', 'SAM3 就绪');
    } catch(e) {
        setStatus('error', '嵌入失败: ' + e.message);
    }
}

// ═══════════════════════════════════════════════════════
// SAM 推理
// ═══════════════════════════════════════════════════════

async function runSAMInference() {
    if (!samEnabled) { setStatus('error', 'SAM 模式未启用'); return; }
    if (isInferring) { setStatus('loading', '⏳ SAM 推理进行中，请等待...'); return; }

    // 获取当前切片的拾取点
    const curKey = currentSliceKey();
    const picks = picksBySlice.get(curKey) || [];
    if (picks.length === 0) {
        setStatus('error', '请先拾取 Include/Exclude 点');
        return;
    }

    isInferring = true;
    setStatus('loading', '⏳ SAM 推理中...');

    try {
        // 1. 如果没有 embedding，先自动计算当前 canvas 内容的 embedding
        if (!embeddingId) {
            setStatus('loading', '📐 计算图像嵌入...');
            const tempC = document.createElement('canvas');
            tempC.width = canvas.width;
            tempC.height = canvas.height;
            tempC.getContext('2d').drawImage(canvas, 0, 0);
            const blob = await new Promise(r => tempC.toBlob(r, 'image/png'));
            const form = new FormData();
            form.append('file', blob, 'slice.png');
            const resp = await fetch('/api/embed', {method:'POST', body:form});
            if (!resp.ok) throw new Error((await resp.json()).detail);
            const data = await resp.json();
            embeddingId = data.embedding_id;
            setStatus('loading', '✅ 嵌入完成，开始推理...');
        }

        // 2. 将拾取点坐标映射到图像像素坐标 (归一化坐标 × 当前 canvas)
        const imgW = canvas.width;
        const imgH = canvas.height;
        const points = picks.map(p => {
            if (p.nx != null) return [p.nx * imgW, p.ny * imgH];
            return [p.x, p.y];
        });
        const labels = picks.map(p => p.label);

        setStatus('loading', `🧠 推理中 (${picks.length} 点)...`);

        // 3. 调用后端 predict
        const resp = await fetch('/api/predict', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({embedding_id:embeddingId, points, labels})
        });
        if (!resp.ok) throw new Error((await resp.json()).detail);
        const result = await resp.json();

        // 4. 存储 logits
        setStatus('loading', '🎨 渲染分割结果...');
        logitsHeight = result.mask_shape[0];
        logitsWidth = result.mask_shape[1];
        logitsMap = new Float32Array(result.mask.flat());
        window._lastSamScore = result.scores[0] || 0;  // 供 AI 分析读取
        drawSeismic();

        // 5. 保存结果到数据库
        setStatus('loading', '💾 保存结果...');
        if (currentSessionId) {
            await fetch(`/api/db/session/${currentSessionId}/sam_result`, {
                method:'POST',
                headers:{'Content-Type':'application/json'},
                body: JSON.stringify({mask_path:'', score:result.scores[0], mask_shape:result.mask_shape})
            });
        }
        setStatus('ready', `✅ SAM 完成 · Score: ${result.scores[0].toFixed(3)} · ${picks.length} 点`);
    } catch(e) {
        setStatus('error', '推理失败: ' + e.message);
    } finally { isInferring = false; }
}

// ═══════════════════════════════════════════════════════
// Mask 导出 (GeoJSON + CSV 多边形)
// ═══════════════════════════════════════════════════════

function exportMaskAsContour() {
    if (!logitsMap || !logitsWidth || !logitsHeight) {
        setStatus('error', '请先运行 SAM 推理生成 mask');
        return;
    }

    // 从 logits 提取二值轮廓 (阈值 0.5)
    setStatus('loading', '📐 提取轮廓中...');
    const threshold = 0.5;
    const contours = extractContours(logitsMap, logitsWidth, logitsHeight, threshold);
    if (contours.length === 0) {
        setStatus('error', 'mask 未检测到有效轮廓');
        return;
    }

    // 将像素坐标转换为 IL/XL 坐标
    setStatus('loading', '🔄 转换坐标并生成 GeoJSON...');
    let geoContours;
    try {
        geoContours = contours.map(ring => ring.map(([px, py]) => {
            const xPct = px / logitsWidth;
            const yPct = py / logitsHeight;
            let il, xl;
            if (curDir === 'inline') {
                xl = COORD.crossMin + xPct * (COORD.crossMax - COORD.crossMin);
                il = volInfo.ilMin + curIndex;
            } else if (curDir === 'crossline') {
                il = COORD.crossMin + xPct * (COORD.crossMax - COORD.crossMin);
                xl = volInfo.xlMin + curIndex;
            } else {
                xl = COORD.crossMin + xPct * (COORD.crossMax - COORD.crossMin);
                il = volInfo.ilMin + yPct * (volInfo.ilMax - volInfo.ilMin);
            }
            const depth = curDir === 'timeslice'
                ? curIndex
                : (COORD.yTop + yPct * COORD.yRange);
            return { il: +il.toFixed(2), xl: +xl.toFixed(2), depth: +depth.toFixed(2) };
        }));
    } catch (e) {
        setStatus('error', '坐标转换失败: ' + e.message);
        return;
    }

    // 构建 GeoJSON FeatureCollection
    const features = geoContours.map((ring, i) => ({
        type: 'Feature',
        properties: {
            id: i,
            slice_key: currentSliceKey(),
            direction: curDir,
            index: curIndex,
            area_pixels: contourArea(ring),
        },
        geometry: {
            type: 'Polygon',
            coordinates: [ring.map(p => [p.il, p.xl, p.depth])],
        }
    }));
    const geojson = {
        type: 'FeatureCollection',
        properties: {
            volume: volInfo.name,
            source: 'SAM3',
            threshold: threshold,
            timestamp: new Date().toISOString(),
        },
        features,
    };

    // 导出 GeoJSON
    setStatus('loading', '📦 生成下载文件...');
    const blob = new Blob([JSON.stringify(geojson, null, 2)], {type: 'application/geo+json'});
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `sam_mask_${volInfo.name || 'unknown'}_${currentSliceKey().replace(':','')}.geojson`;
    a.click();

    // 同时导出 CSV 轮廓点
    let csv = `ContourID,Inline,Crossline,Depth,Direction\n`;
    geoContours.forEach((ring, i) => {
        ring.forEach(p => {
            csv += `${i},${p.il},${p.xl},${p.depth},${curDir}\n`;
        });
    });
    const csvBlob = new Blob([csv], {type: 'text/csv'});
    const a2 = document.createElement('a');
    a2.href = URL.createObjectURL(csvBlob);
    a2.download = `sam_mask_${volInfo.name || 'unknown'}_${currentSliceKey().replace(':','')}.csv`;
    a2.click();

    setStatus('ready', `✅ 📐 已导出 ${contours.length} 个多边形轮廓 (GeoJSON + CSV)`);
}

// ═══════════════════════════════════════════════════════
// Marching Squares 轮廓提取
// ═══════════════════════════════════════════════════════

function extractContours(data, w, h, threshold) {
    // 二值化
    const bin = new Uint8Array(w * h);
    for (let i = 0; i < w * h; i++) bin[i] = data[i] >= threshold ? 1 : 0;

    // 边界追踪: 找所有连通区域的外轮廓
    const visited = new Uint8Array(w * h);
    const contours = [];

    for (let y = 0; y < h; y++) {
        for (let x = 0; x < w; x++) {
            const idx = y * w + x;
            if (bin[idx] && !visited[idx]) {
                // BFS 标记连通区域, 同时收集边界像素
                const region = [];
                const boundary = [];
                const queue = [idx];
                visited[idx] = 1;
                while (queue.length) {
                    const ci = queue.shift();
                    region.push(ci);
                    const cx = ci % w, cy = (ci / w) | 0;
                    let isBoundary = false;
                    for (const [dx, dy] of [[-1,0],[1,0],[0,-1],[0,1]]) {
                        const nx = cx + dx, ny = cy + dy;
                        if (nx < 0 || nx >= w || ny < 0 || ny >= h) { isBoundary = true; continue; }
                        const ni = ny * w + nx;
                        if (!bin[ni]) { isBoundary = true; continue; }
                        if (!visited[ni]) { visited[ni] = 1; queue.push(ni); }
                    }
                    if (isBoundary) boundary.push([cx, cy]);
                }
                if (boundary.length >= 6) {
                    // 对边界点排序形成环 (按角度排序)
                    const ring = orderBoundaryRing(boundary);
                    contours.push(ring);
                }
            }
        }
    }
    // 按面积降序排列
    contours.sort((a, b) => contourArea(b) - contourArea(a));
    return contours;
}

function orderBoundaryRing(pts) {
    // 计算质心
    let cx = 0, cy = 0;
    pts.forEach(([x, y]) => { cx += x; cy += y; });
    cx /= pts.length; cy /= pts.length;
    // 按极角排序
    const sorted = pts.slice().sort(([ax, ay], [bx, by]) => {
        return Math.atan2(ay - cy, ax - cx) - Math.atan2(by - cy, bx - cx);
    });
    // 闭合环
    sorted.push(sorted[0]);
    return sorted;
}

function contourArea(ring) {
    // Shoelace formula (像素坐标)
    let area = 0;
    for (let i = 0; i < ring.length - 1; i++) {
        area += ring[i][0] * ring[i+1][1] - ring[i+1][0] * ring[i][1];
    }
    return Math.abs(area / 2);
}

// ═══════════════════════════════════════════════════════
// 分割结果验证 (对比 SAM 预测掩码与真值掩码)
// ═══════════════════════════════════════════════════════

const gtFileInput = document.getElementById('gtFileInput');

async function validateSegmentation() {
    if (!logitsMap || !logitsWidth || !logitsHeight) {
        setStatus('error', '请先运行 SAM 推理生成预测掩码');
        return;
    }
    gtFileInput.click();
}

gtFileInput.onchange = async (e) => {
    const file = e.target.files[0];
    e.target.value = '';
    if (!file) return;

    if (!logitsMap || !logitsWidth || !logitsHeight) {
        setStatus('error', '预测掩码已失效，请重新运行 SAM');
        return;
    }

    setStatus('loading', '📐 加载真值掩码中...');

    try {
        // 1. 加载真值掩码 (图片或 CSV)
        let gt2d;
        const isImage = file.type.startsWith('image/') || /\.(png|jpg|jpeg|bmp|tif|tiff)$/i.test(file.name);
        const isCsv = /\.csv$/i.test(file.name);

        if (isImage) {
            gt2d = await loadGtImage(file, logitsWidth, logitsHeight);
        } else if (isCsv) {
            gt2d = await loadGtCsv(file, logitsWidth, logitsHeight);
        } else {
            setStatus('error', '不支持的文件格式，请选择图片 (PNG/JPG) 或 CSV');
            return;
        }

        // 2. 构建预测掩码 2D 数组 (二值化, 阈值 0.5)
        let pred2d = [];
        for (let y = 0; y < logitsHeight; y++) {
            const row = new Array(logitsWidth);
            for (let x = 0; x < logitsWidth; x++) {
                row[x] = logitsMap[y * logitsWidth + x] >= 0.5 ? 1.0 : 0.0;
            }
            pred2d.push(row);
        }

        // 3. 降采样以控制 payload 大小
        const MAX_DIM = 512;
        pred2d = downsampleMask(pred2d, MAX_DIM);
        gt2d = downsampleMask(gt2d, MAX_DIM);

        // 4. 确保形状一致 (以 pred2d 为基准对齐 GT)
        const ph = pred2d.length, pw = pred2d[0].length;
        const gh = gt2d.length, gw = gt2d[0].length;
        if (ph !== gh || pw !== gw) {
            gt2d = resizeMask(gt2d, pw, ph);
        }

        setStatus('loading', '📊 计算验证指标中...');

        // 5. 确保会话存在 (验证结果需关联会话)
        let sid = currentSessionId;
        if (!sid) {
            const sr = await fetch('/api/db/session', { method: 'POST' });
            if (sr.ok) {
                const sd = await sr.json();
                sid = sd.session_id;
                currentSessionId = sid;
            }
        }
        if (!sid) {
            setStatus('error', '无法创建会话，验证失败');
            return;
        }

        // 6. 调用验证 API
        const resp = await fetch(`/api/db/session/${sid}/validation`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                predicted_mask: pred2d,
                ground_truth_mask: gt2d,
                prediction_threshold: 0.5,
                ground_truth_threshold: 0.5,
            })
        });

        if (!resp.ok) {
            const err = await resp.json().catch(() => ({ detail: resp.statusText }));
            throw new Error(err.detail || `HTTP ${resp.status}`);
        }

        const result = await resp.json();
        showValidationResult(result);
        setStatus('ready', `✅ 验证完成 · IoU=${((result.metrics?.iou || 0) * 100).toFixed(1)}%`);
    } catch (e) {
        setStatus('error', '验证失败: ' + e.message);
    }
};

// ── 真值掩码加载工具 ──────────────────────────────────

function loadGtImage(file, targetW, targetH) {
    return new Promise((resolve, reject) => {
        const img = new Image();
        img.onload = () => {
            const c = document.createElement('canvas');
            c.width = targetW;
            c.height = targetH;
            const ctx = c.getContext('2d');
            ctx.drawImage(img, 0, 0, targetW, targetH);
            const data = ctx.getImageData(0, 0, targetW, targetH).data;
            const grid = [];
            for (let y = 0; y < targetH; y++) {
                const row = new Array(targetW);
                for (let x = 0; x < targetW; x++) {
                    const i = (y * targetW + x) * 4;
                    // 灰度归一化到 0~1 (白色=前景)
                    row[x] = (data[i] + data[i + 1] + data[i + 2]) / 3 / 255;
                }
                grid.push(row);
            }
            URL.revokeObjectURL(img.src);
            resolve(grid);
        };
        img.onerror = () => { URL.revokeObjectURL(img.src); reject(new Error('无法加载图片')); };
        img.src = URL.createObjectURL(file);
    });
}

function loadGtCsv(file, targetW, targetH) {
    return file.text().then(text => {
        const lines = text.trim().split(/\r?\n/);
        let grid = lines.map(l => l.trim().split(/[,\s]+/).map(v => {
            const n = parseFloat(v);
            return isNaN(n) ? 0 : n;
        })).filter(r => r.length > 0);
        if (grid.length === 0) throw new Error('CSV 文件为空');
        const srcW = grid[0].length, srcH = grid.length;
        if (srcW === targetW && srcH === targetH) return grid;
        return resizeMask(grid, targetW, targetH);
    });
}

function resizeMask(grid, targetW, targetH) {
    const srcH = grid.length, srcW = grid[0].length;
    if (srcW === targetW && srcH === targetH) return grid;
    const out = [];
    for (let y = 0; y < targetH; y++) {
        const sy = Math.min(srcH - 1, Math.floor(y * srcH / targetH));
        const row = new Array(targetW);
        for (let x = 0; x < targetW; x++) {
            const sx = Math.min(srcW - 1, Math.floor(x * srcW / targetW));
            row[x] = grid[sy][sx];
        }
        out.push(row);
    }
    return out;
}

function downsampleMask(grid, maxDim) {
    const h = grid.length, w = grid[0].length;
    if (Math.max(h, w) <= maxDim) return grid;
    const scale = maxDim / Math.max(h, w);
    return resizeMask(grid, Math.max(1, Math.round(w * scale)), Math.max(1, Math.round(h * scale)));
}

// ── 验证结果展示 ──────────────────────────────────────

function showValidationResult(result) {
    const m = result.metrics || {};
    const c = result.confusion || {};
    const pct = v => (v * 100).toFixed(2) + '%';
    const predShape = (result.prediction_shape || []).join('×');
    const gtShape = (result.ground_truth_shape || []).join('×');
    document.getElementById('validationBody').innerHTML = `
        <div style="text-align:center;margin-bottom:14px;">
            <div style="font-size:20px;font-weight:bold;color:#0066aa;">分割精度指标</div>
            <div style="font-size:11px;color:#999;margin-top:4px;">预测掩码 ${predShape} · 真值掩码 ${gtShape}</div>
        </div>
        <table style="width:100%;border-collapse:collapse;font-size:13px;">
            <tr style="background:#e8eef5;">
                <th style="padding:7px 10px;border:1px solid #ccc;text-align:left;">指标</th>
                <th style="padding:7px 10px;border:1px solid #ccc;text-align:right;">值</th>
                <th style="padding:7px 10px;border:1px solid #ccc;text-align:left;">说明</th>
            </tr>
            <tr><td style="padding:6px 10px;border:1px solid #ddd;font-weight:bold;">IoU</td><td style="padding:6px 10px;border:1px solid #ddd;text-align:right;font-weight:bold;color:#0066aa;">${pct(m.iou ?? 0)}</td><td style="padding:6px 10px;border:1px solid #ddd;color:#666;">交并比 (核心指标)</td></tr>
            <tr><td style="padding:6px 10px;border:1px solid #ddd;">Dice</td><td style="padding:6px 10px;border:1px solid #ddd;text-align:right;">${pct(m.dice ?? 0)}</td><td style="padding:6px 10px;border:1px solid #ddd;color:#666;">F1-Score</td></tr>
            <tr><td style="padding:6px 10px;border:1px solid #ddd;">Precision</td><td style="padding:6px 10px;border:1px solid #ddd;text-align:right;">${pct(m.precision ?? 0)}</td><td style="padding:6px 10px;border:1px solid #ddd;color:#666;">精确率</td></tr>
            <tr><td style="padding:6px 10px;border:1px solid #ddd;">Recall</td><td style="padding:6px 10px;border:1px solid #ddd;text-align:right;">${pct(m.recall ?? 0)}</td><td style="padding:6px 10px;border:1px solid #ddd;color:#666;">召回率</td></tr>
            <tr><td style="padding:6px 10px;border:1px solid #ddd;">Specificity</td><td style="padding:6px 10px;border:1px solid #ddd;text-align:right;">${pct(m.specificity ?? 0)}</td><td style="padding:6px 10px;border:1px solid #ddd;color:#666;">特异度</td></tr>
            <tr><td style="padding:6px 10px;border:1px solid #ddd;">Accuracy</td><td style="padding:6px 10px;border:1px solid #ddd;text-align:right;">${pct(m.accuracy ?? 0)}</td><td style="padding:6px 10px;border:1px solid #ddd;color:#666;">总体准确率</td></tr>
        </table>
        <div style="margin-top:14px;padding:10px;background:#f8f8f8;border-radius:6px;font-size:12px;">
            <b>混淆矩阵</b><br>
            TP (真正) = ${c.tp ?? 0} &nbsp;&nbsp; FP (假正) = ${c.fp ?? 0}<br>
            TN (真负) = ${c.tn ?? 0} &nbsp;&nbsp; FN (假负) = ${c.fn ?? 0}<br>
            总像素数 = ${c.total ?? 0}
        </div>`;
    document.getElementById('validationModal').style.display = 'flex';
}

// 弹窗关闭
const validationModal = document.getElementById('validationModal');
document.getElementById('validationModalClose').onclick = () => validationModal.style.display = 'none';
document.getElementById('validationModalOk').onclick = () => validationModal.style.display = 'none';
validationModal.addEventListener('click', e => { if (e.target === validationModal) validationModal.style.display = 'none'; });
