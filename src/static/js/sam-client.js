// sam-client.js — SAM3 embedding, inference, mask export

// ═══════════════════════════════════════════════════════
// SAM embedding & inference
// ═══════════════════════════════════════════════════════

async function computeEmbedding() {
    try {
        setStatus('loading', 'Computing embedding...');
        // Build the blob from the current canvas content (works for images from any source)
        const tempC = document.createElement('canvas');
        tempC.width = seismicImage.naturalWidth || canvas.width;
        tempC.height = seismicImage.naturalHeight || canvas.height;
        tempC.getContext('2d').drawImage(seismicImage, 0, 0, tempC.width, tempC.height);
        const blob = await new Promise(r => tempC.toBlob(r, 'image/png'));
        const form = new FormData();
        form.append('file', blob, 'slice.png');
        const resp = await fetch('/api/embed', {method:'POST', body:form});
        if (!resp.ok) throw await respError(resp);
        const data = await resp.json();
        embeddingId = data.embedding_id;
        embeddingImageSize = data.image_size;
        setStatus('ready', 'SAM3 ready');
    } catch(e) {
        setStatus('error', 'Embedding failed: ' + errText(e));
    }
}

// ═══════════════════════════════════════════════════════
// SAM inference
// ═══════════════════════════════════════════════════════

async function runSAMInference() {
    if (!samEnabled) { setStatus('error', 'SAM mode is not enabled'); return; }
    if (isInferring) { setStatus('loading', 'SAM is already running, please wait...'); return; }

    // Get the picks of the current slice
    const curKey = currentSliceKey();
    const picks = picksBySlice.get(curKey) || [];
    if (picks.length === 0) {
        setStatus('error', 'Pick Include/Exclude points first');
        return;
    }

    isInferring = true;
    setStatus('loading', 'Running SAM...');

    // Auto-refine: the server runs SAM + label-free QC for up to 3 rounds (refine-panel.js)
    if (typeof autoRefineOn === 'function' && autoRefineOn()) {
        try {
            if (!picks.some(p => p.label === 1)) throw new Error('add at least one Include point on the target');
            await runRefine(picks);
        } catch (e) {
            setStatus('error', 'SAM refine failed: ' + errText(e));
        } finally { isInferring = false; }
        return;
    }
    if (typeof clearRefine === 'function') clearRefine();

    try {
        // 1. Embed the current slice once. NPY volumes: the server renders the slice itself, so the
        //    embedding never contains pick markers, overlays or the display colour map (bug B1).
        //    Other sources: embed the clean seismic rendering (seismicImageData), never the live canvas.
        if (!embeddingId) {
            setStatus('loading', encodingStatus());
            let resp;
            if (volInfo.source === 'api/npy' && volInfo.name) {
                resp = await fetch(`/api/npy/${encodeURIComponent(volInfo.name)}/embed`, {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({direction: curDir, index: curIndex, mode: 'raw'})  // SAM segments raw (docs/MEASUREMENTS.md)
                });
            } else {
                const tempC = document.createElement('canvas');
                const src = seismicImageData;
                tempC.width = src ? src.width : canvas.width;
                tempC.height = src ? src.height : canvas.height;
                if (src) tempC.getContext('2d').putImageData(src, 0, 0);
                else tempC.getContext('2d').drawImage(canvas, 0, 0);
                const blob = await new Promise(r => tempC.toBlob(r, 'image/png'));
                const form = new FormData();
                form.append('file', blob, 'slice.png');
                resp = await fetch('/api/embed', {method:'POST', body:form});
            }
            if (!resp.ok) throw await respError(resp);
            const data = await resp.json();
            embeddingId = data.embedding_id;
            embeddingImageSize = data.image_size;   // [w, h] of the embedded image
            setStatus('loading', '✅ Encoded, running SAM...');
        }

        // 2. Map picks (normalised to the displayed slice) to pixels of the embedded image
        const imgW = embeddingImageSize ? embeddingImageSize[0] : canvas.width;
        const imgH = embeddingImageSize ? embeddingImageSize[1] : canvas.height;
        const points = picks.map(p => {
            if (p.nx != null) return [p.nx * imgW, p.ny * imgH];
            return [p.x / canvas.width * imgW, p.y / canvas.height * imgH];
        });
        const labels = picks.map(p => p.label);

        setStatus('loading', `Running inference (${picks.length} points)...`);

        // 3. Call the backend predict
        const resp = await fetch('/api/predict', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({embedding_id:embeddingId, points, labels})
        });
        if (!resp.ok) throw await respError(resp);
        const result = await resp.json();

        // 4. Store the logits
        setStatus('loading', 'Rendering segmentation...');
        logitsHeight = result.mask_shape[0];
        logitsWidth = result.mask_shape[1];
        logitsMap = new Float32Array(result.mask.flat());
        window._lastSamScore = result.scores[0] || 0;  // read by the AI analysis
        drawSeismic();

        // 5. Save the result to the database
        setStatus('loading', 'Saving result...');
        if (currentSessionId) {
            await fetch(`/api/db/session/${currentSessionId}/sam_result`, {
                method:'POST',
                headers:{'Content-Type':'application/json'},
                body: JSON.stringify({mask_path:'', score:result.scores[0], mask_shape:result.mask_shape})
            });
        }
        // 6. Map back to the 3D volume mask (NPY volumes only): slice mask -> voxels
        const volNote = await writeSamVolumeMask(result, picks);
        setStatus('ready', `SAM done${volNote} · Score: ${result.scores[0].toFixed(3)} · ${picks.length} points`);
    } catch(e) {
        setStatus('error', 'Inference failed: ' + errText(e));
    } finally { isInferring = false; }
}

