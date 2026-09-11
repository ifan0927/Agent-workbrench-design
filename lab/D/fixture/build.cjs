const fs = require('node:fs');
fs.mkdirSync('dist', { recursive: true });
fs.copyFileSync('src.cjs', 'dist/index.cjs');
