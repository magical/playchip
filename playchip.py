"""playchip - play chip's challenge levels


"""

import struct
import os
import subprocess
import shutil
import glob

PROGRAM_FOLDER = "%APPDATA%/Andrew Ekstedt/Playchip/"

CHIPS_FOLDER = "bin"
SCORE_FOLDER = "scores"

DEFAULT_DAT = "CHIPS.DAT"
DEFAULT_INI = "./chip.ini"

DAT_LENGTH = len("CHIPS.DAT")
INI_LENGTH = len("entpack.ini")
HEADING_LENGTH = len("Chip's Challenge")

CHIPS_EXE_SIZE = 267776

INI_OFFSET = 0x4A68
HEADING_OFFSET = 0x4A74
DAT_OFFSET = 0x4AD4

# http://www.muppetlabs.com/~breadbox/pub/software/tworld/chipend
# * The number of the first ending level is stored as a two-byte word
#   (little-endian) at offsets 0x91B9 and 0xBB14.
# * The number of the final ending level is stored as a two-byte word
#   (little-endian) at offsets 0x91C0, 0xBA14, and 0xBB1C.
# * To suppress the decade messages, change the byte at offset 0xBB2A
#   from 0xD2 to 0xD1.

ENDLEVEL_OFFSETS = [0x91c0, 0xba14, 0xbb1c]
FAKEENDLEVEL_OFFSETS = [0x91b9, 0xbb14]

CREDITSLEVEL_OFFSETS = [
    0x9f85, #don't ignore passwords if current level is this level
    0xa6d9, #don't ignore passwords when jumping to this level
]

DECADE_OFFSET = 0xbb2b
DECADE_VALUES = ('\xd1', '\xd2') # off, on

SOUND_OFFSET = 0x2f2f

class DocStrMixin(object):
    def __str__(self):
        return self.__doc__

class StringTooLongError(ValueError):
    """The string provided is too long to be used."""

class InvalidExe(Exception):
    """The exe provided is not Chip's Challenge."""

    def __str__(self): return self.__doc__

class NotALevelset(Exception):
    """The dat file is not a Chip's Challenge levelset."""

    def __str__(self): return self.__doc__


def appdata(*path):
    return os.path.join(os.path.expandvars(PROGRAM_FOLDER), *path)


def writestring(file, value, offset):
    """write a null-terminated string to the given offest.
    the file's position will change after calling this function."""
    file.seek(offset)
    file.write(value)
    file.write("\0")

def writeword(file, value, offset):
    """write a signed little-endian word to the file at the given offest.
    the file's position will change after calling this function."""
    value = struct.pack("<h", value)

    file.seek(offset)
    file.write(value)


def patchdecade(file, enable=False):
    file.seek(DECADE_OFFSET)
    byte = file.read(1)
    assert byte in DECADE_VALUES
    file.seek(DECADE_OFFSET)
    if enable:
        file.write(DECADE_VALUES[1])
    else:
        file.write(DECADE_VALUES[0])

def patchexe(exepath,
             datfile=None,
             inifile=None,
             iniheading=None,
             endlevel=None,
             fakeendlevel=None,
             creditslevel=None,
             decade=None,
             soundon=None):
    if fakeendlevel is None:
        fakeendlevel = endlevel
    if creditslevel is None:
        creditslevel = fakeendlevel

    if datfile is not None and not len(datfile) <= DAT_LENGTH:
        raise StringTooLongError(datfile)

    if inifile is not None and not len(inifile) <= INI_LENGTH:
        raise StringTooLongError(inifile)

    if iniheading is not None and not len(iniheading) <= HEADING_LENGTH:
        raise StringTooLongError(iniheading)

    if not 1 <= endlevel <= 999:
        raise ValueError(endlevel)

    if not 0 <= fakeendlevel <= endlevel <= 999:
        raise ValueError(fakeendlevel)
    if not (creditslevel == 0 or 1 <= fakeendlevel <= creditslevel <= endlevel <= 999):
        raise ValueError(creditslevel)

    with open(exepath, "r+b") as exe:
        if datfile is not None:
            writestring(exe, datfile, DAT_OFFSET)
        if inifile is not None:
            writestring(exe, inifile, INI_OFFSET)
        if iniheading is not None:
            writestring(exe, iniheading, HEADING_OFFSET)
        if endlevel is not None:
            for offset in ENDLEVEL_OFFSETS:
                writeword(exe, endlevel, offset)
        if fakeendlevel is not None:
            for offset in FAKEENDLEVEL_OFFSETS:
                writeword(exe, fakeendlevel, offset)
        if creditslevel is not None:
            for offset in CREDITSLEVEL_OFFSETS:
                writeword(exe, creditslevel, offset)
                if creditslevel > 0:
                    exe.write("\x7c") # jl
                else:
                    exe.write("\x75") # jnz
        if decade is not None:
            patchdecade(exe, decade)
        if soundon is not None:
            exe.seek(SOUND_OFFSET)
            exe.write('\x01' if soundon else '\x00')

