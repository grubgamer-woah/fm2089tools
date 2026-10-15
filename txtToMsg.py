import sys
from pathlib import Path
import re

from conversionTables import fullTable
from msgToTxt import txtFileSeparator

# This script takes a .txt file created from msgToTxt.py
# and turns it back into a .msg file
# NOTE: the expected format of the .txt is as follow:
#         string ID,             original text (titles for col 1 and 2)
# msglabels_fileName_msg_000, "string to convert"

tr_export = Path("./text/translated") # Location where we export the translated .msg to

writeToLog = True
debugLog = None

def main():

    if len(sys.argv) > 2:
        tr_export = sys.argv[2]

    tr_txt = Path(sys.argv[1])
    retVal = convert(tr_txt)
    
    sys.exit(retVal != 0)

def convert(txtFilePath):

    # Check if the file exist
    if txtFilePath.exists() == False:
        print(f"### Error: File not found")
        print(f"### {txtFilePath}")
        return -1

    txtFiles = [txtFilePath]

    if txtFilePath.is_dir():
        txtFiles = txtFilePath.glob("*.txt")

    convertedCounter = 0

    for txtFile in txtFiles:

        if writeToLog:
            logName = f"{txtFile.name.replace('.txt', '.log')}"
            logFilePath = Path(f'.temp/logs/txtToMsg_logs/{logName}')
            logFilePath.parent.mkdir(parents=True, exist_ok=True) 
            debugLog = logFilePath.open("w", encoding="utf-8")

        #print(f"Converting {txtFile.name}...")

        # Open the .txt file and read its contents
        txtFileRaw = txtFile.read_text(encoding='utf-8')
    
        ### Match all strings in the file ###
        # .txt files format is MsgLabels_name_000,"string"
        # Let's ignore the IDs and only grab the string between ""
        # read_text gives us the file as one string
        # so we match for pattern >> MsgLabels_name_000,"string"\nMsgLabels_name_000
        # "\nstringID will match till the end of the string
        # instead of when the next " is encountered
        # NOTE: the trailing "" are already ignored by the match pattern
        pattern = r'[Mm]sg[Ll]abels_.*?_\d+' + txtFileSeparator + '"(.*?)"(?=\s*[Mm]sg[Ll]abels_)*'
        txtLines = re.findall(pattern, txtFileRaw, re.DOTALL)
    
        # Let's store how many strings we have found
        strCount = len(txtLines)
        # print(f"strings found: {strCount}")

        # Error out if no strings were found
        if strCount == 0:
            debugString = f"### Error: no strings found in file\n### {txtFile}"
            print(debugString)
            if writeToLog:
                debugLog.write(debugString)
            continue # move to next file

        # split table so we can find hexCodes via char
        # NOTE: We can't reverse the dictionary in our case
        # because the font table has duplicate characters in it :(
        hexCodes = list(fullTable.keys()) # this contains hex values
        font = list(fullTable.values()) # this contains chars
    
        # Create .msg file to write to, file name is the same as the .txt one
        msg_file = tr_export / txtFile.name.replace('.txt', '.msg')
        msg_file.parent.mkdir(parents=True, exist_ok=True)
    
        # Open file for writing binary data and write an empty header to it
        msg_bin = msg_file.open('wb')

        # .msg file header        [      Padding     ]  [T    E    X    T    ? ]  [strCount] [00]  [    file size     ]
        msgFileHeader = bytearray([0x00,0x00,0x00,0x00, 0x54,0x45,0x58,0x54,0x02, 0xFF,0xFF, 0x00, 0xFF,0xFF,0x00,0x00])
        msg_bin.write(msgFileHeader)

        # Pre-allocate the offsets section of the file
        # NOTE: We know that each string has 4bytes for start and 4bytes for end
        # so we can already pre-allocate start and end offset of 4 bytes each
        msg_bin.write(b'\x00\x00\x00\x00\x00\x00\x00\x00' * strCount)
        offsetsBuffer = bytearray(strCount * 8)

        # The actual strings are stored at the bottom of the file, below the offsets section,
        # so let's store a pointer where the strings section starts
        curStrPtr = msg_bin.tell()

        # loop through each string and turn it into binary
        for l in range(0, len(txtLines)):

            string = txtLines[l]

            # Convert the string to bynary using the encoding from the font table
            byteString = StringToMsgHex(string, hexCodes, font, debugLog)
            # Debug stuff
            #print(f'#{l:03d}# {byteString.hex(" ")}')

            # Write str start and end to the offsets
            strBegin = curStrPtr.to_bytes(4, 'little')
            strEnd = (curStrPtr + len(byteString)-1).to_bytes(4, 'little')
            offset = l * 8
            offsetsBuffer[offset:(offset+4)] = strBegin
            offsetsBuffer[(offset+4):(offset+8)] = strEnd

            if writeToLog:
                debugLog.write(f"###{l}_START {strBegin.hex(' ')} ")
                debugLog.write(string.replace("\n","\\n") + '\n')
                debugLog.write(f"###{l}_END {strEnd.hex(' ')}\n\n")

            # Write the actual string
            msg_bin.write(byteString)
        
            # move file pointer to the next string start
            curStrPtr = msg_bin.tell()

        # done converting strings, let's add the offsets to the .msg file
        # and update the header info

        # Write strings count and total file size to the header
        fileSize = msg_bin.tell()
        msg_bin.seek(0x09)
        msg_bin.write(strCount.to_bytes(2, 'little'))
        msg_bin.seek(0x0C)
        msg_bin.write(fileSize.to_bytes(4,'little'))

        # Write offsets right below the header
        # TODO check if we got the buffer size wrong and are overwriting string data
        msg_bin.seek(0x10)
        msg_bin.write(offsetsBuffer)

        convertedCounter += 1
        #print(f'Conversion done, "{msg_file.name}" created')

        if debugLog:
            debugLog.close()

    print(f"{convertedCounter} files converted")
    print("### All done!")

    return 0


