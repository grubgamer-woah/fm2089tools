// Bundles the Firebase web SDK into public/firebase.js. Needs Node: run `npm install` in online/dev first.
import { build } from 'esbuild';
import { fileURLToPath } from 'node:url';
const here = fileURLToPath(new URL('.', import.meta.url));
await build({
  entryPoints: [here + 'sdk-entry.js'], bundle: true, format: 'esm', minify: true, target: 'es2020',
  outfile: here + '../public/firebase.js', legalComments: 'none',
  banner: { js: '// Firebase web SDK (Apache-2.0, https://github.com/firebase/firebase-js-sdk), bundled by dev/build-sdk.mjs' },
});