// ═══════════════════════════════════════════════════════
// Mask export (GeoJSON + CSV polygons + QC round log)
// ═══════════════════════════════════════════════════════

// Polygon vertices sit on pixel corners, so the rings cover exactly the mask pixels shown on the
// canvas. Corner c of an axis with n pixels maps to the same value the on-screen axis shows at that
// position: min + c / n * (max - min) (see updateAxes() in sgy-client.js).
function exportMaskAsContour() {
    if (!logitsMap || !logitsWidth || !logitsHeight) {
        setStatus('error', 'Run SAM first to create a mask');
        return;
    }

    setStatus('loading', 'Extracting contours...');
    const threshold = 0.5;
    const W = logitsWidth, H = logitsHeight;
    const bin = new Uint8Array(W * H);
    let maskPixels = 0;
    for (let i = 0; i < W * H; i++) { bin[i] = logitsMap[i] >= threshold ? 1 : 0; maskPixels += bin[i]; }
    const polygons = extractContours(bin, W, H);
    if (polygons.length === 0) {
        setStatus('error', 'No valid contour found in the mask');
        return;
    }

    // The canvas shows the selected QC round unless another mask replaced it since.
    const run = (typeof refineRun !== 'undefined' && refineRun && refineSliceKey === currentSliceKey()) ? refineRun : null;
    const round = run ? run.rounds[refineSelected - 1] : null;
    const fromRound = !!round && maskEqualsRound(bin, W, H, round, run.grid_shape);

    // Pixel-corner coordinates -> IL / XL / vertical axis, in the units of the displayed axes
    const dtMs = (volInfo.dtUs || 1000) / 1000;
    const yName = curDir === 'timeslice'
        ? (yAxisUnit === 'depth' ? 'Depth (m)' : 'Time (ms)')
        : COORD.yLabel;
    const sliceY = yAxisUnit === 'depth' ? curIndex * dtMs * velocity / 2 / 1000 : curIndex * dtMs;
    const toAxes = ([cx, cy]) => {
        const xPct = cx / W, yPct = cy / H;
        let il, xl, y;
        if (curDir === 'inline') {
            xl = COORD.crossMin + xPct * (COORD.crossMax - COORD.crossMin);
            il = volInfo.ilMin + curIndex;
            y = COORD.yTop + yPct * COORD.yRange;
        } else if (curDir === 'crossline') {
            il = COORD.crossMin + xPct * (COORD.crossMax - COORD.crossMin);
            xl = volInfo.xlMin + curIndex;
            y = COORD.yTop + yPct * COORD.yRange;
        } else {
            xl = COORD.crossMin + xPct * (COORD.crossMax - COORD.crossMin);
            il = volInfo.ilMin + yPct * (volInfo.ilMax - volInfo.ilMin);
            y = sliceY;
        }
        return { il: +il.toFixed(3), xl: +xl.toFixed(3), y: +y.toFixed(3) };
    };
    let geoPolygons;
    try {
        geoPolygons = polygons.map(rings => rings.map(ring => ring.map(toAxes)));
    } catch (e) {
        setStatus('error', 'Coordinate conversion failed: ' + e.message);
        return;
    }

    setStatus('loading', 'Building GeoJSON...');
    const sliceKey = currentSliceKey();
    const features = geoPolygons.map((rings, i) => ({
        type: 'Feature',
        properties: {
            id: i,
            slice_key: sliceKey,
            direction: curDir,
            index: curIndex,
            area_pixels: polygonAreaPixels(polygons[i]),
            holes: rings.length - 1,
        },
        geometry: {
            type: 'Polygon',
            coordinates: rings.map(ring => ring.map(p => [p.il, p.xl, p.y])),
        }
    }));
    const props = {
        volume: volInfo.name,
        source: fromRound ? 'SAM3 + QC refine' : 'SAM3',
        direction: curDir,
        index: curIndex,
        coordinate_order: ['inline', 'crossline', yName],
        grid_shape: [H, W],
        mask_pixels: maskPixels,
        threshold: threshold,
        timestamp: new Date().toISOString(),
    };
    if (fromRound) { props.run_id = run.run_id; props.round = round.round; }
    const geojson = { type: 'FeatureCollection', properties: props, features };

    setStatus('loading', 'Preparing download files...');
    const base = `${volInfo.name || 'unknown'}_${sliceKey.replace(':', '')}`;
    downloadText(JSON.stringify(geojson, null, 2), 'application/geo+json', `sam_mask_${base}.geojson`);

    // CSV: one row per ring vertex; Ring 0 = outer boundary, 1.. = holes
    const yCol = yName.startsWith('Depth') ? 'Depth_m' : 'Time_ms';
    let csv = `ContourID,Ring,Inline,Crossline,${yCol},Direction\n`;
    geoPolygons.forEach((rings, i) => rings.forEach((ring, k) => ring.forEach(p => {
        csv += `${i},${k},${p.il},${p.xl},${p.y},${curDir}\n`;
    })));
    downloadText(csv, 'text/csv', `sam_mask_${base}.csv`);

    let note = '';
    if (run) {
        downloadText(JSON.stringify(buildQcLog(run), null, 2), 'application/json',
                     `qc_log_${run.volume}_${run.direction}${run.index}.json`);
        note = ' + QC log';
    }
    setStatus('ready', `Exported ${polygons.length} polygon(s), ${maskPixels} px (GeoJSON + CSV${note})` +
                       (fromRound ? ` · QC round ${round.round}` : ''));
}

