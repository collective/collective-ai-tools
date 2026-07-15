"Recognize image" now returns structured metadata — a title, a description and
5–10 tags — as JSON. A new "Get image details" button on Classic UI edit/add
forms sends the chosen image to the ``@aitools-recognize-image`` REST endpoint
and fills in the Title, Description and Tags fields that are still empty. A
``scripts/recognize_images.py`` CLI script (``make recognize-images``) backfills
those fields across every image on the site, with an optional ``--path`` to
limit it to a subtree. @frapell