def readstring(file, offset, maxlen):
    file.seek(offset)
    s = []
    while len(s) < maxlen:
        c = file.read(1)
        if not c or c == '\0':
            break
        s.append(c)
    return ''.join(s)

def readword(file, offset, signed=True):
    """read a signed or unsigned little-endian word from the file at the given offset"""
    file.seek(offset)
    return struct.unpack("<h" if signed else "<H", file.read(2))[0]

def readdecade(file):
    file.seek(DECADE_OFFSET)
    c = file.read(1)
    print repr(c)
    return c == DECADE_VALUES[1]

def readexe(exepath):
    info = {}
    with open(exepath, "rb") as exe:
        info['datfile'] = readstring(exe, DAT_OFFSET, DAT_LENGTH)
        info['inifile'] = readstring(exe, INI_OFFSET, INI_LENGTH)
        info['iniheading'] = readstring(exe, HEADING_OFFSET, HEADING_LENGTH)
        info['endlevel'] = [readword(exe, offset) for offset in ENDLEVEL_OFFSETS]
        info['fakeendlevel'] = [readword(exe, offset) for offset in FAKEENDLEVEL_OFFSETS]
        info['creditslevel'] = [readword(exe, offset) for offset in CREDITSLEVEL_OFFSETS]
        info['decade'] = readdecade(exe)
    return info

def checkexe(exepath):
    size = os.stat(exepath).st_size
    if size < CHIPS_EXE_SIZE:
        raise InvalidExe

class LevelsetInfo:
    CHIPSSIG = '\xac\xaa'

    def __init__(self, path):
        with open(path, "rb") as f:
            self.sig = f.read(2)
            self.version = f.read(2)
            self.checksig()
            self.count = struct.unpack("<H", f.read(2))[0]

    def checksig(self):
        if self.sig != self.CHIPSSIG:
            raise NotALevelset

    def __len__(self):
        return self.count

def playchip(levelset):
    info = LevelsetInfo(levelset)

    path, setname = os.path.split(levelset)
    exe = appdata(CHIPS_FOLDER, "chips.exe")

    shutil.copy(levelset, appdata(CHIPS_FOLDER, DEFAULT_DAT))

    endlevel = info.count
    fake = None
    credits = 0
    if endlevel == 149:
        fake = 144
    if setname.upper() == 'CHIPS.DAT':
        credits = 145

    
    patchexe(exe,
             inifile=DEFAULT_INI,
             iniheading=setname[:HEADING_LENGTH],
             endlevel=endlevel,
             fakeendlevel=fake,
             creditslevel=credits,
             decade=False,
             soundon=True
             )

    os.chdir(appdata(CHIPS_FOLDER))
    ret = subprocess.call(exe)

    return 0

def initialize(path):
    """initialize playchip given the path to a directory where the Chip's Challenge executable is located. this function may change the current directory"""
    installdir = appdata(CHIPS_FOLDER)
    
    if not os.path.exists(installdir):
        os.makedirs(installdir)

    exe = ""
    if os.path.isfile(path):
        path, exe = os.path.split(path)
    if not exe:
        exe = "CHIPS.EXE"

    checkexe(os.path.join(path, exe))

    os.chdir(path)
    
    shutil.copy(exe, os.path.join(installdir, 'chips.exe'))

    files = ['WEP4UTIL.DLL'] + glob.glob('*.WAV')
    #files += glob.glob('*.MID')
    for fn in files:
        print fn
        shutil.copy(fn, installdir)

def main(args=None):
    if args is None:
        import sys
        args = sys.argv[1:]

    if not args:
        raise Exception("not enough arguments")
    if args[0] == '-init':
        initialize(args[1])
        return 0
    elif args[0] == '-dump':
        if len(args) == 1:
            exefile = appdata(CHIPS_FOLDER, "chips.exe")
        else:
            exefile = args[1] 
        checkexe(exefile)
        from pprint import pprint
        pprint(readexe(exefile))
        return 0
    elif len(args) == 1:
        return playchip(args[0])
    else:
        raise Exception('Too many arguments')

    return 0
if __name__ == '__main__':
    import sys
    sys.exit(main(sys.argv[1:]))
