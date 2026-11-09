// Cross-platform python runner for npm scripts
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const isWin = process.platform === 'win32';
const venvPy = isWin 
  ? path.join('.venv', 'Scripts', 'python.exe')
  : path.join('.venv', 'bin', 'python');

const pythonBin = fs.existsSync(venvPy) ? venvPy : 'python';
const args = process.argv.slice(2);

const child = spawn(pythonBin, args, { stdio: 'inherit' });
child.on('exit', (code) => {
  process.exit(code || 0);
});
