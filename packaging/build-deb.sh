#!/bin/bash
# Builds readers-tasks_<version>_all.deb next to this script. Needs dpkg-deb and fakeroot.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"; SRC="$HERE/.."
VERSION=$(grep -oE '^VERSION = "[^"]+"' "$SRC/readers_tasks.py" | cut -d'"' -f2)
ROOT="$HERE/deb-root"; rm -rf "$ROOT"
install -Dm755 "$SRC/readers_tasks.py" "$ROOT/usr/lib/readers-tasks/readers_tasks.py"
install -Dm755 /dev/stdin "$ROOT/usr/bin/readers-tasks" <<'SH'
#!/bin/sh
exec python3 /usr/lib/readers-tasks/readers_tasks.py "$@"
SH
install -Dm644 "$HERE/readers-tasks.desktop" "$ROOT/usr/share/applications/readers-tasks.desktop"
install -Dm644 "$HERE/readers-tasks.svg" "$ROOT/usr/share/icons/hicolor/scalable/apps/readers-tasks.svg"
install -Dm644 "$SRC/LICENSE" "$ROOT/usr/share/doc/readers-tasks/copyright"
mkdir -p "$ROOT/DEBIAN"
cat > "$ROOT/DEBIAN/control" <<CTRL
Package: readers-tasks
Version: $VERSION
Section: utils
Priority: optional
Architecture: all
Depends: python3 (>= 3.8), python3-pyqt5, python3-requests
Maintainer: funkypitt <pierregallaz@gmail.com>
Homepage: https://github.com/funkypitt/readers-tasks
Description: Black-and-white, text-only CalDAV task list
 A single-window desktop client for CalDAV task lists (Tasks.org Cloud,
 Nextcloud, Radicale...). Lists on the left, open tasks on the right, a box
 to tick and a line to add. White on black or black on white.
CTRL
fakeroot dpkg-deb --build "$ROOT" "$HERE/readers-tasks_${VERSION}_all.deb"
rm -rf "$ROOT"
echo "built $HERE/readers-tasks_${VERSION}_all.deb"