function downloadText(text, type, filename) {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([text], {type}));
    a.download = filename;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 10000);
}

function maskEqualsRound(bin, W, H, round, gridShape) {
    if (!round || !round.mask || !gridShape || gridShape[0] !== H || gridShape[1] !== W) return false;
    for (let i = 0; i < H; i++) {
        const row = round.mask[i];
        for (let j = 0; j < W; j++) if ((row[j] >= 0.5 ? 1 : 0) !== bin[i * W + j]) return false;
    }
    return true;
}

function maskPixelCount(mask) {
    let n = 0;
    (mask || []).forEach(row => row.forEach(v => { if (v >= 0.5) n++; }));
    return n;
}

// QC round log of a refine run: scores, metrics, corrections and prompts per round, without full masks
function buildQcLog(run) {
    return {
        schema: 'samforgeophysics.qc_log/1',
        exported_at: new Date().toISOString(),
        run_id: run.run_id,
        volume: run.volume,
        direction: run.direction,
        index: run.index,
        sam_view: run.mode,
        target_type: run.target_type,
        grid_shape: run.grid_shape,
        constants: run.constants,
        best_round: run.best_round,
        selected_round: refineSelected,
        stop_reason: run.stop_reason,
        stop_message: run.stop_message,
        rounds: run.rounds.map(r => ({
            round: r.round,
            score: r.score,
            delta: r.delta,
            metrics: r.metrics,
            correction: r.correction,
            prompts: r.prompts,
            truth_reference: r.truth_reference
                ? Object.assign({note: 'Reference only: overlap with the synthetic ground truth; the QC loop never sees it.'},
                                r.truth_reference)
                : null,
            mask_pixels: maskPixelCount(r.mask),
        })),
    };
}

// ═══════════════════════════════════════════════════════
// Mask outline tracing (pixel-edge boundaries)
// ═══════════════════════════════════════════════════════

