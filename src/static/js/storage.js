// storage.js — localStorage backup/restore
// ── localStorage 备份 (防崩溃丢失拾取数据) ─────────────
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
        console.warn('localStorage 备份失败:', e);
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
            // 兼容旧数据: 若无归一化坐标则用 snap 中的 canvas 尺寸反算
            nx: p.nx != null ? p.nx : (snap.canvasW ? p.x / snap.canvasW : null),
            ny: p.ny != null ? p.ny : (snap.canvasH ? p.y / snap.canvasH : null),
            sliceKey: key,
        })));
    });
    if (snap.yAxisUnit) yAxisUnit = snap.yAxisUnit;
    if (snap.velocity) velocity = snap.velocity;
    const total = [...picksBySlice.values()].reduce((s, a) => s + a.length, 0);
    setStatus('ready', `已恢复 ${total} 个拾取点`);
    // 恢复浏览位置 (如果卷已加载)
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
    const volLabel = snap.volName || '未知';
    const ageLabel = ageMin > 0 ? ageMin + ' 分钟前' : '刚刚';
    const msg = `发现未保存的拾取数据:\n\n` +
        `卷: ${volLabel}\n` +
        `点数: ${backup.total}\n` +
        `时间: ${ageLabel}\n\n` +
        `是否恢复？`;
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
        const ageStr = age < 60000 ? '刚刚'
                     : age < 3600000 ? Math.floor(age / 60000) + '分钟前'
                     : Math.floor(age / 3600000) + '小时前';
        const vol = snap.volName ? ` [${snap.volName}]` : '';
        el.textContent = `💾 ${total} 点${vol} · ${ageStr}`;
    } catch { el.textContent = ''; }
}

function clearAllPicks() {
    picksBySlice.clear();
    logitsMap = null; logitsWidth = 0; logitsHeight = 0;
    clearBackup();
}
