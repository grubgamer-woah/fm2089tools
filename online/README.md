# FM2089 Online Script

A web page where the translation team edits the script together. Everyone signed in sees each other's
changes within a second or two, sees who is on which line, and can look up who changed what. There is no
ROM and no patch building here: the desktop Translation Studio still builds the patch.

How the script travels:

1. **Studio to web.** In the desktop Studio, click **Online pack**. It saves `FM2089 online script.json`
   (the Japanese and English text, notes, speaker names and font widths; no ROM data beyond the text) in
   its `exports` folder. An admin uploads that file with **Upload pack**. Lines nobody changed online take
   the pack's English; lines someone changed online keep their online text.
2. **Web to Studio.** **Download changes** saves every line changed online since the last upload as a
   script `.md`, the same kind the Studio's Export script makes. In the Studio, **Import script** (or
   **Import multiple**) loads it, and asks you to pick where you also changed a line in the Studio since
   that upload. **Download full script** saves the whole script as a project.json instead; Import script
   takes every line from it without asking. Then build the xdelta in the Studio as usual.

It runs on Firebase's free plan (Spark): Google sign-in, the Firestore database and Hosting. A team of a
few people uses a small part of the free daily limits (50,000 reads and 20,000 writes): opening the
page reads about 160 documents, and each saved edit is one or two writes.

## Who can get in

Only Google accounts on the team list. The first person to sign in on a new database is offered the
admin role; after that, admins add or remove people under **Team**. The rules in `firestore.rules` are
what enforce this, so the page itself holds nothing secret and the settings in `firebase-config.js` are
safe to share.

## Setting it up (once)

1. Go to https://console.firebase.google.com, click **Create a project** and give it a name. Google
   Analytics is not needed.
2. **Build > Authentication > Get started > Sign-in method > Google**: turn it on and save.
3. **Build > Firestore Database > Create database**: pick a location near the team and **production mode**.
4. **Project settings** (gear icon) **> Your apps > Web** (`</>`): register an app (any nickname, no
   Hosting checkbox needed). Copy the `apiKey`, `authDomain`, `projectId` and `appId` it shows into
   `public/firebase-config.js`.
5. Install Node.js (LTS) from https://nodejs.org if it is not installed, then double-click `deploy.cmd`.
   It asks for the project id, opens a browser to sign in to Firebase, and uploads the page and the
   database rules. At the end it prints the page's address, `https://<project-id>.web.app`.
6. Open that address, sign in, and click **Make me the admin**. Then upload the Online pack and add the
   team under **Team**.

Run `deploy.cmd` again after the page or `firestore.rules` change.

## Files

- `public/` is the page: `index.html`, `app.js`, `style.css`, `firebase-config.js` and `firebase.js`
  (the Firebase web SDK, bundled so the page loads nothing from other sites).
- `firestore.rules` holds the database rules. `firebase.json` is the Hosting and emulator setup.
- `dev/` rebuilds `firebase.js` (`npm install`, then `node build-sdk.mjs`).

Testing without a real project: run `npx firebase-tools emulators:start --project demo-fm2089` here, with a
`firebase-config.js` whose projectId is `demo-fm2089`, then open
`http://localhost:5000/?emulator&as=someone@example.com` to sign in as a made-up account.

Database layout: `meta/access` (team list), `meta/script` (pack date, font widths, portraits),
`meta/speakers`, `files/{file}` (one per game text file: its lines, English, notes, the last uploaded
English, and who changed each line), `history` (one item per finished edit) and `presence` (who is online).
