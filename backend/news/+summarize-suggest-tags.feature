Add two editor tools: "Summarize" fills an item's Description from its body
text (also usable as the SEO meta description), and "Suggest tags" proposes
Subject keywords from the body text, reusing tags already in use on the site.
Both offer a Classic UI edit-form button (``@aitools-summarize`` /
``@aitools-suggest-tags`` endpoints) and a CLI backfill script
(``make summarize-content`` / ``make suggest-tags``, with an optional
``--path``). @frapell
