// storage.js — localStorage backup/restore
// ── localStorage backup (keeps picks safe after a crash) ─────────────
const LS_KEY = 'sam3_picks_backup';
const LS_VERSION = 2;

// References global variables from app.js:
//   picksBySlice, curDir, curIndex, yAxisUnit, velocity, canvas, volInfo, activePicks
// Also references: setStatus, drawSeismic, syncYAxis, updateLineRangeLabel, loadAndRenderSlice

function serializePicks() {
    const picks = {};
    picksBySlice.forEach((pts, key) => {
        picks[key] = pts.map(p => ({
            x: p.x, y: p.y, nx: p.nx, ny: p.ny,
            il: p.il, xl: p.xl,
            time_ms: p.time_ms, depth_m: p.depth_m,
            yUnit: p.yUnit, color: p.color,
            label: p.label,
        }));
    });
    return picks;
}

function saveToLocalStorage() {
    const snapshot = {
        version: LS_VERSION,
        timestamp: Date.now(),
        volName: volInfo.name || null,
        curDir, curIndex,
        yAxisUnit, velocity,
        canvasW: canvas.width, canvasH: canvas.height,
        picks: serializePicks(),
    };
    try {
        localStorage.setItem(LS_KEY, JSON.stringify(snapshot));
        updateBackupStatus();
    } catch (e) {
        console.warn('localStorage backup failed:', e);
    }
}

function clearBackup() {
    try { localStorage.removeItem(LS_KEY); } catch {}
    updateBackupStatus();
}

function checkForBackup() {
    try {
        const raw = localStorage.getItem(LS_KEY);
        if (!raw) return null;
        const snap = JSON.parse(raw);
        if (!snap.version || !snap.picks) return null;
        const total = Object.values(snap.picks)
            .reduce((s, arr) => s + (Array.isArray(arr) ? arr.length : 0), 0);
        if (total === 0) return null;
        return { snapshot: snap, total };
    } catch { return null; }
}

function restoreFromBackup(snap) {
    picksBySlice.clear();
    Object.entries(snap.picks).forEach(([key, pts]) => {
        if (!Array.isArray(pts) || pts.length === 0) return;
        picksBySlice.set(key, pts.map(p => ({
            ...p,
            // Old data: without normalised coordinates, derive them from the canvas size in snap
            nx: p.nx != null ? p.nx : (snap.canvasW ? p.x / snap.canvasW : null),
            ny: p.ny != null ? p.ny : (snap.canvasH ? p.y / snap.canvasH : null),
            sliceKey: key,
        })));
    });
    if (snap.yAxisUnit) yAxisUnit = snap.yAxisUnit;
    if (snap.velocity) velocity = snap.velocity;
    const total = [...picksBySlice.values()].reduce((s, a) => s + a.length, 0);
    setStatus('ready', `Restored ${total} picks`);
    // Restore the browse position (if the volume is loaded)
    if (volInfo.name && snap.curDir) {
        curDir = snap.curDir;
        curIndex = snap.curIndex || 0;
        const dirSel = document.getElementById('dirSelect');
        if (dirSel) dirSel.value = curDir;
        const yUnitSel = document.getElementById('yUnitSelect');
        if (yUnitSel) yUnitSel.value = yAxisUnit;
        syncYAxis(); updateLineRangeLabel();
        loadAndRenderSlice(curDir, curIndex);
    } else {
        drawSeismic();
    }
}

function showRecoveryDialog(backup) {
    const snap = backup.snapshot;
    const ageMin = Math.floor((Date.now() - (snap.timestamp || 0)) / 60000);
    const volLabel = snap.volName || 'unknown';
    const ageLabel = ageMin > 0 ? ageMin + ' min ago' : 'just now';
    const msg = `Found unsaved picks:\n\n` +
        `Volume: ${volLabel}\n` +
        `Points: ${backup.total}\n` +
        `Time: ${ageLabel}\n\n` +
        `Restore them?`;
    if (confirm(msg)) {
        restoreFromBackup(snap);
    } else {
        clearBackup();
    }
}

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

function clearAllPicks() {
    picksBySlice.clear();
    logitsMap = null; logitsWidth = 0; logitsHeight = 0;
    clearBackup();
}
