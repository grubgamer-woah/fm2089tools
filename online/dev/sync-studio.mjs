// Copies the desktop Studio's page (studio/web) into public/studio and makes public/index.html from its
// index.html, so the online editor shows the Studio's own screens. online.js connects them to the database.
// Run after the Studio's page changes: node dev/sync-studio.mjs
import fs from 'node:fs';
const web = new URL('../../studio/web/', import.meta.url), pub = new URL('../public/', import.meta.url);
fs.mkdirSync(new URL('studio/', pub), {recursive: true});
for (const f of ['app.js', 'style.css']) fs.copyFileSync(new URL(f, web), new URL('studio/' + f, pub));
let html = fs.readFileSync(new URL('index.html', web), 'utf8');
const swap = (from, to) => { if (!html.includes(from)) throw new Error('studio/web/index.html no longer has ' + from); html = html.replace(from, to); };
swap('<title>FM2089 Translation Studio</title>', '<title>FM2089 Online Studio</title>');
swap('<link rel="stylesheet" href="/style.css">', '<link rel="stylesheet" href="studio/style.css">\n<link rel="stylesheet" href="online.css">');
swap('<script src="/app.js"></script>', '<script type="module" src="online.js"></script>');
swap('<body>', '<body class="gated">');
swap('<html lang="en">', '<!-- Made by dev/sync-studio.mjs from studio/web/index.html; change that file instead. -->\n<html lang="en">');
fs.writeFileSync(new URL('index.html', pub), html);
console.log('public/index.html and public/studio/ updated from studio/web');
