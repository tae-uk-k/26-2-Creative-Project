import { build } from 'esbuild';
import { mkdir, copyFile } from 'node:fs/promises';

await mkdir('검수', { recursive: true });
await build({ entryPoints: ['screens.jsx'], outfile: '.render.cjs', bundle: true, platform: 'node', format: 'cjs', packages: 'external', jsx: 'automatic', logLevel: 'warning' });
await import('./.render.cjs');
process.stdout.write('정적 HTML과 화면 목록 생성 완료\n');
