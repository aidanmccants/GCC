// Rebuilds the map page from src/template.html and the map data, then copies it
// to src/page.html where the Worker imports it. Set PYTHON if your command is not "python".
import { execFileSync } from 'node:child_process';
import { copyFileSync } from 'node:fs';

execFileSync(process.env.PYTHON || 'python', ['../src/assemble.py', '../tools/data.js'], { stdio: 'inherit' });
copyFileSync('../index.html', 'src/page.html');
console.log('built src/page.html');
