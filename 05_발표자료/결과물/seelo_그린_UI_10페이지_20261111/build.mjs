import {build} from 'esbuild';
await build({entryPoints:['screens.jsx'],outfile:'.render.cjs',bundle:true,platform:'node',format:'cjs',packages:'external',jsx:'automatic',logLevel:'warning'});
await import('./.render.cjs');
