# AGENTS.md — backend

Agent guide for the `collective.aitools` Plone add-on (`backend/`). For
the cross-cutting picture of how this half relates to the Volto half
and to the `collective.aisettings` dependency, read
[`../AGENTS.md`](../AGENTS.md) first.

## Scope

Anything under `backend/src/collective/aitools/` plus the package
metadata (`pyproject.toml`, `instance.yaml`, `mx.ini`, profiles, ZCML).

The frontend Volto add-on (`frontend/packages/volto-collective-aitools/`)
is documented at [`../frontend/AGENTS.md`](../frontend/AGENTS.md). Don't
edit it from this side; coordinate cross-half changes via REST/registry
contracts and land both sides together.

**Do not edit `backend/sources/`** — it is an mxdev checkout of
`collective.aisettings` (and any other VCS sources from `mx.ini`),
read-only as far as this repo is concerned.

## The `collective.aisettings` dependency

This add-on connects to LLMs **only** through `collective.aisettings`.
It is a hard dependency (declared in [`pyproject.toml`](pyproject.toml)
`dependencies`) and pulled into the dev venv from a local checkout via
[`mx.ini`](mx.ini) (`url = collective.aisettings`,
`subdirectory = backend`). `mx.ini` also pins a few transitive
versions (`pydantic-ai-slim`, `pydantic`, `h11`, …) to keep
`collective.aisettings`' pydantic-ai stack compatible with Plone's
constraints — see the comments there before changing any pin.

To make an AI call from Python, get the `IAIService` utility from
`collective.aisettings` rather than calling an LLM SDK directly:

```python
from zope.component import getUtility
from collective.aisettings.interfaces import IAIService

service = getUtility(IAIService)
result = service.chat(prompt="…", context=context)
```

Capability resolution, the permission gate, and the registry JSON
schema all live in `collective.aisettings`. Its
`backend/sources/collective.aisettings/backend/AGENTS.md` is the
reference; don't reimplement model resolution or key handling here.

## Package layout

```
backend/src/collective/aitools/
├── __init__.py            ← __version__, PACKAGE_NAME, MessageFactory (_), logger
├── configure.zcml         ← package root: translations + includes subpackages
├── AGENTS.md              ← in-package guide: the AI tools framework + control panel  ← READ
├── dependencies.zcml      ← <include> plone.restapi + plone.volto + collective.aisettings
├── permissions.zcml       ← add/declare permissions here
├── profiles.zcml          ← GenericSetup profile registrations (default/uninstall/initial)
├── interfaces.py          ← IBrowserLayer + IAITool + IAIAssistantCapability + IContentTypeSynonyms + IAIToolsSettings
├── testing.py             ← PloneSandboxLayer + INTEGRATION/FUNCTIONAL/ACCEPTANCE layers
├── setuphandlers/         ← INonInstallable (hidden profiles) + post-install + example content
├── tools/                 ← the AI tools (named IAITool utilities) — see src AGENTS.md
├── capabilities/          ← assistant capabilities (named IAIAssistantCapability utilities) — see src AGENTS.md
├── controlpanels/         ← "AI Tools" control panel (RegistryEditForm + restapi adapter)
├── services/              ← plone.restapi services — @aitools-* endpoints (incl. @aitools-assistant)
├── browser/               ← viewlets (Patternslib triggers) + static/ (committed webpack bundle output)
├── content/               ← (empty stub) dexterity content types
├── indexers/              ← (empty stub) portal_catalog indexers
├── serializers/           ← plone.restapi serializers — summary.py adds listing metadata
├── vocabularies/          ← (empty stub) zope.schema vocabularies
├── upgrades/              ← (empty stub) GenericSetup upgrade steps
├── locales/               ← i18n (.pot/.po); __main__.py drives `make i18n`
└── profiles/
    ├── default/           ← install profile (registry, catalog, types, browserlayer, controlpanel)
    ├── initial/           ← initial metadata
    └── uninstall/         ← uninstall profile (hidden via setuphandlers)
```