// Returns polygons as [outerRing, ...holeRings]; rings are closed lists of [x, y] pixel corners.
// Foreground is 4-connected (diagonal pixels are separate polygons). Largest polygon first.
function extractContours(bin, w, h) {
    const fg = (x, y) => x >= 0 && x < w && y >= 0 && y < h && bin[y * w + x] === 1;
    // Directed boundary edges with the foreground on the right (y points down)
    const out = new Map();   // vertex key -> list of edges leaving it
    const edges = [];
    const add = (x0, y0, x1, y1) => {
        const e = {x0, y0, x1, y1, used: false};
        edges.push(e);
        const k = y0 * (w + 1) + x0;
        if (!out.has(k)) out.set(k, []);
        out.get(k).push(e);
    };
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
        if (!fg(x, y)) continue;
        if (!fg(x, y - 1)) add(x, y, x + 1, y);
        if (!fg(x + 1, y)) add(x + 1, y, x + 1, y + 1);
        if (!fg(x, y + 1)) add(x + 1, y + 1, x, y + 1);
        if (!fg(x - 1, y)) add(x, y + 1, x, y);
    }
    const loops = [];
    for (const start of edges) {
        if (start.used) continue;
        const ring = [[start.x0, start.y0]];
        let e = start;
        while (e && !e.used) {
            e.used = true;
            ring.push([e.x1, e.y1]);
            const dx = e.x1 - e.x0, dy = e.y1 - e.y0;
            const cand = (out.get(e.y1 * (w + 1) + e.x1) || []).slice();
            // Two edges leave a vertex only at a diagonal saddle; the right turn keeps diagonal
            // pixels apart. The loop closes when the chosen edge is the (used) start edge.
            const rank = c => {
                const cx = c.x1 - c.x0, cy = c.y1 - c.y0;
                if (cx === -dy && cy === dx) return 0;
                if (cx === dx && cy === dy) return 1;
                return 2;
            };
            cand.sort((a, b) => rank(a) - rank(b));
            e = cand[0];
        }
        loops.push(simplifyRing(ring));
    }
    // Outer rings have positive signed area (clockwise on screen), holes negative
    const outers = loops.filter(r => ringSignedArea(r) > 0).map(r => [r]);
    loops.filter(r => ringSignedArea(r) < 0).forEach(hole => {
        const [x0, y0] = hole[0], [x1, y1] = hole[1];
        const dx = Math.sign(x1 - x0), dy = Math.sign(y1 - y0);
        const px = (x0 + x0 + dx) / 2 + 0.25 * dy, py = (y0 + y0 + dy) / 2 - 0.25 * dx;  // just inside the hole
        let owner = null;
        outers.forEach(p => {
            if (pointInRing(px, py, p[0]) && (!owner || ringSignedArea(p[0]) < ringSignedArea(owner[0]))) owner = p;
        });
        if (owner) owner.push(hole);
    });
    outers.sort((a, b) => polygonAreaPixels(b) - polygonAreaPixels(a));
    return outers;
}

// Drop vertices in the middle of straight runs; keeps the ring closed
function simplifyRing(ring) {
    const pts = ring.slice(0, -1);
    const n = pts.length;
    const keep = pts.filter((p, i) => {
        const a = pts[(i - 1 + n) % n], b = pts[(i + 1) % n];
        return (p[0] - a[0]) * (b[1] - p[1]) - (p[1] - a[1]) * (b[0] - p[0]) !== 0;
    });
    keep.push(keep[0]);
    return keep;
}

function ringSignedArea(ring) {
    let s = 0;
    for (let i = 0; i < ring.length - 1; i++) s += ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1];
    return s / 2;
}

// Pixel count covered by a polygon: outer area minus holes
function polygonAreaPixels(rings) {
    return rings.reduce((s, r) => s + ringSignedArea(r), 0);
}

function pointInRing(x, y, ring) {
    let inside = false;
    for (let i = 0, j = ring.length - 2; i < ring.length - 1; j = i++) {
        const [xi, yi] = ring[i], [xj, yj] = ring[j];
        if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) inside = !inside;
    }
    return inside;
}

// ═══════════════════════════════════════════════════════
// Segmentation validation (compare the SAM predicted mask with a ground-truth mask)
// ═══════════════════════════════════════════════════════

const gtFileInput = document.getElementById('gtFileInput');

async function validateSegmentation() {
    if (!logitsMap || !logitsWidth || !logitsHeight) {
        setStatus('error', 'Run SAM first to create a predicted mask');
        return;
    }
    gtFileInput.click();
}

