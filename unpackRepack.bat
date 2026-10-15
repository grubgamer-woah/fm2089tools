@Echo off
SETLOCAL

SET "unpacked_jp=FM2089_JP_UNPACK"
SET "unpacked_tr=FM2089_TR_UNPACK"
SET "txt_jp=./text/JP/"
SET "txt_tr=./text/translated/"
SET "rom_tr=fm2089_tr.nds"

IF NOT EXIST "./temp/" (mkdir "./temp/")
IF NOT EXIST "%txt_jp%" (mkdir "%txt_jp%")
IF NOT EXIST "%txt_tr%" (mkdir "%txt_tr%")

ECHO ######################
ECHO This script will do:
ECHO 1. look for a valid rom in current folder
ECHO 2. unpack rom with NitroPacker.exe
ECHO 3. extract all .msg files from unpacked rom
ECHO 4. convert all .txt files in the traslated folder
ECHO 5. repack the rom
ECHO ######################
ECHO.
PAUSE

ECHO.
ECHO ### Looking for JP rom...
REM Look for a file with .nds extention
REM Once we found a rom, validate against known checksums

FOR %%f IN ("*.nds") DO (
    python -c "import fm2089Utils; fm2089Utils.validateRom('%%f')"
    IF ERRORLEVEL 0 (
        ECHO valid rom found!
        SET rom="%%f"
        GOTO :unpack_jp_rom
    )
)

IF "%rom%" == "" (
    ECHO.
    ECHO ### ERROR no valid rom found!
    ECHO ### please place a valid FM2089 rom next to this file
    ECHO.
    PAUSE
    EXIT
)


:unpack_jp_rom
ECHO.
ECHO ### Check if we need to unpack JP rom...

REM Check if we already unpacked the JP rom
REM !!! This hangs in an infinite loop for some reason?
REM IF EXIST "./temp/%unpacked_jp%" (
REM    python -c "import fm2089Utils; fm2089Utils.validateUnpack('./temp/%unpacked_jp%')"
REM    IF ERRORLEVEL 0 (
REM        ECHO JP rom already unpacked, skipping
REM        GOTO :jp_msg_to_txt
REM    ELSE
REM        rmdir /s /q "./temp/"
REM    )
REM )

IF EXIST "./temp/%unpacked_jp%" (
    GOTO :jp_msg_to_txt
)

ECHO Creating temp folder
rmdir /s /q "./temp/"

REM We couldn't find a valid unpacked JP rom, let's unpack the rom we found
IF NOT EXIST "./NitroPacker.exe" (
    ECHO #ERROR NitroPacker.exe not found, please download it from:
    ECHO https://github.com/haroohie-club/NitroPacker/releases/
    PAUSE
    EXIT
)

ECHO NitroPacker.exe found, unpacking JP rom... (this might take a while)
PAUSE
NitroPacker.exe unpack -r %rom% -o "./temp/%unpacked_jp%" -p "%unpacked_jp%"

ECHO unpacking done!
PAUSE

:jp_msg_to_txt
ECHO.
ECHO ### Convert JP script to txt
PAUSE

IF EXIST %txt_jp% (
    python -c "import fm2089Utils; fm2089Utils.validateTxt('%txt_jp%')"
    IF %ERRORLEVEL% == 0 (
        ECHO JP text already exported, skipping...
        GOTO :tr_txt_to_msg
    )

    rmdir /s /q "%txt_jp%"
)

python msgToTxt.py "./temp/%unpacked_jp%/data/data/font/"
IF NOT ERRORLEVEL 0 ( 
    PAUSE
    EXIT
)

:tr_txt_to_msg
REM Look for translated .txt and convert them, never skip this step!
REM Copy unpacked jp project so we can use it for repacking tr
ECHO.
ECHO ### Copying unpacked files for translated rom...

IF NOT EXIST "./temp/%unpacked_tr%" (
    xcopy "./temp/%unpacked_jp%" "./temp/%unpacked_tr%" /E /I /Q
    ren .\temp\%unpacked_tr%\%unpacked_jp%.xml %unpacked_tr%.xml
)

REM Check if there are any translated .txt files
ECHO.
ECHO ### Coverting translated txt to msg files...

dir /b /s /a "%txt_tr%" | findstr .>nul || (
    ECHO No translated .txt files found in %txt_tr%
    PAUSE
    EXIT
)

python txtToMsg.py %txt_tr%
IF NOT ERRORLEVEL 0 (
    PAUSE
    EXIT
)

ECHO.
ECHO ### Repacking translated rom...
NitroPacker.exe pack -p ".\temp\%unpacked_tr%\%unpacked_tr%.xml" -r "%rom_tr%"
ECHO ### packing done!
PAUSE