The product's features are **AI tools** — named `IAITool` utilities under
`tools/`, enabled/configured from the "AI Tools" control panel
(`controlpanels/`), each calling the `collective.aisettings` `IAIService`. One
of them, `assistant`, is an **agentic chat** that dispatches to **capabilities**
(named `IAIAssistantCapability` utilities under `capabilities/`) via
`IAIService.tool_call`, with a classic-UI floating chat widget. The detailed
framework docs (anatomy of a tool, the assistant + capabilities, the add-a-tool
/ add-a-capability checklists, what's deferred) live in
[`src/collective/aitools/AGENTS.md`](src/collective/aitools/AGENTS.md) — read
that before adding or changing a tool.

`serializers/summary.py` is the other non-trivial piece: an
`IJSONSummarySerializerMetadata` utility that adds `image_field`,
`image_scales`, `effective`, and `Subject` to REST listing summaries. The
`content` / `indexers` / `vocabularies` / `upgrades` subpackages are still
empty `__init__.py` stubs wired into
[`configure.zcml`](src/collective/aitools/configure.zcml).

## How it's wired (ZCML cheat sheet)

- [`configure.zcml`](src/collective/aitools/configure.zcml) — registers
  `locales`, includes `Products.CMFCore` permissions, then
  `dependencies.zcml`, `profiles.zcml`, `permissions.zcml`, and the
  `.browser` / `.controlpanels` / `.indexers` / `.serializers` /
  `.services` / `.tools` / `.vocabularies` subpackages. **Add new
  subpackages to the include list here.** The `++plone++collective.aitools`
  static directory (`browser/static/`, the committed webpack bundle output) is
  registered with `<plone:static>` in `browser/configure.zcml`; the Classic UI
  source lives in `backend/resources/` (see the src AGENTS.md for the build).
- Auto-included into Plone via the `z3c.autoinclude.plugin` entry point
  (`target = "plone"`) in [`pyproject.toml`](pyproject.toml).
- [`dependencies.zcml`](src/collective/aitools/dependencies.zcml) —
  `plone.restapi` + `plone.volto` + `collective.aisettings`. Add backend
  dependency ZCML here.
- Profile metadata version is `1000`
  ([`profiles/default/metadata.xml`](src/collective/aitools/profiles/default/metadata.xml));
  it depends on `profile-plone.volto:default` and
  `profile-collective.aisettings:default`. The install test asserts this
  version, so when you add an upgrade step, bump the version here and add
  the step under `upgrades/`.
- `plone.exportimport` (Plone 6.1 core, used by `setuphandlers/initial.py`
  for example content) must be present in the venv — both this package and
  `collective.aisettings` import it at profile-registration time. If a
  fresh `make install` lacks it, install `plone.exportimport==2.0.1`.

## Conventions

- Imports: ruff isort config is `force-single-line`, `from-first`,
  `no-sections` (one import per line, `from x import y` style, no
  grouping). `make format` enforces it.
- Use the module-level `_ = MessageFactory("collective.aitools")` from
  `__init__.py` for translatable strings; i18n domain is
  `collective.aitools` everywhere (ZCML `i18n_domain`, locales).
- Use the package `logger` from `__init__.py` rather than ad-hoc
  logging.
- Python ≥ 3.11; line length 88; target Plone 6.1 / 6.2.

## Tests

Pytest via `pytest-plone`, configured in
[`pyproject.toml`](pyproject.toml) (`testpaths = ["tests"]`). Tests live
in [`tests/`](tests/) (sibling of `src/`, not inside the package):

- [`tests/conftest.py`](tests/conftest.py) builds fixtures from the
  three layers in
  [`testing.py`](src/collective/aitools/testing.py) via
  `pytest_plone.fixtures_factory` (`integration`, `functional`,
  `acceptance` fixtures).
- [`tests/setup/`](tests/setup/) covers install/uninstall (profile
  version, browserlayer registration, product (un)installed).
- [`tests/tools/`](tests/tools/) covers tool registration, enable/model
  resolution, and `run` (using a `fake_service` fixture that swaps the
  global `IAIService` for a recorder — no network/model needed).
- [`tests/controlpanels/`](tests/controlpanels/) covers the AI Tools
  control panel (registry records, classic page, restapi configlet).

Mirror the `tests/<area>/test_*.py` layout when you add a feature.
`tests/*` files relax some ruff rules (`E501`, `RUF001`, `S101`) so
asserts and long lines are fine in tests.

## Validation commands

```sh
# From backend/
make install            # uv venv + mxdev-resolved deps (pulls collective.aisettings) + instance config
make create-site        # create the Plone site with the addon profile
make start              # backend on :8080 (runwsgi)
make console            # zconsole debug shell into the instance

make format             # ruff (incl. import sort) + zpretty for XML/ZCML
make lint               # ruff check + pyroma + check-python-versions + zpretty --check
make test               # pytest
make test-coverage      # pytest --cov
make i18n               # rebuild .pot/.po (python -m collective.aitools.locales)
make install-npm        # npm install (Classic UI resources, first time)
make build-resources    # npm run build → browser/static/aitools-*.min.js (webpack)
make check-resources    # CI: build + fail if the committed bundle is stale
```

`make install` is required before tests (it creates `.venv` and
resolves dependencies through mxdev). Lint/format run via `uvx` and
don't need the venv.

## Editing rules

- **Keep this file and the in-package guide current.** When you add real
  code under `src/collective/aitools/` — a content type, REST service,
  control panel, vocabulary, indexer, upgrade step — update the layout
  and the relevant section above. If the package grows enough that a
  subtree needs its own detailed notes, create an `AGENTS.md` inside
  `src/collective/aitools/` (or the specific subpackage) and keep it in
  sync as that code changes. Treat a code change in those folders and
  its `AGENTS.md` update as one unit of work.
- Anything AI/LLM-related goes through `collective.aisettings`' public
  API (the `IAIService` utility / its REST endpoints). Don't add LLM
  SDK calls, API-key fields, or model-resolution logic here.
- When you add a subpackage with ZCML, include it from
  `configure.zcml`; when you add an upgrade, bump the profile version in
  `profiles/default/metadata.xml` and register the step under
  `upgrades/`.
- Don't edit `backend/sources/` or import private internals of
  `collective.aisettings`; depend on its documented interfaces.
- Changes sharing a contract with the Volto add-on (a REST service it
  calls, a registry record both UIs read) must land together with the
  frontend change — see [`../frontend/AGENTS.md`](../frontend/AGENTS.md).