gtFileInput.onchange = async (e) => {
    const file = e.target.files[0];
    e.target.value = '';
    if (!file) return;

    if (!logitsMap || !logitsWidth || !logitsHeight) {
        setStatus('error', 'Predicted mask is no longer valid, run SAM again');
        return;
    }

    setStatus('loading', 'Loading ground-truth mask...');

    try {
        // 1. Load the ground-truth mask (image or CSV)
        let gt2d;
        const isImage = file.type.startsWith('image/') || /\.(png|jpg|jpeg|bmp|tif|tiff)$/i.test(file.name);
        const isCsv = /\.csv$/i.test(file.name);

        if (isImage) {
            gt2d = await loadGtImage(file, logitsWidth, logitsHeight);
        } else if (isCsv) {
            gt2d = await loadGtCsv(file, logitsWidth, logitsHeight);
        } else {
            setStatus('error', 'Unsupported file format, choose an image (PNG/JPG) or CSV');
            return;
        }

        // 2. Build the 2D predicted mask array (binarized, threshold 0.5)
        let pred2d = [];
        for (let y = 0; y < logitsHeight; y++) {
            const row = new Array(logitsWidth);
            for (let x = 0; x < logitsWidth; x++) {
                row[x] = logitsMap[y * logitsWidth + x] >= 0.5 ? 1.0 : 0.0;
            }
            pred2d.push(row);
        }

        // 3. Downsample to limit the payload size
        const MAX_DIM = 512;
        pred2d = downsampleMask(pred2d, MAX_DIM);
        gt2d = downsampleMask(gt2d, MAX_DIM);

        // 4. Make the shapes match (align GT to pred2d)
        const ph = pred2d.length, pw = pred2d[0].length;
        const gh = gt2d.length, gw = gt2d[0].length;
        if (ph !== gh || pw !== gw) {
            gt2d = resizeMask(gt2d, pw, ph);
        }

        setStatus('loading', 'Computing validation metrics...');

        // 5. Make sure a session exists (validation results are linked to a session)
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
            setStatus('error', 'Could not create a session, validation failed');
            return;
        }

        // 6. Call the validation API
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
        setStatus('ready', `Validation done · IoU=${((result.metrics?.iou || 0) * 100).toFixed(1)}%`);
    } catch (e) {
        setStatus('error', 'Validation failed: ' + e.message);
    }
};

// ── Ground-truth mask loaders ──────────────────────────────────

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
                    // Grayscale normalized to 0~1 (white = foreground)
                    row[x] = (data[i] + data[i + 1] + data[i + 2]) / 3 / 255;
                }
                grid.push(row);
            }
            URL.revokeObjectURL(img.src);
            resolve(grid);
        };
        img.onerror = () => { URL.revokeObjectURL(img.src); reject(new Error('Could not load image')); };
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
        if (grid.length === 0) throw new Error('CSV file is empty');
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

// ── Validation result display ──────────────────────────────────────

