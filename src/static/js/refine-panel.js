// refine-panel.js — Auto-refine (QC-driven prompt loop) and the round-by-round QC panel (scope S6,
// spec qc-refine-loop Requirement 5). Loaded after sam-client.js and survey-map.js; uses their globals
// (volInfo, curDir, curIndex, picksBySlice, logitsMap, setStatus, refreshSurveyFootprint).
//
// Defaults come from scripts/measure_refine.py (docs/MEASUREMENTS.md, 2026-11-13): SAM and the loop
// segment the RAW slice whatever view is displayed, and Auto-refine is on for NPY volumes.

let refineRun = null;          // last response of POST /api/npy/{vol}/refine
let refineSelected = null;     // round number shown on the canvas
let refineSliceKey = null;     // slice the run belongs to (currentSliceKey())

const REFINE_SAM_MODE = 'raw'; // measured: SAM on low-freq gives IoU 0.06 vs 0.43 on the noisy volume

function autoRefineAvailable() {
    return volInfo.source === 'api/npy' && !!volInfo.name && curDir !== 'timeslice';
}

function autoRefineOn() {
    const cb = document.getElementById('autoRefine');
    return !!(cb && cb.checked && autoRefineAvailable());
}

function updateAutoRefineControl() {
    const cb = document.getElementById('autoRefine');
    const lab = document.getElementById('autoRefineLabel');
    if (!cb) return;
    const ok = autoRefineAvailable();
    cb.disabled = !ok;
    if (lab) lab.title = ok
        ? 'Run SAM, check the mask with label-free QC and add up to 2 corrective points (max 3 rounds)'
        : 'Auto-refine works on inline and crossline slices of the demo volumes';
}

async function runRefine(picks) {
    const body = {
        direction: curDir, index: curIndex, mode: REFINE_SAM_MODE, target_type: 'deep_target',
        points: picks.map(p => [p.nx, p.ny]), labels: picks.map(p => p.label), write_mask: true,
    };
    setStatus('loading', 'Running SAM with QC refine (up to 3 rounds)...');
    const resp = await fetch(`/api/npy/${encodeURIComponent(volInfo.name)}/refine`, {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)
    });
    if (!resp.ok) {
        let msg = `HTTP ${resp.status}`;
        try { msg = (await resp.json()).detail || msg; } catch (e) { /* not JSON */ }
        throw new Error(msg);
    }
    refineRun = await resp.json();
    refineSliceKey = currentSliceKey();
    selectRefineRound(refineRun.best_round);
    renderRefinePanel();
    if (typeof refreshSurveyFootprint === 'function') refreshSurveyFootprint();
    const best = refineRun.rounds[refineRun.best_round - 1];
    setStatus('ready', `QC refine: ${refineRun.rounds.length} round(s), best round ${refineRun.best_round}, ` +
                       `QC score ${best.score.toFixed(3)}. ${refineRun.stop_message}`);
    return refineRun;
}

function selectRefineRound(n) {
    if (!refineRun) return;
    const r = refineRun.rounds[n - 1];
    if (!r) return;
    refineSelected = n;
    const [rows, cols] = refineRun.grid_shape;
    const flat = new Float32Array(rows * cols);
    for (let i = 0; i < rows; i++) for (let j = 0; j < cols; j++) flat[i * cols + j] = r.mask[i][j];
    logitsHeight = rows;
    logitsWidth = cols;
    logitsMap = flat;
    window._lastSamScore = r.score;
    drawSeismic();
    renderRefinePanel();
}

// Corrective points of the selected round, as hollow diamonds (user points stay filled squares).
// Called by drawSeismic() inside its zoom transform.
function drawRefineOverlay(c, w, h) {
    if (!refineRun || refineSliceKey !== currentSliceKey() || !refineSelected) return;
    const [rows, cols] = refineRun.grid_shape;
    const r = refineRun.rounds[refineSelected - 1];
    r.prompts.filter(p => p.source === 'correction').forEach(p => {
        const x = (p.col + 0.5) / cols * w, y = (p.row + 0.5) / rows * h, s = 7;
        c.beginPath();
        c.moveTo(x, y - s); c.lineTo(x + s, y); c.lineTo(x, y + s); c.lineTo(x - s, y); c.closePath();
        c.lineWidth = 2.5;
        c.strokeStyle = 'black';
        c.stroke();
        c.lineWidth = 1.5;
        c.strokeStyle = p.label === 1 ? '#00c853' : '#ff1744';
        c.stroke();
    });
}

