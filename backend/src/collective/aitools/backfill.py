"""Shared catalog-walk helper for the CLI backfill scripts.

The ``scripts/*.py`` entry points (run via ``zconsole run``) bind the admin
user, resolve the Plone site and then hand a per-item callable to
:func:`run_backfill`, which walks the catalog subtree, tallies outcomes and
commits periodically. Keeping the walk here (rather than in each script) means
the scripts stay tiny and the logic is import-testable.
"""

from AccessControl.SecurityManagement import newSecurityManager

import transaction


def setup_admin(app):
    """Bind the Zope ``admin`` user as the acting user. Returns the user."""
    admin = app.acl_users.getUserById("admin")
    if admin is None:
        raise SystemExit("No 'admin' user found; cannot run.")
    newSecurityManager(None, admin.__of__(app.acl_users))
    return admin


def resolve_site(app, site_id):
    """Return the Plone site object, setting it as the active local site."""
    from zope.component.hooks import setSite

    site = app.get(site_id)
    if site is None:
        raise SystemExit(f"Plone site {site_id!r} not found under the app root.")
    setSite(site)
    return site


def resolve_path(site, path):
    """Turn a user-supplied ``--path`` into an absolute catalog path.

    Accepts an absolute path ("/Plone/news") or one relative to the site
    ("news"); an empty path means the whole site.
    """
    site_path = "/".join(site.getPhysicalPath())
    if not path:
        return site_path
    if not path.startswith("/"):
        path = "/" + path
    if path == site_path or path.startswith(site_path + "/"):
        return path
    return site_path + path


def run_backfill(
    site,
    process_item,
    *,
    path="",
    dry_run=False,
    commit_every=10,
    limit=0,
):
    """Walk the catalog subtree and apply ``process_item`` to each object.

    ``process_item(obj)`` must return one of ``"updated"``, ``"skipped"`` or
    ``"failed"`` and is responsible for its own field logic (it should not
    commit). Returns a tally dict with keys ``processed``, ``updated``,
    ``skipped`` and ``failed``.
    """
    catalog = site.portal_catalog
    target_path = resolve_path(site, path)
    print(f"Scanning {target_path!r} ...")

    tally = {"processed": 0, "updated": 0, "skipped": 0, "failed": 0}
    for brain in catalog(path={"query": target_path}):
        try:
            obj = brain.getObject()
        except Exception as exc:
            print(f"  ! {brain.getPath()}: could not load ({exc})")
            tally["failed"] += 1
            continue

        try:
            outcome = process_item(obj)
        except Exception as exc:
            print(f"  ! {obj.absolute_url()}: failed ({exc})")
            tally["failed"] += 1
            continue

        if outcome is None:
            continue  # not applicable to this item; don't count it

        tally["processed"] += 1
        tally[outcome] += 1
        due = commit_every and tally["updated"] % commit_every == 0
        if outcome == "updated" and not dry_run and due:
            transaction.commit()

        if limit and tally["processed"] >= limit:
            print(f"Reached --limit {limit}; stopping.")
            break

    if dry_run:
        transaction.abort()
    else:
        transaction.commit()

    print(
        "Done. processed={processed} updated={updated} "
        "skipped={skipped} failed={failed}".format(**tally)
        + (" (dry-run, nothing written)" if dry_run else "")
    )
    return tally