function showValidationResult(result) {
    const m = result.metrics || {};
    const c = result.confusion || {};
    const pct = v => (v * 100).toFixed(2) + '%';
    const predShape = (result.prediction_shape || []).join('×');
    const gtShape = (result.ground_truth_shape || []).join('×');
    document.getElementById('validationBody').innerHTML = `
        <div style="text-align:center;margin-bottom:14px;">
            <div style="font-size:20px;font-weight:bold;color:#0066aa;">Segmentation accuracy</div>
            <div style="font-size:11px;color:#999;margin-top:4px;">Predicted mask ${predShape} · Ground-truth mask ${gtShape}</div>
        </div>
        <table style="width:100%;border-collapse:collapse;font-size:13px;">
            <tr style="background:#e8eef5;">
                <th style="padding:7px 10px;border:1px solid #ccc;text-align:left;">Metric</th>
                <th style="padding:7px 10px;border:1px solid #ccc;text-align:right;">Value</th>
                <th style="padding:7px 10px;border:1px solid #ccc;text-align:left;">Meaning</th>
            </tr>
            <tr><td style="padding:6px 10px;border:1px solid #ddd;font-weight:bold;">IoU</td><td style="padding:6px 10px;border:1px solid #ddd;text-align:right;font-weight:bold;color:#0066aa;">${pct(m.iou ?? 0)}</td><td style="padding:6px 10px;border:1px solid #ddd;color:#666;">Intersection over union (main metric)</td></tr>
            <tr><td style="padding:6px 10px;border:1px solid #ddd;">Dice</td><td style="padding:6px 10px;border:1px solid #ddd;text-align:right;">${pct(m.dice ?? 0)}</td><td style="padding:6px 10px;border:1px solid #ddd;color:#666;">F1-Score</td></tr>
            <tr><td style="padding:6px 10px;border:1px solid #ddd;">Precision</td><td style="padding:6px 10px;border:1px solid #ddd;text-align:right;">${pct(m.precision ?? 0)}</td><td style="padding:6px 10px;border:1px solid #ddd;color:#666;">Precision</td></tr>
            <tr><td style="padding:6px 10px;border:1px solid #ddd;">Recall</td><td style="padding:6px 10px;border:1px solid #ddd;text-align:right;">${pct(m.recall ?? 0)}</td><td style="padding:6px 10px;border:1px solid #ddd;color:#666;">Recall</td></tr>
            <tr><td style="padding:6px 10px;border:1px solid #ddd;">Specificity</td><td style="padding:6px 10px;border:1px solid #ddd;text-align:right;">${pct(m.specificity ?? 0)}</td><td style="padding:6px 10px;border:1px solid #ddd;color:#666;">Specificity</td></tr>
            <tr><td style="padding:6px 10px;border:1px solid #ddd;">Accuracy</td><td style="padding:6px 10px;border:1px solid #ddd;text-align:right;">${pct(m.accuracy ?? 0)}</td><td style="padding:6px 10px;border:1px solid #ddd;color:#666;">Overall accuracy</td></tr>
        </table>
        <div style="margin-top:14px;padding:10px;background:#f8f8f8;border-radius:6px;font-size:12px;">
            <b>Confusion matrix</b><br>
            TP (true positive) = ${c.tp ?? 0} &nbsp;&nbsp; FP (false positive) = ${c.fp ?? 0}<br>
            TN (true negative) = ${c.tn ?? 0} &nbsp;&nbsp; FN (false negative) = ${c.fn ?? 0}<br>
            Total pixels = ${c.total ?? 0}
        </div>`;
    document.getElementById('validationModal').style.display = 'flex';
}

// Close the modal
const validationModal = document.getElementById('validationModal');
document.getElementById('validationModalClose').onclick = () => validationModal.style.display = 'none';
document.getElementById('validationModalOk').onclick = () => validationModal.style.display = 'none';
validationModal.addEventListener('click', e => { if (e.target === validationModal) validationModal.style.display = 'none'; });

// ═══════════════════════════════════════════════════════
// 3D volume mask overlay & cross-slice propagation
// ═══════════════════════════════════════════════════════

async function writeSamVolumeMask(result, picks) {
    if (volInfo.source !== 'api/npy' || !volInfo.name) return '';
    const volume = volInfo.name;
    try {
        const response = await fetch(`/api/npy/${encodeURIComponent(volume)}/mask`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                direction: curDir, index: curIndex, mask: result.mask,
                mask_name: VOL_MASK_NAME, mode: 'replace', score: result.scores[0],
                points: picks.map(p => ({ x: p.nx ?? p.x, y: p.ny ?? p.y, label: p.label })),
            }),
        });
        if (!response.ok) return ' · Volume mask write failed';
        const mask = await response.json();
        refreshVolumeMaskAvailability(volume);
        return ` · Voxels ${mask.total_voxels} (${mask.slices_written} slices)`;
    } catch (e) {
        return ' · Volume mask write failed';
    }
}

const VOL_MASK_NAME = 'sam_mask';
const volumeMaskAvailability = new Map();

function hasVolumeMask(volume) {
    if (!volumeMaskAvailability.has(volume)) {
        const request = fetch(`/api/npy/${encodeURIComponent(volume)}/masks`)
            .then(async response => {
                if (!response.ok) throw await respError(response);
                const { masks } = await response.json();
                return masks.some(mask => mask.mask_name === VOL_MASK_NAME);
            })
            .catch(() => {
                if (volumeMaskAvailability.get(volume) === request) volumeMaskAvailability.delete(volume);
                return false;
            });
        volumeMaskAvailability.set(volume, request);
    }
    return volumeMaskAvailability.get(volume);
}

function refreshVolumeMaskAvailability(volume) {
    volumeMaskAvailability.delete(volume);
    if (volInfo.source === 'api/npy' && volInfo.name === volume) refreshSurveyFootprint();
}

