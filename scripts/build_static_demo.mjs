// Build the zero-serverless static Vercel bundle in dist/.
// Uses Node.js built-ins only; exits non-zero if injection fails, .py files leak, or dist >= 4 MB.
'use strict';

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT = path.resolve(__dirname, '..');
const DIST = path.join(ROOT, 'dist');
const MAX_DIST_BYTES = 4 * 1024 * 1024;
const SHIM_TAG = '<script src="/demo/demo-shim.js"></script>';

function copyRecursive(src, dst) {
    const st = fs.statSync(src);
    if (st.isDirectory()) {
        fs.mkdirSync(dst, { recursive: true });
        for (const name of fs.readdirSync(src)) {
            copyRecursive(path.join(src, name), path.join(dst, name));
        }
    } else {
        fs.mkdirSync(path.dirname(dst), { recursive: true });
        fs.copyFileSync(src, dst);
    }
}

function collectFiles(dir, out = []) {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
        const p = path.join(dir, entry.name);
        if (entry.isDirectory()) collectFiles(p, out);
        else out.push(p);
    }
    return out;
}

function main() {
    fs.rmSync(DIST, { recursive: true, force: true });
    fs.mkdirSync(DIST, { recursive: true });

    for (const rel of ['LICENSE', path.join('src', 'static'), 'demo']) {
        const src = path.join(ROOT, rel);
        if (!fs.existsSync(src)) {
            console.error(`Missing required source path: ${rel}`);
            process.exit(1);
        }
        const target = rel === path.join('src', 'static') ? path.join(DIST, 'static') : path.join(DIST, rel);
        copyRecursive(src, target);
    }

    const indexPath = path.join(ROOT, 'index.html');
    const rawHtml = fs.readFileSync(indexPath, 'utf8');
    const eol = rawHtml.includes('\r\n') ? '\r\n' : '\n';
    const scriptMatch = rawHtml.match(/^([ \t]*)<script\b/m);
    if (!scriptMatch) {
        console.error('Could not find <script tag in index.html for shim injection.');
        process.exit(1);
    }
    const idx = scriptMatch.index;
    const indent = scriptMatch[1] || '';
    const injectedHtml = rawHtml.slice(0, idx) + `${indent}${SHIM_TAG}${eol}` + rawHtml.slice(idx);
    if (injectedHtml === rawHtml) {
        console.error('Shim injection produced no change in index.html.');
        process.exit(1);
    }
    fs.writeFileSync(path.join(DIST, 'index.html'), injectedHtml, 'utf8');

    const files = collectFiles(DIST);
    const pyFiles = files.filter(f => f.endsWith('.py'));
    if (pyFiles.length > 0) {
        console.error('Forbidden .py files found in dist:', pyFiles);
        process.exit(1);
    }

    const totalBytes = files.reduce((sum, f) => sum + fs.statSync(f).size, 0);
    console.log(`Built static demo: ${files.length} files, ${totalBytes} bytes (${(totalBytes / (1024 * 1024)).toFixed(3)} MiB)`);
    if (totalBytes >= MAX_DIST_BYTES) {
        console.error(`dist/ size ${totalBytes} exceeds limit (< ${MAX_DIST_BYTES} bytes).`);
        process.exit(1);
    }
}

main();
