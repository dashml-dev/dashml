const fs = require('fs');
const html = fs.readFileSync('output_observable/index.html', 'utf-8');
const m = html.match(/<script>([\s\S]*?)<\/script>/g);
const script = m[1].replace(/<\/?script>/g, '');
fs.writeFileSync('_script_block.js', script);
console.log('Extracted script block 1 to _script_block.js');
console.log('Lines:', script.split('\n').length);
