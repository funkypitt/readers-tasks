# Reader's Tasks

A black-and-white, text-only desktop client for CalDAV task lists: Tasks.org Cloud,
Nextcloud, Radicale, or any server that stores VTODO. The desktop twin of the tasks tile
in [Reader's Launcher](https://github.com/funkypitt/readers-launcher).

One window. Your lists on the left, the open tasks of the chosen list on the right, a box
to tick, a line at the bottom to add. White on black or black on white. Nothing else.

## Install

Debian, Ubuntu, Pop!_OS:

```
sudo apt install ./readers-tasks_1.1.0_all.deb
```

Arch, Manjaro:

```
git clone https://github.com/funkypitt/readers-tasks
cd readers-tasks/packaging && makepkg -si
```

Anywhere else: `python3 readers_tasks.py` with PyQt5 and requests installed.

## Tasks.org Cloud

In the Android app: ⚙ › App settings › Tasks.org › *Generate new password*. Copy the URL,
username and app password shown there into the first-run dialog (Ctrl+, later). The
password is stored in `~/.config/readers-tasks/config.json`, readable by you only.

## Keys

| Key | Effect |
|---|---|
| Enter in the bottom line | add the task to the current list |
| click ☐ | complete |
| right click on a task | complete · delete |
| Ctrl+T | flip white on black / black on white |
| Ctrl+= / Ctrl+- | larger / smaller text |
| F5 or Ctrl+R | sync now (also every 5 minutes) |
| Ctrl+N | jump to the new-task line |
| Ctrl+D or the "show n done" line | show / hide completed tasks; click ☑ (or right click → reopen) to untick one |
| right click on a list | move up · move down · hide this list · show a hidden list |
| Ctrl+, or the ⚙ in the status line | server settings |
| Ctrl+Q | quit |

Completed tasks are hidden by default; the "show n done" line under the list brings them
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

## Build the .deb

```
packaging/build-deb.sh
```

Single file, PyQt5 + requests, no CalDAV library: discovery, listing, adding and completing
are four HTTP requests. MIT.
