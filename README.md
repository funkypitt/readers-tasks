# Reader's Tasks

A black-and-white, text-only desktop client for CalDAV task lists: Tasks.org Cloud, Nextcloud,
Radicale, or any server that stores VTODO. One window: your lists on the left, the open tasks on
the right, a box to tick, a line at the bottom to add. The desktop twin of the tasks tile in
[Reader's Launcher](https://github.com/funkypitt/readers-launcher). No account with the app, only
your own server.

## Key points

- Enter in the bottom line adds a task; click ☐ to complete; double-click to rename; right click to complete, rename or delete.
- Drag a task to put the open tasks in your own order. The order is saved on the server, so the phone shows the same. Tasks never dragged come after, by due date then creation.
- Completed tasks are hidden; Ctrl+D or the "show n done" line brings them back, dimmed, so one ticked by mistake can be reopened.
- Right click on a list: move up, move down, hide it, show a hidden one.
- Syncs every 5 minutes, and on F5 or Ctrl+R. Ctrl+T (or the last entry of the lists' right-click menu) moves to the next colour theme: black on white, then lavender, sage, nordic, terracotta, coquette, activist, sultry, nature, white on black, and round again (with a colour theme the lists, rows, menus and buttons are rounded cards; the two inks stay text on the page); Ctrl+= and Ctrl+- change the text size.
- Account: server, username and app password, asked at first run (Ctrl+, later, ⌘, on a Mac), kept in `~/.config/readers-tasks/config.json` (macOS: `~/Library/Application Support/readers-tasks/config.json`; Windows: `%APPDATA%\Readers Tasks\config.json`), readable by you only. Tasks.org Cloud shows them in its Android app: ⚙ › App settings › Tasks.org › *Generate new password*.
- A new computer: *export credentials…* in the setup dialog writes a JSON file that Reader's Calendar, Tasks and Notes share; *import credentials…* reads it back. It holds passwords in clear: delete it once imported.
- `copy_tasks.py` copies a list to another list or another server, without deleting anything on the source.
- English, French, German, Spanish, Portuguese and Russian, following the system language.
- 1.8.1, macOS: the app speaks the Mac's language (not its region's), shows ⌘, for the settings, and trusts the certificates the Keychain trusts; a server whose certificate is not trusted says so instead of "cannot reach the server".

More detail: [docs/NOTES.md](docs/NOTES.md).

## Install

- Debian, Ubuntu, Pop!_OS: add the [apt repository](https://funkypitt.github.io/apt-repo/), then `sudo apt install readers-tasks`. Or take the `.deb` from the [latest release](https://github.com/funkypitt/readers-tasks/releases/latest): `sudo apt install ./readers-tasks_*_all.deb`.
- Arch, Manjaro: `git clone https://github.com/funkypitt/readers-tasks && cd readers-tasks/packaging && makepkg -si`.
- Windows (`.exe`) and macOS (`.dmg`, `apple-silicon` or `intel`): from the latest release. They are unsigned: on Windows *More info* › *Run anyway*; on macOS, after the first refusal, System Settings › Privacy & Security › *Open Anyway* (macOS 15 and later; right click on the app › *Open* on macOS 14), or in a Terminal `xattr -dr com.apple.quarantine "/Applications/Readers Tasks.app"`.
- Anywhere else: `python3 readers_tasks.py` with PyQt5 and requests installed.

## Build

`packaging/build-deb.sh` builds the .deb. The Windows and macOS binaries are built by GitHub Actions
at every `v*` tag. Single file, PyQt5 + requests (+ truststore when present, for the system's certificates), no CalDAV library.

## Crédits / Credits

© 2026 Pierre Gallaz. Développé avec [Claude Code](https://claude.com/claude-code) (Anthropic).
Licence MIT, voir `LICENSE`.

© 2026 Pierre Gallaz. Developed with [Claude Code](https://claude.com/claude-code) (Anthropic).
MIT licence, see `LICENSE`.