// After a slice change, if the volume mask has content on that slice, load it as the overlay (same rendering as SAM logits)
async function loadVolumeMaskOverlay(dir, index) {
    if (volInfo.source !== 'api/npy' || !volInfo.name) return;
    const volume = volInfo;
    const availability = hasVolumeMask(volume.name);
    try {
        if (!await availability || volume !== volInfo) return;
        const r = await fetch(`/api/npy/${encodeURIComponent(volume.name)}/mask/${VOL_MASK_NAME}/slice/${dir}/${index}`);
        if (!r.ok) return;
        const rows = +r.headers.get('X-Rows'), cols = +r.headers.get('X-Cols');
        const arr = new Float32Array(await r.arrayBuffer());
        if (volume !== volInfo || availability !== volumeMaskAvailability.get(volume.name)
            || dir !== curDir || index !== curIndex || arr.length !== rows * cols) return;
        let any = false;
        for (let i = 0; i < arr.length; i++) if (arr[i] > 0.5) { any = true; break; }
        if (!any) return;
        logitsMap = arr; logitsHeight = rows; logitsWidth = cols;
        drawSeismic();
    } catch (e) { /* silent when there is no volume mask */ }
}

const propPanel = document.getElementById('propPanel');
const propSliders = [
    ['propIl', 'propIlVal', v => String(v)],
    ['propXl', 'propXlVal', v => String(v)],
    ['propV', 'propVVal', v => String(v)],
    ['propIou', 'propIouVal', v => (+v).toFixed(2)],
].map(([id, valId, fmt]) => {
    const el = document.getElementById(id), lab = document.getElementById(valId);
    el.addEventListener('input', () => { lab.textContent = fmt(el.value); });
    return el;
});

function syncPropSliderLimits() {
    // Slider maximum follows the current volume size (max = axis length - 1)
    const setMax = (id, n) => {
        const el = document.getElementById(id);
        el.max = Math.max(1, (n || 1) - 1);
        if (+el.value > +el.max) { el.value = el.max; el.dispatchEvent(new Event('input')); }
    };
    setMax('propIl', volInfo.ilCount);
    setMax('propXl', volInfo.xlCount);
    setMax('propV', volInfo.tsCount);
}

document.getElementById('btnPropSettings').onclick = e => {
    e.stopPropagation();
    syncPropSliderLimits();
    propPanel.style.display = propPanel.style.display === 'none' ? 'block' : 'none';
};
document.addEventListener('click', e => {
    if (propPanel.style.display !== 'none' && !propPanel.contains(e.target)) propPanel.style.display = 'none';
});

let isPropagating = false;

async function runPropagation() {
    if (volInfo.source !== 'api/npy' || !volInfo.name) {
        setStatus('error', 'Propagation only works on NPY volumes'); return;
    }
    if (isInferring || isPropagating) { setStatus('loading', 'Inference/propagation already running, please wait...'); return; }
    if (!logitsMap) { setStatus('error', 'Run SAM (▶ SAM) on the current slice first to create a seed mask'); return; }

    const volume = volInfo.name;
    isPropagating = true;
    const btn = document.getElementById('btnPropagate');
    btn.disabled = true;
    const lim = {
        max_il: +document.getElementById('propIl').value,
        max_xl: +document.getElementById('propXl').value,
        max_vertical: +document.getElementById('propV').value,
        min_iou: +document.getElementById('propIou').value,
    };
    setStatus('loading', `Propagating (IL ±${lim.max_il}, XL ±${lim.max_xl}, vertical ±${lim.max_vertical})...`);
    try {
        const resp = await fetch(`/api/npy/${encodeURIComponent(volume)}/propagate`, {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({direction: curDir, index: curIndex, mask_name: VOL_MASK_NAME, ...lim})
        });
        if (!resp.ok) throw await respError(resp);
        const r = await resp.json();
        const n = r.written_indices.length;
        const stops = [...new Set(r.slices.filter(s => s.stopped).map(s => s.stopped))];
        refreshVolumeMaskAvailability(volume);
        setStatus('ready', `Propagation done · ${n} new slices · Voxels ${r.total_voxels}` +
            (stops.length ? ` · Stop reason: ${stops.join('/')}` : ''));
    } catch (e) {
        setStatus('error', 'Propagation failed: ' + errText(e));
    } finally {
        isPropagating = false;
        btn.disabled = false;
    }
}

document.getElementById('btnPropagate').onclick = () => runPropagation();
