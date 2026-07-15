"""Backfill the Description of content across the site from its body text.

For each item with body text but no description, ask the ``summarize`` AI tool
to generate one and fill it in (never overwrites an existing description).

Run with zconsole from ``backend/``::

    make summarize-content                              # whole site
    make summarize-content ARGS="--path /Plone/news"    # a subtree only

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
        prog="summarize_content",
        description="Backfill content descriptions from body text via AI.",
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
            return None  # no text content to summarize
        if (getattr(obj, "description", "") or "").strip():
            return "skipped"  # already has a description

        url = obj.absolute_url()
        summary = tool.run(obj, text=text)
        if not summary:
            print(f"  - {url}: no result from AI service; skipped.")
            return "skipped"

        prefix = "[dry-run] would set" if dry_run else "set"
        print(f"  + {url}: {prefix} description ({len(summary)} chars)")
        if not dry_run:
            obj.description = summary
            obj.reindexObject()
        return "updated"

    return process_item


def main(app, argv):
    args = parse_args(argv)
    app = makerequest(app)
    setup_admin(app)
    site = resolve_site(app, args.site)

    tool = get_tool("summarize")
    if tool is None or not tool.is_enabled():
        sys.exit(
            "The 'Summarize' tool is not registered/enabled. Enable it in the "
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
