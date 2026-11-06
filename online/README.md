# FM2089 Online Studio

The desktop Translation Studio's own page, running on the web so the translation team edits one shared
script: the same list, editor, game-font preview, flags, Speakers, Credits, Validate, Import script and
Import multiple. Everyone signed in sees changes within a second or two. There is no ROM and no patch
building here (Build, Restart, Fonts, Mission titles, Export TSV and Online pack are hidden); the desktop
Studio still builds the patch.

`public/index.html` and `public/studio/` are copies of `studio/web` made by `node dev/sync-studio.mjs`;
run it again after changing the Studio's page. `public/online.js` answers the Studio's `/api/...`
requests from the database (JavaScript versions of the Studio's checks, saving, credits and import).

How the script travels:

1. **Studio to web.** In the desktop Studio, click **Online pack**. It saves `FM2089 online script.json`
   (the text, notes, flags, speaker names and portraits, the game font and the credits) in its `exports`
   folder. An admin uploads it with **Upload pack**. Lines nobody changed online take the pack's version;
   lines changed online keep theirs.
2. **Web to Studio.** **Export script** downloads every change made online since the last upload as a
   script `.md` (English, notes, Done and Hidden flags, speaker names, portraits and the credits). In the
   Studio, **Import script** loads it and asks you to pick wherever you also changed something since that
   upload. Then build the xdelta as usual.

## Roles, review and claims

- **Editors** suggest changes. A suggestion shows as "waiting for review" on its line; the shared script
  changes only when a reviewer or admin accepts it.
- **Reviewers** use **Review** to accept a suggestion, edit it and accept it, or reject it, with a note.
  Their own edits go straight in.
- **Admins** do the same, and also manage **Team** and upload packs.
- **Inbox** shows each person what happened to their suggestions and the reviewer's note.
- **Claims** mark untranslated or MTL lines as someone's for a week ("Claim this line" in the editor, or
  "Claim shown lines" for everything the list's filters show). Show > Claimed by me / by others lists them.

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
2. Turn on Google sign-in: open
   `https://console.firebase.google.com/project/<project-id>/authentication/providers`, click
   **Get started** if it shows, then **Google**, switch it on and save. (The console's menus move
   around; these links go straight to the page.)
3. Create the database: open `https://console.firebase.google.com/project/<project-id>/firestore`,
   click **Create database**, pick a location near the team and **production mode**.
4. Register a web app: open `https://console.firebase.google.com/project/<project-id>/settings/general`,
   add a **Web** app (`</>`, any nickname, no Hosting checkbox needed), and copy the `apiKey`,
   `authDomain`, `projectId` and `appId` it shows into `public/firebase-config.js`.
5. Install Node.js (LTS) from https://nodejs.org if it is not installed, then double-click `deploy.cmd`.
   It asks for the project id, opens a browser to sign in to Firebase, and uploads the page and the
   database rules. At the end it prints the page's address, `https://<project-id>.web.app`.
6. Open that address, sign in, and click **Make me the admin**. Then upload the Online pack and add the
   team under **Team**.

Run `deploy.cmd` again after the page or `firestore.rules` change.

## Files

- `public/` is the page: `index.html` and `studio/` (copied from the Studio), `online.js` and
  `online.css`, `firebase-config.js` and `firebase.js` (the Firebase web SDK, bundled so the page loads
  nothing from other sites).
- `firestore.rules` holds the database rules. `firebase.json` is the Hosting and emulator setup.
- `dev/` rebuilds `firebase.js` (`npm install`, then `node build-sdk.mjs`).

Testing without a real project: run `npx firebase-tools emulators:start --project demo-fm2089` here, with a
`firebase-config.js` whose projectId is `demo-fm2089`, then open
`http://localhost:5000/?emulator&as=someone@example.com` to sign in as a made-up account.

Database layout: `meta/access` (admins, reviewers, editors), `meta/script` (pack date and layout),
`meta/font`, `meta/portraits`, `meta/speakers`, `meta/project` (settings and credits), `files/{file}` (one
per game text file: its lines, their English, notes and flags, the last upload's version, and who changed
each line), `suggestions` (waiting and reviewed), `claims/{file}`, `history` and `presence`.
