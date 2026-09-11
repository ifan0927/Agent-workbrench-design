// Per-attempt test service with isolated disk state; no external dependencies.
const http = require('node:http');
const fs = require('node:fs');
http.createServer((req, res) => {
  if (req.url === '/health') { res.end('ready'); return; }
  if (req.url !== '/value') { res.writeHead(404).end(); return; }
  if (req.method === 'PUT') {
    let data = '';
    req.on('data', chunk => { data += chunk; });
    req.on('end', () => { fs.writeFileSync('/data/value', data); res.end('saved'); });
  } else { res.end(fs.existsSync('/data/value') ? fs.readFileSync('/data/value') : ''); }
}).listen(8080, '0.0.0.0');
