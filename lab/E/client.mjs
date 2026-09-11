let text = '';
for await (const data of process.stdin) text += data;
const response = await fetch('http://127.0.0.1:4771', { method: 'POST', body: text });
console.log(await response.text());
if (!response.ok) process.exitCode = 1;
