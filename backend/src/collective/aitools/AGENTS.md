# AGENTS.md — collective.aitools package source

Notes for the add-on source itself. Read [`../../../AGENTS.md`](../../../AGENTS.md)
(backend) and the repo root `AGENTS.md` first. **Update this file whenever you
add or change code under `src/collective/aitools/`** — that is the maintenance
rule from the backend guide, applied here.

## The AI tools framework

The product's features are **AI tools**: each is a named utility providing
[`IAITool`](interfaces.py), enabled/configured from the "AI Tools" control
panel, and reaching a model through the `collective.aisettings` `IAIService`
utility (never an LLM SDK directly). When no model is configured the tool
passes `model=None` so aisettings resolves one by capability.

> Don't confuse our `collective.aitools.interfaces.IAITool` (a high-level
> editor/visitor feature) with `collective.aisettings`'s `IAITool` (a
> pydantic-ai function-calling tool offered to an agent mid-run). Different
> concept, same short name, different package.

### Anatomy of a tool

```
tools/
├── base.py            ← AITool base class + get_tool / get_tools / get_tools_settings
├── recognize_image.py ← RecognizeImageTool (vision → IAIService.analyze_image)
├── help_me_write.py   ← HelpMeWriteTool (completion → IAIService.chat)
├── summarize.py       ← SummarizeTool (completion → IAIService.chat)
├── suggest_tags.py    ← SuggestTagsTool (completion, vocabulary-aware)
├── assistant.py       ← AssistantTool (agentic chat: IAIService.tool_call loop) — see below
└── configure.zcml     ← one <utility provides=IAITool name=...> per tool
```

Most tools do a single model call. **`assistant`** is different: it runs a
tool-calling *loop* and dispatches to **capabilities** (`capabilities/`) — see
the "The Assistant (agentic chat) + capabilities" section below.

`AITool` (in [`tools/base.py`](tools/base.py)) reads the registry via the
`<name>_enabled` / `<name>_model` convention, exposes `is_enabled()`,
`get_model()`, `available_for(context)`, and `self.service` (the
`IAIService` utility). Subclasses set `name` / `title` / `description` and
implement `run(context, **kwargs)`. The public `run` should early-return via
`self._skip_if_disabled()`.

How tools are *invoked* (event subscriber, action/menu item, async cron) is
deliberately undecided — tools only expose `run`.

### Adding a new tool — checklist

1. Create `tools/<name>.py` with a subclass of `AITool` (set `name` to match
   the utility name; implement `run`).
2. Register it in [`tools/configure.zcml`](tools/configure.zcml) as a
   `<utility ... provides="collective.aitools.interfaces.IAITool"
   name="<name>" />`.
3. Add `<name>_enabled` (Bool) and, if it uses a model, `<name>_model`
   (TextLine) to [`IAIToolsSettings`](interfaces.py) — plus any extra config
   fields the tool needs (e.g. `recognize_image_prompt`).
