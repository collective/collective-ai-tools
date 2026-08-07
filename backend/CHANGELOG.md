# Changelog

<!--
   You should *NOT* be adding new change log entries to this file.
   You should create a file in the news directory instead.
   For helpful instructions, please see:
   https://github.com/plone/plone.releaser/blob/master/ADD-A-NEWS-ITEM.rst
-->

<!-- towncrier release notes start -->

## 1.3.2 (2026-08-07)


### Bug fixes:

- Stop Mosaic's edit-mode dimming from fading out the Assistant button, and bring the "Help me write" bar
  back on every rich-text tile each time it is selected, not just on the first one. @frapell 

## 1.3.1 (2026-08-05)


### Bug fixes:

- Stop "Help me write" from emptying the inline elements a selection spans: grammar check now corrects
  the selection's text nodes one by one, while the tone rewrites exchange HTML and may restructure. @frapell 

## 1.3.0 (2026-08-03)


### Bug fixes:

- Do not fail an Assistant capability call with a `TypeError` when the model wraps its arguments (e.g. under `parameters`), invents extra ones, or double-encodes the JSON. @frapell 
- Log a warning when a capability declares a permission Zope does not know, instead of quietly denying it to everyone but Managers. @frapell 
- Offer the Assistant's capabilities to non-Manager users again: they declared ZCML permission ids (`zope2.View`) instead of permission titles (`View`), which `checkPermission` silently treats as Manager-only. @frapell 

## 1.2.0 (2026-07-31)


### Bug fixes:

- Preserve the virtual-hosting state when the Assistant rebuilds its request on the background thread, so links it returns use the public host instead of the internal proxy hostname and the Plone site id. @frapell 

## 1.1.2 (2026-07-21)


### Bug fixes:

- Put the AI helping button next to the action buttons in mosaic. @frapell 

## 1.1.1 (2026-07-21)


### Bug fixes:

- Change the position of the help me write button for inline TinyMCE to avoid conflicts with the toolbar. @frapell 

## 1.1.0 (2026-07-21)


### New features:

- Add the help me write and identify image on mosaic tiles when available. @frapell 
- Run the chat Assistant asynchronously: the endpoint starts a background task and returns a task id, and the widget keeps showing "Thinking…" while polling every 2 seconds until the answer is ready. @frapell 
- When the Assistant proposes creating an Event, derive the event's start/end from the brief — both explicit dates ("on July 21st 2026") and relative ones ("in 2 weeks", anchored to the current date) — and set them on the created event. @frapell 

## 1.0.0 (2026-07-15)


### New features:

- "Recognize image" now returns structured metadata — a title, a description and
  5–10 tags — as JSON. A new "Get image details" button on Classic UI edit/add
  forms sends the chosen image to the ``@aitools-recognize-image`` REST endpoint
  and fills in the Title, Description and Tags fields that are still empty. A
  ``scripts/recognize_images.py`` CLI script (``make recognize-images``) backfills
  those fields across every image on the site, with an optional ``--path`` to
  limit it to a subtree. @frapell 
- Add an "AI Tools" control panel and a tools framework (named ``IAITool``
  utilities), with two initial Classic UI tools: "Recognize image" (vision)
  and "Help me write" (drafting/rewriting). "Help me write" adds a button to
  TinyMCE rich-text fields on edit/add forms, backed by the
  ``@aitools-help-me-write`` REST endpoint. Tools reach a model through
  ``collective.aisettings``. @frapell 
- Add an agentic chat "Assistant" for authenticated users. It runs a tool-calling
  loop (via ``collective.aisettings``' ``IAIService.tool_call``) over a set of
  *capabilities* — named ``IAIAssistantCapability`` utilities — that ground its
  answers: "Search the site", "Where to add" (suggest folders for a content type)
  and "Propose a draft" (generate a draft from a rough brief for the editor to
  confirm). Capabilities are permission-gated per user, and any content creation
  only happens after an explicit confirmation, re-validated server-side by the
  ``@aitools-assistant`` / ``@aitools-assistant-apply`` endpoints. Ships a
  Classic UI floating chat widget (Markdown rendering, session persistence,
  "start new chat"). Loose content-type names are accepted and add-ons can
  contribute more via an ``IContentTypeSynonyms`` utility. @frapell 
- Add two editor tools: "Summarize" fills an item's Description from its body
  text (also usable as the SEO meta description), and "Suggest tags" proposes
  Subject keywords from the body text, reusing tags already in use on the site.
  Both offer a Classic UI edit-form button (``@aitools-summarize`` /
  ``@aitools-suggest-tags`` endpoints) and a CLI backfill script
  (``make summarize-content`` / ``make suggest-tags``, with an optional
  ``--path``). @frapell 


### Internal:

- Refactor the Classic UI JavaScript into ES6 Patternslib modules under
  ``backend/resources/``, built with webpack (``@patternslib/dev``) into a single
  ``aitools`` bundle registered through the Plone resource registry — replacing
  the hand-minified ``browser/static`` assets and the ``rjsmin``/``rcssmin`` step.
  Build with ``make build-resources``. @frapell
