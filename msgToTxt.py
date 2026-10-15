import sys
from pathlib import Path
from collections import defaultdict

import conversionTables

'''
how to use:
msgToTxt ./path/to/msg (file or dir) ./txt/out/dir (optional)
'''

### TODO
### [] Allow this script to export to a different folder if the .msg is not JP
###    Right now it is hardcoded to export to ./text/JP
### [] Print a summary in the end with errors and results
###     Summary:
###         files exported = 10
###         ERROR: unkown character {EEBB33} in string MsgLabels_cool_015, replaced with �

# by default we are putting the .txt files in "./text/JP"
outDefaultPath = Path(__file__).parent # Folder where this script is located
outDefaultExportPath = Path(f"{outDefaultPath}/text/JP")
outPath = outDefaultExportPath

# Separator to use between stringID and string
txtFileSeparator = '\t'

# First line of a txt file exported by our tool
txtFileHeader = f'stringID{txtFileSeparator}text'

def main():

    # if we have two parameters then assume 2 is output location
    if len(sys.argv) > 2:
        outPath = sys.argv[2]

    pathToMsg = Path(sys.argv[1])
    retVal = convert(pathToMsg)
    
    sys.exit(retVal != 0)

def convert(msgFilePath):

    if msgFilePath.exists() == False:
        print("### ERROR:")
        print(f"### {msgFilePath} does not exist!")
        return -1

    msgFiles = [msgFilePath]
    if msgFilePath.is_dir():
        msgFiles = msgFilePath.glob("*.msg")

    convertedCounter = 0

    # Loop through all .msg files and convert to .txt 
    for msgFile in msgFiles:

        # Read .msg file in a blob
        msgFileName = msgFile.name
        msgBytes = msgFile.read_bytes()

        # print(f"Converting {msgFileName} to txt...")

        # Validate .msg header
        validHEader = isMsgHeaderValid(msgBytes[0x00:0x10])
        if validHEader == False:
            return -1

        # Read how many strings there are and the file size
        strCount = int.from_bytes(msgBytes[0x09:0x0c], byteorder='little')
        fileSize = int.from_bytes(msgBytes[0x0c:0x10], byteorder='little')
        # print(f"strCount {strCount} fileSize {fileSize}")

        # strings delimiters store a string position as an offset from the beginning of the file
        # !!! if header is 16 bytes then we can delete strDelimiters and just loop from 0x10 to 0x10+(strCount * 8)
        # !!! 0x10 is the end of the header and the stride of the string delimiters is 8 bytes
        strDelimiters = memoryview(msgBytes)[0x10:0x10+(strCount * 8)]
        
        # Create a .txt file to output to
        txt_file = outPath / msgFileName.replace(".msg", ".txt")
        txt_file.parent.mkdir(parents=True, exist_ok=True)
        outTxtFile = txt_file.open("w", encoding="utf-8")

        # Add a row on top of the file with the title for each column
        # Nice to have for spreadsheets
        outTxtFile.writelines(f'{txtFileHeader}\n')

        # String identifier format
        # we create an identifier for each string in the file for ease of use
        # format is msg_fileName_stringIndex (index is in the order the strings are laid out in the .msg file)
        # E.G. the identifier for string 17 in the file MsgLabels_common.msg would be 'MsgLabels_common_msg_017'
        stringUIDFormat = msgFileName.replace(".", "_")

        # Loop through all strings and write to out file
        for i in range(strCount):
            # Get the string start and end position in the file
            
            # strings delimiters are stored as a pair of 4 bytes
            offset = i * 8
            
            strStart = int.from_bytes(strDelimiters[offset:offset+4], byteorder='little')
            strEnd = int.from_bytes(strDelimiters[offset+4:offset+8], byteorder='little')
            str = msgBytes[strStart:strEnd]

            # Convert the binary string into a list of chars using the provided font table
            chars = StrFromBinary(msgBytes, strStart, strEnd)

            # Create a unique identifier for the string (filename_string)
            stringIndex = f'{stringUIDFormat}_{(i+1):03d}'

            # Write to the file
            outTxtFile.writelines(f'{stringIndex}{txtFileSeparator}"{"".join(chars)}"\n')

        convertedCounter += 1

        outTxtFile.close()
        # print(f'Conversion done, "{txt_file.name}" created')
        # print(f'str [{i}] chars "{"".join("�" if x is None else x for x in chars)}"')

    print(f"{convertedCounter} files converted")
    print("### All done!")

    return 0