4. The control panel ([`controlpanels/ai_tools.py`](controlpanels/ai_tools.py))
   renders the new fields automatically (it's bound to the whole schema). No
   change needed there.
5. The registry records are created by `<records interface=...IAIToolsSettings />`
   in [`profiles/default/registry/main.xml`](profiles/default/registry/main.xml) —
   already wired, but **bump the profile version in
   `profiles/default/metadata.xml` and add an upgrade step under `upgrades/`**
   so existing sites get the new records.
6. Add tests under `backend/tests/tools/` (registration, enable/disable,
   model resolution, and a `run` test with the `fake_service` fixture pattern).
7. Update this file.

## The Assistant (agentic chat) + capabilities

The `assistant` tool ([`tools/assistant.py`](tools/assistant.py)) is a chat
assistant for authenticated users. Unlike the other tools it is **agentic**: it
hands the model a set of *capabilities* (function/tool-calling schemas), runs
whichever the model asks for, feeds the results back, and repeats until the
model produces a final answer (capped at `MAX_STEPS`). It reaches the model
through `IAIService.tool_call(messages, tools, …)` — the OpenAI-style
tool-calling surface — never an SDK directly.

### Capabilities

A **capability** is the assistant's equivalent of a tool, but exposed *to the
model* as a callable function. Each is a named utility providing
[`IAIAssistantCapability`](interfaces.py), under `capabilities/`:

```
capabilities/
├── base.py          ← AICapability base + get_capability / get_capabilities / manifest_for
├── search_site.py   ← search_site   (permission View; read-only catalog search)
├── where_to_add.py  ← where_to_add  (permission "Modify portal content"; suggest folders)
├── propose_draft.py ← propose_draft (permission "Modify portal content"; AI-drafts, proposes only)
├── types.py         ← resolve_portal_type + IContentTypeSynonyms extension point
└── configure.zcml   ← one <utility provides=IAIAssistantCapability name=...> per capability
```

`AICapability` ([`capabilities/base.py`](capabilities/base.py)) sets `name`,
`description` (sent to the model), `parameters` (a JSON Schema for the call
args), and `permission` — a Zope permission **title** (`"View"`, `"Modify
portal content"`; import the constants from `Products.CMFCore.permissions`),
*not* the dotted ZCML id used in `configure.zcml`: `checkPermission` does not
know ids and silently treats an unknown name as Manager-only. It exposes
`allowed_for(context)` (a real `checkPermission`), `tool_schema()` (the
OpenAI function definition),
and `run(context, request, **kwargs)` returning a JSON-serializable result.

### Security model — read this before adding a capability

- **The manifest is a filter; `run` is the enforcement.** `manifest_for(context)`
  only offers the model the capabilities the current user is allowed to use, but
  `AssistantTool._run_capability` **re-checks `allowed_for` before every call**
  and returns an error payload (not a raise) if it fails. A hallucinated or
  malicious tool call can never do something the user can't.
- **No writes inside the loop.** A capability that would change content must
  only *propose* it. `propose_draft` validates + generates but creates nothing;
  the proposal bubbles up (`result["proposal"]`) to the widget as a confirm
  card. The actual write happens in a separate, explicit, permission-gated
  endpoint (`@aitools-assistant-apply`) that **re-validates server-side** — the
  client's proposal is untrusted, so tampering can't escalate.

### Content-type synonyms (extensible)

`resolve_portal_type(value)` ([`capabilities/types.py`](capabilities/types.py))
lets the model/editor use loose type names. Precedence: exact id →
case-insensitive id → type title → synonyms; it only ever returns a type that
exists on the site. Synonyms come from the built-in `TYPE_SYNONYMS` **plus**
every registered [`IContentTypeSynonyms`](interfaces.py) utility, merged by
`collect_synonyms()` (add-on entries override built-ins on conflict).
Add-ons that ship content types register their own provider (subclass
`SynonymProvider`, set `synonyms`, register a `<utility>`) to teach the
assistant friendly names — no change to this package.

### Adding a new capability — checklist

1. Create `capabilities/<name>.py` subclassing `AICapability`; set `name`,
   `description`, `parameters` (JSON Schema), `permission`; implement `run`.
2. Register it in [`capabilities/configure.zcml`](capabilities/configure.zcml)
   as `<utility ... provides="collective.aitools.interfaces.IAIAssistantCapability"
   name="<name>" />`.
3. Read-only? Safe to run in the loop. Does it write? Return a `proposal`
   instead and add a handler to `AssistantApply` (`services/assistant.py`) that
   re-validates and performs the write.
4. Add tests; update this file.

### REST endpoints

- `@aitools-assistant` (POST, permission `zope2.View`) — drives the `assistant`
  tool over the client's `{messages}` history; returns `{reply, steps,
  proposals}`. History is sanitized/clamped server-side; the system prompt and
  tool turns are added by the tool, never taken from the client.
- `@aitools-assistant-apply` (POST, permission `cmf.ModifyPortalContent`) —
  applies a user-confirmed `{proposal}`. Implements `create_draft` (re-validates
  via `propose_draft.validate_draft`, creates a private draft, sets the body
  only on types that have a `text` RichText field). Add more proposal types
  here.

> The chat endpoint is gated at `View` (so the authenticated members the viewlet
> targets can chat; capabilities self-gate). Anonymous rate-limiting is **not**
> done yet — see [What's deferred](#whats-deferred).

### Classic-UI chat widget

A floating chat widget, separate from the edit-form tools:

- **Viewlet** ([`browser/assistant.py`](browser/assistant.py)) — renders the
  trigger in `IPortalFooter` when the tool is enabled and the user is
  **authenticated** (`not api.user.is_anonymous()` — deliberately *not* a
  permission check, since the viewlet runs on the root where editor perms may be
  absent). Emits config incl. both endpoints, translated labels, and a
  `plone.protect` CSRF `token` (`createToken()`).
- **Pattern** ([`resources/js/assistant.pattern.js`](../../../resources/js/assistant.pattern.js))
  — a launcher + toggleable panel with chat bubbles, proposal confirm cards, and
  a "Start new chat" (↻) button. The transcript and open/closed state persist in
  **sessionStorage**, so navigating (a full reload) keeps the conversation and
  re-opens the widget. Assistant replies render through the safe Markdown helper
  [`resources/js/lib/markdown.js`](../../../resources/js/lib/markdown.js)
  (HTML-escaped first, then links/emphasis; link hrefs scheme-checked).
- **CSRF** — writes (the apply request) require the token; the pattern sends it
  via the `X-CSRF-TOKEN` header (`postJSON`'s `extraHeaders` arg). `postJSON`
  lives in [`lib/ui.js`](../../../resources/js/lib/ui.js).

## The AI Tools control panel

[`controlpanels/ai_tools.py`](controlpanels/ai_tools.py) mirrors the
`collective.aisettings` "AI Settings" panel exactly: a `RegistryEditForm`
(`IAIToolsSettings`) wrapped with `layout.wrap_form` for classic Plone, plus a
`RegistryConfigletPanel` adapter named `ai-tools` for the Volto REST surface
(`@controlpanels/ai-tools`). The Volto widget itself is not built yet — that's
the deferred frontend work.

## Classic-UI edit-form integration (editor tools)

Editor-facing UI is built as **Patternslib patterns** bundled with webpack (the
same setup other ESP packages use, e.g. `collective.alerts`). Each tool is a
REST endpoint + a viewlet that emits a Patternslib *trigger element* + a pattern
in the bundle. There are four edit-form tools:

| Tool | Endpoint | Button fills |
| --- | --- | --- |
| Help me write | `@aitools-help-me-write` | TinyMCE body (draft / rewrite) |
| Get image details | `@aitools-recognize-image` | Title / Description / Tags from an image |
| Summarize | `@aitools-summarize` | Description from the body text |
| Suggest tags | `@aitools-suggest-tags` | Tags from the body text (vocabulary-aware) |

- **REST endpoints** — `services/*.py`, all `for="*"`, permission
  `cmf.ModifyPortalContent`; each just drives its tool and returns `{result}` /
  `{error}`. Model choice / prompts / the enabled gate stay server-side. The
  text tools take the current form text in the body (`{text}`) since the content
  may be unsaved; recognize-image takes the chosen `{image}` data-URI.
- **Viewlets** — `browser/*.py` render (in `IPortalFooter`, only on edit/add
  forms and only when the tool is enabled) a hidden `<div class="pat-aitools-…">`
  whose `data-pat-aitools-…` attribute carries the JSON config (endpoint,
  translated labels, …). No script/CSS is injected by the viewlet — the bundle
  is loaded globally by the resource registry.
- **Patterns** (bundle source under [`resources/`](../../../resources), *not*
  `browser/static`): `help-me-write.pattern.js` hooks the global `window.tinymce`
  registry; `recognize-image.pattern.js` attaches a button per image file field;
  `summarize.pattern.js` / `suggest-tags.pattern.js` are built from the shared
  `lib/content-tool.js` factory (read body text via `lib/fields.getBodyText` →
  POST → fill one empty field). Shared field/widget logic (locating widgets,
  fill-if-empty, the select2 tags API) lives in `lib/fields.js`; the button+status
  UI in `lib/ui.js`. All tools fill target fields **only when empty**. SCSS is
  imported by the patterns.

### Shared backend helpers

- `tools/text.py` — `get_body_text(context)` (title + description + every
  RichText field, HTML-stripped, capped) and `clean_tags()` (trim / de-dupe /
  clamp), reused by the tools and the CLI scripts.
- `backfill.py` — `setup_admin` / `resolve_site` / `run_backfill(site,
  process_item, …)`: the catalog-walk + tally + periodic-commit loop behind every
  `scripts/*.py` backfill (recognize-images, summarize-content, suggest-tags).

### Building the bundle

Source is ES6 in `backend/resources/`; webpack (via `@patternslib/dev`) compiles
it to `browser/static/aitools-remote.min.js` (module-federation remote entry).
That output **is committed** and ships in the wheel.

```sh
make install-npm       # npm install (first time)
make build-resources   # npm run build  → browser/static/aitools-*.min.js
make watch-resources   # rebuild on change
make check-resources   # CI: build + fail if the committed bundle is stale
```

Wiring: `resources/index.js` → `resources/aitools-config.js` imports the
patterns and calls `registry.init()`. The bundle is registered as
`plone.bundles/aitools` in
[`profiles/default/registry/resources.xml`](profiles/default/registry/resources.xml)
pointing at `++plone++collective.aitools/aitools-remote.min.js`; the
`++plone++collective.aitools` static directory is declared with `<plone:static>`
in [`browser/configure.zcml`](browser/configure.zcml).

When you add another edit-form tool, follow the same endpoint + viewlet-trigger
+ pattern trio. The TinyMCE selection/replacement helpers and the field-fill
helpers in the patterns are the reusable parts.

Registry records use **no prefix** (keyed
`collective.aitools.interfaces.IAIToolsSettings.<field>`), matching aisettings.

## collective.aisettings coupling

- [`dependencies.zcml`](dependencies.zcml) `<include>`s `collective.aisettings`
  so its `IAIService` utility is registered (it also auto-includes in a real
  site via `plone.autoinclude`; the explicit include is what makes it load in
  the test layer).
- [`profiles/default/metadata.xml`](profiles/default/metadata.xml) depends on
  `profile-collective.aisettings:default` so installing this add-on installs
  aisettings too.
- Both this package's and aisettings' `setuphandlers/initial.py` import
  `plone.exportimport` (Plone 6.1 core, for example-content import). The dev
  venv must have it; if a fresh `make install` lacks it, install
  `plone.exportimport` (matching aisettings' pin, 2.0.1).

## What's deferred

- **Embeddings tool** — intentionally not implemented yet (vector
  storage/proximity-search backend undecided; `collective.vectorsearch`
  exists but computes embeddings locally via FastEmbed rather than through
  aisettings). Once available, `search_site` should rank semantically.
- **Volto counterparts** of these tools, the assistant widget, and the
  control-panel widget.
- **Assistant hardening** — anonymous access + rate-limiting/abuse controls for
  the chat endpoint (today it's authenticated-only by viewlet, `View` by
  endpoint); streaming replies; more `apply` proposal types beyond
  `create_draft`; showing `steps` in the widget.

## Tests

`backend/tests/tools/test_tools.py` and
`backend/tests/controlpanels/test_ai_tools.py`. The `fake_service` fixture
swaps the global `IAIService` for a recorder so `run` can be asserted without
a network/model. Run with `make test` from `backend/`.
