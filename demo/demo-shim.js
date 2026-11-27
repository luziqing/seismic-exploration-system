// demo-shim.js — Injected ONLY into the Vercel static demo build (dist/index.html).
// Intercepts /api/ requests in window.fetch so the unmodified frontend UI runs without a Python backend,
// serves exported synthetic inline slices (IL 1-48) on demand, stitches crosslines and time slices
// in the browser from cached inlines, returns honest 503/404 statuses, and replays recorded local runs.
(function initStaticWebDemo() {
    'use strict';

    const realFetch = window.fetch.bind(window);
    const UNAVAILABLE_DETAIL =
        'Not available in the static web demo: SAM3, the QC loop and the server run only in the local build. See README > Run it.';
    const LOCAL_RUN_URL = 'https://github.com/luziqing/seismic-exploration-system#run-it';

    let manifestPromise = null;
    const inlineCache = new Map();   // key: `${vol}:${mode}:${idx}` -> Promise<Float32Array>
    const recordedCache = new Map();

    function getManifest() {
        if (!manifestPromise) {
            manifestPromise = realFetch('/demo/assets/manifest.json').then(r => {
                if (!r.ok) throw new Error('Failed to load static demo manifest: HTTP ' + r.status);
                return r.json();
            });
        }
        return manifestPromise;
    }

    async function getRecordedRun(key) {
        const manifest = await getManifest();
        const info = manifest.recorded_runs && manifest.recorded_runs[key];
        if (!info) return null;
        if (!recordedCache.has(key)) {
            const resp = await realFetch('/' + info.file.replace(/^\/+/, ''));
            if (!resp.ok) throw new Error('Failed to load recorded run: HTTP ' + resp.status);
            recordedCache.set(key, { info, run: await resp.json() });
        }
        return recordedCache.get(key);
    }

    function jsonResponse(payload, status) {
        return new Response(JSON.stringify(payload), {
            status: status || 200,
            headers: { 'Content-Type': 'application/json' },
        });
    }

    function binaryResponse(f32Array, rows, cols) {
        return new Response(f32Array.buffer, {
            status: 200,
            headers: {
                'Content-Type': 'application/octet-stream',
                'X-Rows': String(rows),
                'X-Cols': String(cols),
            },
        });
    }

    function decodeI16Slice(buffer, scale, rows, cols) {
        const view = new DataView(buffer);
        const total = rows * cols;
        const out = new Float32Array(total);
        for (let i = 0; i < total; i++) {
            out[i] = view.getInt16(i * 2, true) * scale;
        }
        return out;
    }

    function getInlineArray(vol, mode, idx, volEntry) {
        const key = `${vol}:${mode}:${idx}`;
        if (!inlineCache.has(key)) {
            const p = (async () => {
                const modeEntry = volEntry.modes[mode];
                const sliceMeta = modeEntry.slices[String(idx)];
                if (!sliceMeta) throw new Error(`Missing static inline ${idx}`);
                const assetResp = await realFetch('/' + sliceMeta.path.replace(/^\/+/, ''));
                if (!assetResp.ok) throw new Error('Static slice asset missing: HTTP ' + assetResp.status);
                const [rows, cols] = modeEntry.shape;
                return decodeI16Slice(await assetResp.arrayBuffer(), modeEntry.scale, rows, cols);
            })().catch(err => {
                inlineCache.delete(key);
                throw err;
            });
            inlineCache.set(key, p);
        }
        return inlineCache.get(key);
    }

    async function getAllInlines(vol, mode, volEntry, nIL) {
        const tasks = [];
        for (let il = 0; il < nIL; il++) {
            tasks.push(getInlineArray(vol, mode, il, volEntry));
        }
        return Promise.all(tasks);
    }

    // Explicit route table covering every /api/* fetch call in src/static/js/*.js
    const ROUTES = [
        {
            method: 'GET',
            pattern: /^\/api\/status$/,
            handler: async () => jsonResponse({
                model_loaded: false,
                model_loading: false,
                weights_exists: false,
                gpu_available: false,
                gpu_name: null,
                sam_device: 'cpu',
                weights_path: 'data/weights/sam3.pt',
                weights_source: 'static web demo',
                sgy_loaded: false,
                openvds_available: false,
            }, 200),
        },
        {
            method: 'GET',
            pattern: /^\/api\/devices$/,
            handler: async () => jsonResponse({
                devices: [{ id: 'cpu', name: 'CPU (SAM3 unavailable in static web demo)' }],
                selected: 'cpu',
                model_loaded: false,
            }, 200),
        },
        {
            method: 'GET',
            pattern: /^\/api\/npy\/list$/,
            handler: async () => {
                const manifest = await getManifest();
                return jsonResponse({ volumes: manifest.volume_list || [] }, 200);
            },
        },
        {
            method: 'GET',
            pattern: /^\/api\/npy\/([^/]+)\/meta$/,
            handler: async (m) => {
                const vol = decodeURIComponent(m[1]);
                const manifest = await getManifest();
                const entry = manifest.volumes && manifest.volumes[vol];
                if (!entry) return jsonResponse({ detail: 'NumPy volume not found: ' + vol }, 404);
                return jsonResponse(entry.meta, 200);
            },
        },
        {
            method: 'GET',
            pattern: /^\/api\/npy\/([^/]+)\/masks$/,
            handler: async (m) => {
                const vol = decodeURIComponent(m[1]);
                const manifest = await getManifest();
                if (!manifest.volumes || !manifest.volumes[vol]) {
                    return jsonResponse({ detail: 'NumPy volume not found: ' + vol }, 404);
                }
                return jsonResponse({ masks: [] }, 200);
            },
        },
        {
            method: 'GET',
            pattern: /^\/api\/npy\/([^/]+)\/mask\/([^/]+)\/(?:info|footprint|slice\/[^/]+\/-?\d+)$/,
            handler: async () => jsonResponse({ detail: 'Not found in the static web demo.' }, 404),
        },
        {
            method: 'GET',
            pattern: /^\/api\/npy\/([^/]+)\/slice\/(inline|crossline|timeslice)\/(-?\d+)$/,
            handler: async (m, url) => {
                const vol = decodeURIComponent(m[1]);
                const dir = m[2];
                const idx = parseInt(m[3], 10);
                const mode = url.searchParams.get('mode') || 'raw';
                const manifest = await getManifest();
                const volEntry = manifest.volumes && manifest.volumes[vol];
                if (!volEntry) return jsonResponse({ detail: 'NumPy volume not found: ' + vol }, 404);
                const modeEntry = volEntry.modes && volEntry.modes[mode];
                if (!modeEntry) return jsonResponse({ detail: 'Unknown mode: ' + mode }, 400);

                const meta = volEntry.meta;
                const nIL = meta.n_inlines;
                const nXL = meta.n_crosslines;
                const nSamples = meta.n_samples;

                if (dir === 'inline') {
                    if (idx < 0 || idx >= nIL || !(modeEntry.slices && modeEntry.slices[String(idx)])) {
                        return jsonResponse({ detail: `Inline index ${idx} out of range [0, ${nIL - 1}] in the static web demo.` }, 404);
                    }
                    const f32 = await getInlineArray(vol, mode, idx, volEntry);
                    return binaryResponse(new Float32Array(f32), nSamples, nXL);
                }

                if (dir === 'crossline') {
                    if (idx < 0 || idx >= nXL) {
                        return jsonResponse({ detail: `Crossline index ${idx} out of range [0, ${nXL - 1}] in the static web demo.` }, 404);
                    }
                    const inlines = await getAllInlines(vol, mode, volEntry, nIL);
                    const out = new Float32Array(nSamples * nIL);
                    for (let il = 0; il < nIL; il++) {
                        const src = inlines[il];
                        for (let s = 0; s < nSamples; s++) {
                            out[s * nIL + il] = src[s * nXL + idx];
                        }
                    }
                    return binaryResponse(out, nSamples, nIL);
                }

                if (idx < 0 || idx >= nSamples) {
                    return jsonResponse({ detail: `TimeSlice index ${idx} out of range [0, ${nSamples - 1}] in the static web demo.` }, 404);
                }
                const inlines = await getAllInlines(vol, mode, volEntry, nIL);
                const out = new Float32Array(nIL * nXL);
                const rowStart = idx * nXL;
                const rowEnd = rowStart + nXL;
                for (let il = 0; il < nIL; il++) {
                    out.set(inlines[il].subarray(rowStart, rowEnd), il * nXL);
                }
                return binaryResponse(out, nIL, nXL);
            },
        },
        {
            method: 'GET',
            pattern: /^\/api\/refine\/(\d+)$/,
            handler: async (m) => {
                const runId = Number(m[1]);
                for (const key of ['clean', 'noisy']) {
                    const rec = await getRecordedRun(key);
                    if (rec && Number(rec.run.run_id) === runId) return jsonResponse(rec.run, 200);
                }
                return jsonResponse({ detail: 'Refine run not found: ' + runId }, 404);
            },
        },
        {
            method: 'ANY',
            pattern: /^\/api\/(?:llm|sgy|vds|zarr|db)(?:\/.*)?$/,
            handler: async (_m, url) => {
                if (url.pathname === '/api/vds/status') {
                    return jsonResponse({ available: false, detail: UNAVAILABLE_DETAIL }, 503);
                }
                if (url.pathname === '/api/sgy/info') {
                    return jsonResponse({ loaded: false, detail: UNAVAILABLE_DETAIL }, 503);
                }
                return jsonResponse({ detail: UNAVAILABLE_DETAIL }, 503);
            },
        },
        {
            method: 'POST',
            pattern: /^\/api\/(?:embed|predict|device|npy\/[^/]+\/(?:embed|mask|propagate|refine))$/,
            handler: async () => jsonResponse({ detail: UNAVAILABLE_DETAIL }, 503),
        },
        {
            method: 'DELETE',
            pattern: /^\/api\/.*$/,
            handler: async () => jsonResponse({ detail: UNAVAILABLE_DETAIL }, 503),
        },
        {
            method: 'POST',
            pattern: /^\/api\/.*$/,
            handler: async () => jsonResponse({ detail: UNAVAILABLE_DETAIL }, 503),
        },
    ];

    window.fetch = async function staticDemoFetch(input, init) {
        const rawUrl = typeof input === 'string' ? input : (input && input.url) || '';
        let parsed;
        try {
            parsed = new URL(rawUrl, window.location.origin);
        } catch (_) {
            return realFetch(input, init);
        }
        if (parsed.origin !== window.location.origin || !parsed.pathname.startsWith('/api/')) {
            return realFetch(input, init);
        }

        const method = ((init && init.method) || (typeof input === 'object' && input && input.method) || 'GET').toUpperCase();
        for (const route of ROUTES) {
            if (route.method !== 'ANY' && route.method !== method) continue;
            const match = parsed.pathname.match(route.pattern);
            if (match) return route.handler(match, parsed);
        }
        return jsonResponse({ detail: 'Not found in the static web demo.' }, 404);
    };

    async function replayRecordedRun(key) {
        const btns = [document.getElementById('btnReplayClean'), document.getElementById('btnReplayNoisy')].filter(Boolean);
        btns.forEach(b => { b.disabled = true; });
        try {
            const payload = await getRecordedRun(key);
            if (!payload) {
                setStatus('error', 'Recorded run unavailable in manifest.');
                return;
            }
            const { info, run } = payload;
            if (typeof compareMode !== 'undefined' && compareMode !== 'off' && typeof setCompareMode === 'function') {
                setCompareMode('off');
            }
            if (typeof sliceMode !== 'undefined' && sliceMode !== 'raw' && typeof setSliceMode === 'function') {
                setSliceMode('raw');
            }

            if (!volInfo || volInfo.name !== run.volume) {
                const manifest = await getManifest();
                const volMeta = manifest.volumes[run.volume].meta;
                const sel = document.getElementById('volumeSelect');
                if (sel) sel.value = run.volume;
                applyVolumeInfo(volMeta, run.volume, 'api/npy');
            }

            curDir = run.direction || 'inline';
            curIndex = Number(run.index);
            const dirSel = document.getElementById('dirSelect');
            if (dirSel) dirSel.value = curDir;
            if (typeof updateLineRangeLabel === 'function') updateLineRangeLabel();
            const sp = document.getElementById('slicePanel');
            if (sp) sp.classList.add('visible');

            await loadAndRenderSlice(curDir, curIndex);

            refineRun = run;
            refineSliceKey = currentSliceKey();
            selectRefineRound(run.best_round);
            renderRefinePanel();
            setStatus('ready', `Recorded with the local app on ${info.recorded_date} (SAM3, ${info.gpu_name}). Not computed in your browser.`);
        } catch (err) {
            setStatus('error', 'Replay failed: ' + err.message);
        } finally {
            btns.forEach(b => { b.disabled = false; });
        }
    }

    function injectBanner() {
        if (document.getElementById('demoBanner')) return;
        const style = document.createElement('style');
        style.textContent = [
            '#demoBanner{display:flex;align-items:center;gap:8px;flex-wrap:wrap;background:#1e3a5f;color:#fff;',
            'padding:5px 10px;font-size:12px;line-height:1.35;border-bottom:1px solid #0f243d;}',
            '#demoBanner .demo-text{flex:1;min-width:260px;}',
            '#demoBanner .demo-btn{background:#fff;color:#12263f;border:1px solid #9ab4d3;border-radius:3px;',
            'padding:2px 8px;font-size:11px;font-weight:bold;cursor:pointer;text-decoration:none;white-space:nowrap;}',
            '#demoBanner .demo-btn:hover{background:#e8f0fb;}',
            '#demoBanner .demo-btn:disabled{opacity:.6;cursor:wait;}',
            '#demoBanner .demo-link{background:transparent;color:#fff;border-color:#9ab4d3;}',
            '#demoBanner .demo-link:hover{background:rgba(255,255,255,0.14);}',
            '.main-container{height:calc(100vh - 138px) !important;}',
        ].join('');
        document.head.appendChild(style);

        const banner = document.createElement('div');
        banner.id = 'demoBanner';
        banner.setAttribute('role', 'region');
        banner.setAttribute('aria-label', 'Static web demo notice');

        const span = document.createElement('span');
        span.className = 'demo-text';
        span.textContent =
            'Static web demo. Browse the synthetic volumes, the low-frequency view and the noisy/clean compare in your browser. SAM3 segmentation and the QC loop run only in the local build.';

        const btnClean = document.createElement('button');
        btnClean.id = 'btnReplayClean';
        btnClean.className = 'demo-btn';
        btnClean.type = 'button';
        btnClean.textContent = 'Replay recorded SAM3 run';
        btnClean.title = 'Load recorded clean IL 24 (3 rounds) from the local GPU app';
        btnClean.onclick = () => replayRecordedRun('clean');

        const btnNoisy = document.createElement('button');
        btnNoisy.id = 'btnReplayNoisy';
        btnNoisy.className = 'demo-btn';
        btnNoisy.type = 'button';
        btnNoisy.textContent = 'Replay noisy gate';
        btnNoisy.title = 'Load recorded noisy IL 21 gate response from the local GPU app';
        btnNoisy.onclick = () => replayRecordedRun('noisy');

        const linkLocal = document.createElement('a');
        linkLocal.id = 'linkRunLocally';
        linkLocal.className = 'demo-btn demo-link';
        linkLocal.href = LOCAL_RUN_URL;
        linkLocal.target = '_blank';
        linkLocal.rel = 'noopener';
        linkLocal.textContent = 'Run it locally';

        banner.appendChild(span);
        banner.appendChild(btnClean);
        banner.appendChild(btnNoisy);
        banner.appendChild(linkLocal);
        document.body.insertBefore(banner, document.body.firstChild);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', injectBanner);
    } else {
        injectBanner();
    }
})();
