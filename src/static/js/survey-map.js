// survey-map.js — small plan-view map of the survey (IL × XL) in the corner of the section view.
// Shows where the current slice sits, the footprint of the volume mask (voxels per trace),
// and lets the user click to jump to an inline / crossline.
// Loaded after sgy-client.js and sam-client.js; uses their globals (volInfo, curDir, curIndex,
// loadAndRenderSlice, VOL_MASK_NAME, setStatus).

const SURVEY_MAP_MAX_PX = 160;   // longer side of the map, CSS pixels

const surveyMap = {
    panel: document.getElementById('surveyMap'),
    canvas: document.getElementById('surveyMapCanvas'),
    info: document.getElementById('surveyMapInfo'),
    footprint: null,      // Float32Array, row-major (nIL, nXL)
    footprintMax: 0,
    footprintVol: null,   // volume name the footprint belongs to
    hover: null,          // {il, xl} indices under the mouse
};

function surveyMapGeometry() {
    const nIL = volInfo.ilCount, nXL = volInfo.xlCount;
    const scale = SURVEY_MAP_MAX_PX / Math.max(nIL, nXL, 1);
    return { nIL, nXL, w: Math.max(1, Math.round(nXL * scale)), h: Math.max(1, Math.round(nIL * scale)), sx: scale, sy: scale };
}

async function refreshSurveyFootprint() {
    surveyMap.footprint = null;
    surveyMap.footprintMax = 0;
    surveyMap.footprintVol = volInfo.name;
    if (volInfo.source !== 'api/npy' || !volInfo.name) { drawSurveyMap(); return; }
    try {
        const r = await fetch(`/api/npy/${encodeURIComponent(volInfo.name)}/mask/${VOL_MASK_NAME}/footprint`);
        if (r.ok) {
            const rows = +r.headers.get('X-Rows'), cols = +r.headers.get('X-Cols');
            const arr = new Float32Array(await r.arrayBuffer());
            if (rows === volInfo.ilCount && cols === volInfo.xlCount && arr.length === rows * cols) {
                let mx = 0;
                for (let i = 0; i < arr.length; i++) if (arr[i] > mx) mx = arr[i];
                surveyMap.footprint = arr;
                surveyMap.footprintMax = mx;
            }
        }
    } catch (e) { /* no mask yet: draw the map without a footprint */ }
    drawSurveyMap();
}

function updateSurveyMap() {
    if (!surveyMap.panel) return;
    if (!volInfo.name || !volInfo.ilCount || !volInfo.xlCount) { surveyMap.panel.style.display = 'none'; return; }
    surveyMap.panel.style.display = 'block';
    if (surveyMap.footprintVol !== volInfo.name) refreshSurveyFootprint();
    else drawSurveyMap();
}

function drawSurveyMap() {
    const c = surveyMap.canvas;
    if (!c || !volInfo.ilCount || !volInfo.xlCount) return;
    const g = surveyMapGeometry();
    const dpr = window.devicePixelRatio || 1;
    c.style.width = g.w + 'px'; c.style.height = g.h + 'px';
    c.width = Math.round(g.w * dpr); c.height = Math.round(g.h * dpr);
    const ctx = c.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    ctx.fillStyle = '#eef1f4';
    ctx.fillRect(0, 0, g.w, g.h);

    // Volume-mask footprint: opacity grows with voxels per trace
    const fp = surveyMap.footprint;
    let traces = 0;
    if (fp && surveyMap.footprintMax > 0) {
        for (let il = 0; il < g.nIL; il++) {
            for (let xl = 0; xl < g.nXL; xl++) {
                const v = fp[il * g.nXL + xl];
                if (v <= 0) continue;
                traces++;
                ctx.fillStyle = `rgba(230,120,0,${(0.25 + 0.75 * v / surveyMap.footprintMax).toFixed(3)})`;
                ctx.fillRect(xl * g.sx, il * g.sy, Math.ceil(g.sx), Math.ceil(g.sy));
            }
        }
    }

    // Current slice position
    ctx.strokeStyle = '#d00000'; ctx.lineWidth = 2;
    if (curDir === 'inline') {
        const y = (curIndex + 0.5) * g.sy;
        ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(g.w, y); ctx.stroke();
    } else if (curDir === 'crossline') {
        const x = (curIndex + 0.5) * g.sx;
        ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, g.h); ctx.stroke();
    } else {
        ctx.strokeRect(1, 1, g.w - 2, g.h - 2);
    }

    // Hover crosshair
    if (surveyMap.hover) {
        ctx.strokeStyle = 'rgba(0,0,0,0.35)'; ctx.lineWidth = 1;
        ctx.strokeRect(surveyMap.hover.xl * g.sx, surveyMap.hover.il * g.sy, Math.max(1, g.sx), Math.max(1, g.sy));
    }

    ctx.strokeStyle = '#555'; ctx.lineWidth = 1;
    ctx.strokeRect(0.5, 0.5, g.w - 1, g.h - 1);

    if (surveyMap.info) {
        let pos;
        if (curDir === 'inline') pos = `Inline ${volInfo.ilMin + curIndex}`;
        else if (curDir === 'crossline') pos = `Crossline ${volInfo.xlMin + curIndex}`;
        else pos = `Time slice ${volInfo.dtUs ? (curIndex * volInfo.dtUs / 1000).toFixed(0) + ' ms' : '#' + curIndex}`;
        const hov = surveyMap.hover ? ` · IL ${volInfo.ilMin + surveyMap.hover.il}, XL ${volInfo.xlMin + surveyMap.hover.xl}` : '';
        const mask = fp ? ` · Mask: ${traces} traces` : '';
        surveyMap.info.textContent = pos + mask + hov;
    }
}

function surveyMapCellAt(e) {
    const g = surveyMapGeometry();
    const rect = surveyMap.canvas.getBoundingClientRect();
    const xl = Math.floor((e.clientX - rect.left) / (rect.width / g.nXL));
    const il = Math.floor((e.clientY - rect.top) / (rect.height / g.nIL));
    if (il < 0 || il >= g.nIL || xl < 0 || xl >= g.nXL) return null;
    return { il, xl };
}

if (surveyMap.canvas) {
    surveyMap.canvas.addEventListener('mousemove', e => { surveyMap.hover = surveyMapCellAt(e); drawSurveyMap(); });
    surveyMap.canvas.addEventListener('mouseleave', () => { surveyMap.hover = null; drawSurveyMap(); });
    surveyMap.canvas.addEventListener('click', e => {
        const cell = surveyMapCellAt(e);
        if (!cell) return;
        // Crossline view: jump to the clicked crossline. Inline or time-slice view: open the clicked inline.
        const dir = curDir === 'crossline' ? 'crossline' : 'inline';
        if (dir !== curDir) {
            curDir = dir;
            const sel = document.getElementById('dirSelect');
            if (sel) sel.value = dir;
            if (typeof updateLineRangeLabel === 'function') updateLineRangeLabel();
        }
        curIndex = dir === 'inline' ? cell.il : cell.xl;
        loadAndRenderSlice(curDir, curIndex);
        if (typeof updateAxes === 'function') updateAxes();
    });
}

const surveyMapToggle = document.getElementById('surveyMapToggle');
if (surveyMapToggle) surveyMapToggle.onclick = () => {
    const body = document.getElementById('surveyMapBody');
    const hidden = body.style.display === 'none';
    body.style.display = hidden ? 'block' : 'none';
    surveyMapToggle.textContent = hidden ? '–' : '+';
    surveyMapToggle.title = hidden ? 'Hide survey map' : 'Show survey map';
};

updateSurveyMap();
