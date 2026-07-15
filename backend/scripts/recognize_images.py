"""Backfill title / description / tags for images across the site.

For each image-bearing item missing a title, description and/or tags, ask the
``recognize_image`` AI tool to generate them and fill in the empty fields only.

Run with zconsole from ``backend/``::

    make recognize-images                              # whole site
    make recognize-images ARGS="--path /Plone/news"    # a subtree only

or directly::

    bin/zconsole run instance/etc/zope.conf \\
        ./scripts/recognize_images.py --path /Plone/news --dry-run

Options: ``--path``, ``--site``, ``--commit-every``, ``--limit``, ``--dry-run``
(see ``parse_args``).
"""

from collective.aitools.backfill import resolve_site
from collective.aitools.backfill import run_backfill
from collective.aitools.backfill import setup_admin
from collective.aitools.tools import get_tool
from collective.aitools.tools.recognize_image import find_image
from Testing.makerequest import makerequest

import argparse
import os
import sys


def parse_args(argv):
    parser = argparse.ArgumentParser(
        prog="recognize_images",
        description="Backfill title/description/tags for site images via AI.",
    )
    parser.add_argument("--path", default="", help="Limit to this path (subtree).")
    parser.add_argument(
        "--site",
        default=os.getenv("PLONE_SITE_ID", "Plone"),
        help="Plone site id (default: $PLONE_SITE_ID or 'Plone').",
    )
    parser.add_argument("--commit-every", type=int, default=10, dest="commit_every")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true", dest="dry_run")
    return parser.parse_args(argv)


def _missing(obj):
    """Return ``(need_title, need_description, need_tags)`` booleans."""
    return (
        not (getattr(obj, "title", "") or "").strip(),
        not (getattr(obj, "description", "") or "").strip(),
        not tuple(getattr(obj, "subject", ()) or ()),
    )


def _apply(obj, details, needs, dry_run):
    """Fill the empty fields flagged in ``needs``; return changed-field labels."""
    need_title, need_description, need_tags = needs
    changes = []
    if need_title and details["title"]:
        changes.append("title")
        if not dry_run:
            obj.title = details["title"]
    if need_description and details["description"]:
        changes.append("description")
        if not dry_run:
            obj.description = details["description"]
    if need_tags and details["tags"]:
        changes.append(f"tags({len(details['tags'])})")
        if not dry_run:
            obj.subject = tuple(details["tags"])
    return changes


def make_process_item(tool, dry_run):
    def process_item(obj):
        field_name, _image = find_image(obj)
        if field_name is None:
            return None  # not an image-bearing item

        needs = _missing(obj)
        if not any(needs):
            return "skipped"

        url = obj.absolute_url()
        details = tool.run(obj)
        if not details:
            print(f"  - {url}: no result from AI service; skipped.")
            return "skipped"

        changes = _apply(obj, details, needs, dry_run)
        if not changes:
            return "skipped"

        prefix = "[dry-run] would update" if dry_run else "updated"
        print(f"  + {url}: {prefix} {', '.join(changes)}")
        if not dry_run:
            obj.reindexObject()
        return "updated"

    return process_item


def main(app, argv):
    args = parse_args(argv)
    app = makerequest(app)
    setup_admin(app)
    site = resolve_site(app, args.site)

    tool = get_tool("recognize_image")
    if tool is None or not tool.is_enabled():
        sys.exit(
            "The 'Recognize image' tool is not registered/enabled. Enable it in "
            "the 'AI Tools' control panel before running this script."
        )

    run_backfill(
        site,
        make_process_item(tool, args.dry_run),
        path=args.path,
        dry_run=args.dry_run,
        commit_every=args.commit_every,
        limit=args.limit,
    )


# zconsole runs this module with the Zope application root bound to ``app`` and
# the script's args in ``sys.argv[1:]``.
if "app" in globals():
    main(globals()["app"], sys.argv[1:])