def StringToMsgHex(string, byteCodes, font, debugLog):
    
    debugString = ''
    retVal = bytearray()

    for c in range(0, len(string)):
        
        char = string[c]

        # let's check if we hit a special code (E.G «9C23») 
        # NOTE Line break is set to \n in the font, so we do not catch it here
        if char == '«':
            parsed = ParseSpecialCode(string[c:], debugString)
            if parsed is not None:
                i = font.index(parsed.group(0))
                debugString += char + f" {parsed.group(0)}\n"
                retVal += byteCodes[i]
                c += parsed.end() # jump to closing '»'
                continue
        try:
            # Find char index in the font and use the index to find the hex value
            i = font.index(char)
            byteChar = byteCodes[i]
            retVal += byteChar

            # NOTE there are duplicate chars in the font table
            # so when we look for them we stop at the first one we find
            # if you have debugLog enabled the log will show all the bytecodes of each character
            # TODO we should probably turn the font table into a dict with char as key 
            # and an array of byte codes as value
            debugChar = '\\n' if char == '\n' else char
            debugString += debugChar + f" {byteChar.hex(' ')}"
            indices = [x for x, y in enumerate(font) if y == char]
            for z in range(1,len(indices)):
                debugString += f" || {byteCodes[indices[z]].hex(' ')}"
            
            # 2 bytes chars need to be un-masked
            if len(byteChar) == 2:
                
                maskedChar = bytearray(byteChar)
                maskedChar[0] = byteChar[0] | 0x40
                maskedChar[1] = byteChar[1] | 0x80
                
                retVal[-1] |= 0x80 #1000 0000
                retVal[-2] |= 0x40 #0100 0000

                debugString += f" > {maskedChar.hex(' ')}"
            debugString += "\n"
        except ValueError:
            debugString += f' {char}(NONE)'

    # Add padding at the end of the string 
    # single char str have only one byte padding
    if len(retVal) == 1:
        retVal += b'\x00'
    else:
        retVal += b'\x00\x00'

    if debugLog:
        debugLog.write(debugString)        
    # print(debugString)
    
    return retVal


def ParseSpecialCode(string, debugString):
    # Handles converting special codes {000000} to hex
     
    # try to match a bunch of characters betwen «»
    # pattern = r'\{[^}]+\}'
    pattern = r'(«[^»]+»)?'
    match = re.search(pattern, string)

    # no match :(
    if match is None:
        debugString += f"{pattern} not found in {string}"
        print(f"### ERROR:") 
        print(f"### {debugString}")

    return match



if __name__ == "__main__":
    main()