function _fmt(x, d = 3) { return (x === null || x === undefined) ? '–' : Number(x).toFixed(d); }

function renderRefinePanel() {
    const panel = document.getElementById('refinePanel');
    const body = document.getElementById('refinePanelBody');
    if (!panel || !body) return;
    if (!refineRun) { panel.style.display = 'none'; return; }
    panel.style.display = '';
    const run = refineRun;
    const title = document.getElementById('refinePanelTitle');
    if (title) title.textContent = `QC refine · ${run.direction === 'crossline' ? 'XL ' + (volInfo.xlMin + run.index) : 'IL ' + (volInfo.ilMin + run.index)}`;
    const hasTruth = run.rounds.some(r => r.truth_reference);
    let html = '<table class="refine-table"><thead><tr><th>Round</th><th>QC score</th><th>Δ</th>' +
               '<th>Correction added</th><th>Best</th>' + (hasTruth ? '<th title="Overlap with the synthetic ground truth. Shown for reference only; the loop never sees it.">Truth IoU<br><small>(reference)</small></th>' : '') +
               '</tr></thead><tbody>';
    run.rounds.forEach(r => {
        const c = r.correction;
        const corr = c ? `${c.label === 1 ? '+ include' : '− exclude'} (${c.kind}, ${c.region_px} px)` : '–';
        const delta = r.delta === null || r.delta === undefined ? '–' : (r.delta >= 0 ? '+' : '') + r.delta.toFixed(3);
        const cls = [r.round === refineSelected ? 'sel' : '', r.round === run.best_round ? 'best' : ''].join(' ');
        html += `<tr class="${cls}" data-round="${r.round}"><td>${r.round}</td><td>${_fmt(r.score)}</td>` +
                `<td>${delta}</td><td>${corr}</td><td>${r.round === run.best_round ? '★' : ''}</td>` +
                (hasTruth ? `<td class="ref">${r.truth_reference ? _fmt(r.truth_reference.iou) : '–'}</td>` : '') + '</tr>';
    });
    html += '</tbody></table>';
    let note = run.stop_message;
    const m1 = run.rounds[0] && run.rounds[0].metrics;
    if (run.stop_reason === 'qc_unreliable' && m1 && m1.target_like_fraction !== null && m1.target_like_fraction !== undefined) {
        note += ` ${Math.round(m1.target_like_fraction * 100)}% of the slice looks like the clicked area ` +
                `(limit ${Math.round(run.constants.GATE_MAX_TARGET_LIKE_FRAC * 100)}%), so the mask is kept as SAM made it.`;
    }
    if (run.stop_reason === 'no_gain') note += ' The earlier, better round is kept.';
    html += `<div class="refine-stop">${note}</div>` +
            `<div class="refine-hint">Click a row to show that round. ◇ = corrective point added by the loop. ` +
            `Best round written to the volume mask.</div>`;
    body.innerHTML = html;
    body.querySelectorAll('tr[data-round]').forEach(tr => {
        tr.onclick = () => selectRefineRound(Number(tr.dataset.round));
    });
}

function clearRefine() {
    refineRun = null; refineSelected = null; refineSliceKey = null;
    renderRefinePanel();
}

(function initRefinePanel() {
    const t = document.getElementById('refinePanelToggle');
    const b = document.getElementById('refinePanelBody');
    if (t && b) t.onclick = () => {
        const hidden = b.style.display === 'none';
        b.style.display = hidden ? '' : 'none';
        t.textContent = hidden ? '–' : '+';
    };
    const x = document.getElementById('refinePanelClose');
    if (x) x.onclick = () => clearRefine();
    updateAutoRefineControl();
})();
