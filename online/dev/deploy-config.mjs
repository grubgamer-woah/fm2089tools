// Writes firebase.deploy.json: firebase.json plus Google sign-in, so deploy.cmd also turns sign-in on.
// The sign-in screen's support email is the Google account signed in to the Firebase CLI (kept out of the repo).
import { execSync } from 'node:child_process';
import fs from 'node:fs';
const root = new URL('..', import.meta.url);
let email;
try {
  const out = execSync('npx -y firebase-tools@15 login:list --json', {encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore']});
  email = (JSON.parse(out.slice(out.indexOf('{'))).result || [])[0]?.user?.email;
} catch { /* reported below */ }
if (!email) {
  console.error('Not signed in to the Firebase CLI, so Google sign-in cannot be set up. Run deploy.cmd again and sign in.');
  process.exit(1);
}
const config = JSON.parse(fs.readFileSync(new URL('firebase.json', root), 'utf8'));
config.auth = {providers: {googleSignIn: {oAuthBrandDisplayName: 'FM2089 Online Script', supportEmail: email}}};
fs.writeFileSync(new URL('firebase.deploy.json', root), JSON.stringify(config, null, 2));
console.log(`Google sign-in will be turned on (support email ${email}).`);
