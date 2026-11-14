"""The macOS build's Info.plist completed after PyInstaller and before the signature: the version
(PyInstaller writes 0.0.0) and the oldest macOS the bundle can start on. That one is read from the
bundle itself: the highest `minos` of its Mach-O files (Python, Qt, the wheels), so an older Mac
is told by the Finder instead of seeing the app vanish at its first start. Apple silicon and Intel
may differ. The app opens no documents: no document types.
usage: python packaging/macos-info.py "dist/Readers Tasks.app" 1.8.1"""
import os
import plistlib
import re
import subprocess
import sys

MACHO = (b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe", b"\xca\xfe\xba\xbe")   # 64, 32 bits, universal


def minimum_macos(app):
    found = []
    for root, dirs, files in os.walk(app):
        for name in files:
            path = os.path.join(root, name)
            if os.path.islink(path):
                continue
            try:
                with open(path, "rb") as f:
                    if f.read(4) not in MACHO:
                        continue
            except OSError:
                continue
            out = subprocess.run(["otool", "-l", path], capture_output=True, text=True).stdout
            # LC_BUILD_VERSION gives "minos 11.0", the older LC_VERSION_MIN_MACOSX "version 10.13"
            for cmd in out.split("Load command")[1:]:
                m = (re.search(r"cmd LC_BUILD_VERSION.*?\n\s*platform 1\n\s*minos (\S+)", cmd, re.S)
                     or re.search(r"cmd LC_VERSION_MIN_MACOSX.*?\n\s*version (\S+)", cmd, re.S))
                if m:
                    found.append((tuple(int(x) for x in m.group(1).split(".")), path))
    if not found:
        return None, None
    best = max(found)
    return ".".join(str(x) for x in best[0]), best[1]


app, version = sys.argv[1], sys.argv[2]
path = app + "/Contents/Info.plist"
with open(path, "rb") as f:
    info = plistlib.load(f)
info["CFBundleShortVersionString"] = version
info["CFBundleVersion"] = version
minos, why = minimum_macos(app)
if minos:
    info["LSMinimumSystemVersion"] = minos
with open(path, "wb") as f:
    plistlib.dump(info, f)
print("Info.plist:", version, "· macOS", minos, "or later, set by", os.path.relpath(why, app) if why else "nothing")
