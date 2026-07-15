"""Backfill Subject tags for content across the site from its body text.

For each item with body text but no tags, ask the ``suggest_tags`` AI tool
(vocabulary-aware) to propose tags and fill them in (never overwrites existing
tags).

Run with zconsole from ``backend/``::

    make suggest-tags                              # whole site
    make suggest-tags ARGS="--path /Plone/news"    # a subtree only

Options: ``--path``, ``--site``, ``--commit-every``, ``--limit``, ``--dry-run``.
"""

from collective.aitools.backfill import resolve_site
from collective.aitools.backfill import run_backfill
from collective.aitools.backfill import setup_admin
from collective.aitools.tools import get_tool
from collective.aitools.tools.text import get_body_text
from Testing.makerequest import makerequest

import argparse
import os
import sys


def parse_args(argv):
    parser = argparse.ArgumentParser(
        prog="suggest_tags",
        description="Backfill content tags from body text via AI.",
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


def make_process_item(tool, dry_run):
    def process_item(obj):
        text = get_body_text(obj)
        if not text:
            return None  # no text content to classify
        if tuple(getattr(obj, "subject", ()) or ()):
            return "skipped"  # already tagged

        url = obj.absolute_url()
        tags = tool.run(obj, text=text)
        if not tags:
            print(f"  - {url}: no result from AI service; skipped.")
            return "skipped"

        prefix = "[dry-run] would set" if dry_run else "set"
        print(f"  + {url}: {prefix} tags {tags}")
        if not dry_run:
            obj.subject = tuple(tags)
            obj.reindexObject()
        return "updated"

    return process_item


def main(app, argv):
    args = parse_args(argv)
    app = makerequest(app)
    setup_admin(app)
    site = resolve_site(app, args.site)

    tool = get_tool("suggest_tags")
    if tool is None or not tool.is_enabled():
        sys.exit(
            "The 'Suggest tags' tool is not registered/enabled. Enable it in the "
            "'AI Tools' control panel before running this script."
        )

    run_backfill(
        site,
        make_process_item(tool, args.dry_run),
        path=args.path,
        dry_run=args.dry_run,
        commit_every=args.commit_every,
        limit=args.limit,
    )


if "app" in globals():
    main(globals()["app"], sys.argv[1:])
