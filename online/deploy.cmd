@echo off
rem Puts the online script editor on Firebase Hosting and sets its database rules.
rem Needs Node.js (https://nodejs.org, the LTS installer) and your Firebase project id.
cd /d "%~dp0"
where npx >nul 2>nul || (echo Node.js is not installed. Get the LTS installer from https://nodejs.org, then run this again. & pause & exit /b 1)
findstr /c:"PASTE-HERE" public\firebase-config.js >nul && (echo Paste your Firebase settings into public\firebase-config.js first. See README.md. & pause & exit /b 1)
set PROJECT=
if exist project-id.txt set /p PROJECT=<project-id.txt
if "%PROJECT%"=="" set /p PROJECT=Firebase project id (Project settings, "Project ID"): 
echo %PROJECT%>project-id.txt
call npx -y firebase-tools@14 login
call npx -y firebase-tools@14 deploy --only hosting,firestore:rules --project %PROJECT%
pause
