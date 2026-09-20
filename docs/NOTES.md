# Reader's Tasks — notes

Reference material moved out of the README.

## Windows and macOS: first opening

**Windows** — take the `.exe` from the
[latest release](https://github.com/funkypitt/readers-tasks/releases/latest) and open it: one file,
nothing to install, no Python needed. The app is not signed by a paid certificate, so Windows
shows a blue "Windows protected your PC" panel the first time: *More info* › *Run anyway*.

**macOS** — take the `.dmg` for your Mac (`apple-silicon` for an M1 and later, `intel` for an
older one), open it and drag the app onto *Applications*. It is not signed by a paid Apple
certificate either, so the first opening must be a **right click on the app › Open** › *Open*; a
double click at that point says the app "cannot be opened" and offers nothing but the bin. Once
opened that way it starts normally ever after. If macOS still refuses, in a Terminal:
`xattr -dr com.apple.quarantine "/Applications/Readers Tasks.app"`.

## A new computer

The setup dialog (Ctrl+,) › *export credentials…* writes the accounts (server, username, app password) into a JSON file. Reader's
Calendar, Tasks and Notes can all write into the same file, each in its own section. On the new
computer, *import credentials…* at the same place brings them back — or, before the first
window, `readers-tasks --import-credentials readers-credentials.json` (and `--export-credentials FILE` the
other way). The look (colours, text size, font) stays out of it.

The file holds your passwords in clear and is written readable by you only: carry it on a USB key
or in your own cloud folder, not by e-mail, and delete it once imported.

## Tasks.org Cloud

In the Android app: ⚙ › App settings › Tasks.org › *Generate new password*. Copy the URL,
username and app password shown there into the first-run dialog (Ctrl+, later). The
password is stored in `~/.config/readers-tasks/config.json`, readable by you only.

## Keys

| Key | Effect |
|---|---|
| Enter in the bottom line | add the task to the current list |
| click ☐ | complete |
| double-click on a task | rename it |
| drag a task up or down | put the open tasks in your own order (saved on the server as X-APPLE-SORT-ORDER, so the phone shows the same order) |
| right click on a task | complete · rename · delete |
| Ctrl+T | flip white on black / black on white |
| Ctrl+= / Ctrl+- | larger / smaller text |
| F5 or Ctrl+R | sync now (also every 5 minutes) |
| Ctrl+N | jump to the new-task line |
| Ctrl+D or the "show n done" line | show / hide completed tasks; click ☑ (or right click → reopen) to untick one |
| right click on a list | move up · move down · hide this list · show a hidden list |
| Ctrl+, or the ⚙ in the status line | server settings |
| Ctrl+Q | quit |

Open tasks follow the order you give them by dragging; tasks never dragged come after,
by due date then creation. Completed tasks are hidden by default; the "show n done" line under the list brings them
back, dimmed, so a task ticked by mistake can be reopened. Lists you hide, and the order
you give them, are remembered in the config file. Tasks are ordered by due date, then by
creation, like the launcher tile.

## Moving lists between servers

`copy_tasks.py` copies the tasks of one list into another, on the same server or not —
for instance from Tasks.org Cloud to an Infomaniak or Nextcloud calendar:

```
python3 copy_tasks.py \
    --from https://caldav.tasks.org/ USER APP_PASSWORD "Inbox" \
    --to   https://sync.infomaniak.com AB12345 APP_PASSWORD "À faire" \
    --include-completed
```

Tasks keep their UID, so a second run skips what is already there; nothing is deleted on
the source. Add `--dry-run` to see the list first.

## Building

The .deb, on the machine itself:

```
packaging/build-deb.sh
```

The Windows and macOS binaries are built by GitHub, since neither can be built here:
`.github/workflows/desktop-builds.yml` runs PyInstaller on a Windows runner and on two macOS
runners at every `v*` tag and attaches the `.exe` and the two `.dmg` to the release of that tag.
*Actions* › *Windows and macOS builds* › *Run workflow* builds them without a tag, kept as
artifacts. The icons come from `packaging/readers-tasks.png` (`.ico` beside it, `.icns` built on the
runner).

Single file, PyQt5 + requests, no CalDAV library: discovery, listing, adding and completing
are four HTTP requests. MIT.