def StrFromBinary(msgBytes, strStart, strEnd):
    """
    Loops through a given string using the Start and End pointers, 
    then looks up each hex value in the font table (default table is in conversionTables.py).

    Notes:
    The chars can be either 1 or 2 bytes, 
    if the first byte >= 0xC0 then it is a 2 bytes char
    strings all end with 0x0000
    if the string contains only a single 1 byte char, then the string ends with 0x00

    Parameters:
        msgBytes (bytes): binary blob from msg file
        strStart (int): start position of the string in the blob (relative to file start)
        strEnd   (int): end position of the string (relative to file start)

    Returns:
        list of chars
    """

    # Loop through the string, each char is either 1 or 2 bytes long
    outChars = []
    s = strStart
    while s < strEnd:
        
        bytesStride = 0 # byte size of the char we just read

        # if msgBytes[s] in {0x92, 0x9C, 0xBF}:
        #     bytesStride = 1
        if msgBytes[s] == 0xEE: # handle special hex codes first
            bytesStride = 3 if msgBytes[s+1] == 0xA3 else 4
        elif msgBytes[s] >= 0xC0: # check if it is a two bytes char
            bytesStride = 2 # skip reading next byte
        # single byte char
        else:
            bytesStride = 1
        
        # for 2 bytes chars we need to mask them to find them in the actual font file in the rom
        key = msgBytes[s:s+bytesStride]
        if bytesStride == 2:
            # Use bitmask to convert from .msg byte code to FONT byte code (set 7th and 14th to 0)
            maskedBytes = bytearray(msgBytes[s:s+2])
            maskedBytes[0] &= 0xBF #1011 1111
            maskedBytes[1] &= 0x7F #0111 1111
            key = bytes(maskedBytes)
        
        # grab char from table
        try:
            charFromTable = conversionTables.fullTable.get(key)
            outChars.append(f"{charFromTable}")
        except ValueError:
            print("### ERROR:")
            print(f"### Could not find char with code {key} in table")
            outChars.append("�")

        # move byte stream cursor
        s += bytesStride

        # !!!! Maybe early out at the top of the loop instead?
        # peek next two bytes and see if it is the end of string
        if msgBytes[s:s+2] == b'\x00\x00':
            break

    return outChars

def isMsgHeaderValid(msgHeader):

    # We assume that the header is always 16 bytes
    headerSize = len(msgHeader)
    if headerSize != 16:
        print("### ERROR:")
        print(f"### Unexpected file header size, expected 16 bytes, received {headerSize} instead")
        print(f"### {msgHeader.hex(' ')}")
        return False

    ### Read and validate .msg file header ###
    # NOTE header endcoding is the same for all .msg files
    # 00 00 00 00 | 54 45 58 54 02 | FF FF | 00 | FF FF 00 00
    # 00 00 00 00       (padding)
    # 54 45 58 54 02    (a 5 bytes string containing the constant 'TEXT', 02 might be a unix way to signal "start of data")
    # FF FF             (2 bytes containing the number of strings in the file)
    # 00                (padding)
    # FF FF 00 00       (4 bytes containg file byte size, maybe last 2 bytes might be padding?)
    TEXT = msgHeader[0x04:0x08].decode()
    if TEXT != 'TEXT':
        print("### ERROR:")
        print(f"### Malformed header, expected TEXT @ 0x04:0x08, found {TEXT} instead")
        return False

    return True

if __name__ == "__main__":
    main()