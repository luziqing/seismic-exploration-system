// Syntax-check every frontend script. `node --check a.js b.js` only checks the first file,
// so each file gets its own `node --check` run.
const { spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const dir = path.join('src', 'static', 'js');
const files = fs.readdirSync(dir).filter(f => f.endsWith('.js')).sort();
let failed = 0;
for (const f of files) {
  const r = spawnSync(process.execPath, ['--check', path.join(dir, f)], { stdio: 'inherit' });
  if (r.status !== 0) { failed++; console.error(`FAIL  ${f}`); }
}
console.log(`${failed ? 'FAIL' : 'OK  '}  check:js — ${files.length - failed}/${files.length} files`);
process.exit(failed ? 1 : 0);
