#!/usr/bin/env python3
"""Copy the tasks of one CalDAV list into another, possibly on another server.

    python3 copy_tasks.py \
        --from https://caldav.tasks.org/ USER APP_PASSWORD "Inbox" \
        --to   https://sync.infomaniak.com AB12345 APP_PASSWORD "À faire" \
        [--include-completed] [--dry-run]

Tasks keep their UID, so running the script twice does not duplicate anything: a task
already present on the target is skipped. Nothing is deleted on the source."""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/usr/lib/readers-tasks")
from readers_tasks import CalDAV, CalDAVError, _unfold  # noqa: E402


def pick(client, name):
    lists = client.task_lists()
    for n, url in lists:
        if n.strip().lower() == name.strip().lower():
            return url
    raise SystemExit(f"list '{name}' not found; available: " + ", ".join(n for n, _ in lists))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from", dest="src", nargs=4, metavar=("URL", "USER", "PASSWORD", "LIST"), required=True)
    ap.add_argument("--to", dest="dst", nargs=4, metavar=("URL", "USER", "PASSWORD", "LIST"), required=True)
    ap.add_argument("--include-completed", action="store_true", help="also copy completed and cancelled tasks")
    ap.add_argument("--dry-run", action="store_true", help="only show what would be copied")
    a = ap.parse_args()

    src = CalDAV(a.src[0], a.src[1], a.src[2])
    dst = CalDAV(a.dst[0], a.dst[1], a.dst[2])
    src_url = pick(src, a.src[3])
    dst_url = pick(dst, a.dst[3])

    tasks = src.tasks(src_url)
    if not a.include_completed:
        tasks = [t for t in tasks if not t.completed and not t.cancelled]
    existing = {t.uid for t in dst.tasks(dst_url)}
    copied = skipped = 0
    for t in tasks:
        if t.uid in existing:
            skipped += 1
            continue
        print(("would copy: " if a.dry_run else "copy: ") + (t.summary or t.uid))
        if a.dry_run:
            continue
        url = dst_url.rstrip("/") + "/" + t.uid + ".ics"
        # The original VTODO, folded again to be safe; the same UID guards against duplicates.
        body = "\r\n".join(_unfold(t.ics)) + "\r\n"
        try:
            dst._req("PUT", url, body, headers={"Content-Type": "text/calendar; charset=utf-8", "If-None-Match": "*"})
            copied += 1
        except CalDAVError as e:
            print(f"  failed: {e}")
    print(f"{copied} copied, {skipped} already there, {len(tasks)} read from the source")


if __name__ == "__main__":
    main()
