@echo off
rem Puts the online script editor on Firebase Hosting and sets its database rules.
rem Needs Node.js (https://nodejs.org, the LTS installer) and your Firebase project id.
cd /d "%~dp0"
node --version > deploy-log.txt 2>&1
where npx >nul 2>nul || (echo Node.js is not installed. Get the LTS installer from https://nodejs.org, then run this again. & pause & exit /b 1)
rem npm stops with ENOENT when this folder is missing (a known npm-on-Windows problem)
if not exist "%APPDATA%\npm" mkdir "%APPDATA%\npm"
findstr /c:"PASTE-HERE" public\firebase-config.js >nul && (echo Paste your Firebase settings into public\firebase-config.js first. See README.md. & pause & exit /b 1)
set PROJECT=
if exist project-id.txt set /p PROJECT=<project-id.txt
if "%PROJECT%"=="" set /p PROJECT=Firebase project id (Project settings, "Project ID"): 
echo %PROJECT%>project-id.txt
call npx -y firebase-tools@15 login
call node dev\deploy-config.mjs || (pause & exit /b 1)
echo Deploying... (everything it prints also goes to deploy-log.txt)
call npx -y firebase-tools@15 deploy --only hosting,firestore:rules,auth --config firebase.deploy.json --project %PROJECT% > deploy-log.txt 2>&1
type deploy-log.txt
pause
