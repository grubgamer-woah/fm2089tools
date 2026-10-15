import sys
from pathlib import Path
import hashlib

'''
IsRomValid() -> will check a .nds rom to see if it is a valid FM2089 rom
validateUnpack() -> check if the unpacked JP rom is valid
validateTxt() -> check if the JP .txt files from msgToTxt are good
'''

# hashes have been taken from:
# https://datomatic.no-intro.org/index.php?page=show_record&s=28&n=2330
# NOTE: we use string instead of bytes for readability
hash_CRC32 = int('03bafa3d', 16)
hash_MD5 =	'e965ed696171d327656dac3adf6c6221'
hash_SHA1 =	'2e89b8351f125025dcd148e2be4f6b2fc8a16f95'

# Hash of all files in an unpacked JP rom directory (assuming NitroPacker project name to be FM2089_JP_UNPACK)
hash_MD5_unpack = 'dc499003150ce0ae7ffa357719937043'
# Hash of .txt files expoprted from JP .msg via msgToTxt
hash_MD5_txt = '8a1e8864df501d398c3805bcc68c1145'

def validateRom(filePath):
    pathToRom = Path(filePath)
    # get rom's bytes and generate hashes
    rom = pathToRom.read_bytes()
    hashObj = hashlib.md5(rom)
    romHash = hashObj.hexdigest()
    sys.exit(romHash != hash_MD5)

def validateUnpack(directory):
    unpackedMD5 = md5_update_from_dir(directory, hashlib.md5()).hexdigest()
    sys.exit(unpackedMD5 != hash_MD5_unpack)

def validateTxt(directory):
    jpTxtMD5 = md5_update_from_dir(directory, hashlib.md5()).hexdigest()
    sys.exit(jpTxtMD5 != hash_MD5_txt)

def md5_update_from_dir(directory, hash):
    for path in sorted(Path(directory).iterdir(), key=lambda p: str(p).lower()):
        hash.update(path.name.encode())
        if path.is_file():
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(4096),b""):
                    hash.update(chunk)
        elif path.is_dir():
            hash = md5_update_from_dir(path, hash)
    return hash