# fm2089tools

**New:** [`studio/`](studio/README.md) is a GUI editor that reads the text straight from the ROM and builds an xdelta English patch with one button (no NitroPacker needed).
These tools allow you to both export and import text from a .msg file and and can be used to make your own translation.
This tools were written as an improvement of [MSGExporter](https://github.com/neuroKip/MSGExporter) (check the README there for some more info)

## unpackRepack.bat
This is supposed to be a one click export/import script for quick testing purposes, put the rom in the same directory and run it.
For this script to work you will need the [NitroPacker](https://github.com/haroohie-club/NitroPacker) next to it.
The script will unpack a rom using NitroPacker and run msgToTxt.py to export the game's text to `./text/JP`.
If text files are found in `./text/translated` it will run txtToMsg.py on them and repack the rom. 

## conversionTables.py
This file contains the game's font which was extracted from the file msgcmn.fnt using [SERFontEditor](https://www.romhacking.net/utilities/624/).

## msgToTxt.py
This is the script used to convert the in game text to plain text:
`py msgToTxt.py ./path/to/msg (file or dir) ./txt/out/dir (optional)`
By default the exported files will be saved in `./text/JP`.

The exported format looks like this:
```
stringID	text
MsgLabels_city_common_msg_001	"はい"
MsgLabels_city_common_msg_002	"いいえ"
MsgLabels_city_common_msg_003	"どこに行きますか？
```
Note that the values are tab separated (.tsv) which allows you to paste directly into Google Sheets (one piece of text in each cell), 
if you prefer a different separator open the script with a text editor and change `txtFileSeparator`.

## txtToMsg.py
This script will take a .txt file in the format exported by `msgToTxt.py` and convert it back to a .msg file
`txtToMsg ./path/to/txt (file or dir) ./msg/out/dir (optional)`
by default the output files are saved in `./text/translated`.

## fm2089Utils.py
This is a script used by unpackRepack.bat to see if the rom we are using has the correct checksum
