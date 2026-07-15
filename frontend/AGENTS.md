# AGENTS.md — frontend

Agent guide for the `volto-collective-aitools` Volto add-on
(`frontend/`). For the cross-cutting picture of how this half relates to
the Plone backend and the `collective.aisettings` dependency, read
[`../AGENTS.md`](../AGENTS.md) first.

## Scope

The Volto add-on lives in
`frontend/packages/volto-collective-aitools/`. Everything else under
`frontend/` is workspace scaffolding (pnpm workspace root,
`volto.config.js`, ESLint/Prettier/Stylelint config, Cypress harness,
Storybook config).

**Do not edit `frontend/core/`** — it is Volto core, vendored via
`mrs-developer` (pinned to the tag in
[`mrs.developer.json`](mrs.developer.json), currently Volto `19.1.4`).
It is checked out by `make install` and is read-only here.

## How the add-on is wired

This is a pnpm-workspace monorepo. The workspace root
[`package.json`](package.json) (`volto-collective-aitools-dev`) is not
published; it orchestrates Volto plus the add-on via pnpm filters.

- [`volto.config.js`](volto.config.js) lists `volto-collective-aitools`
  in `addons`, so Volto loads it. Scripts pass this file via the
  `VOLTOCONFIG` env var.
- The add-on entry point is
  [`packages/volto-collective-aitools/src/index.ts`](packages/volto-collective-aitools/src/index.ts):
  its default export `applyConfig(config)` is Volto's add-on hook. It
  delegates to
  [`src/config/settings.ts`](packages/volto-collective-aitools/src/config/settings.ts)
  (`installSettings`), which is currently a pass-through.

> **Status:** the add-on is a working scaffold but ships **no features
> yet** — `applyConfig`/`installSettings` return the config unchanged
> and `src/components/` is empty. When you add the first block, view,
> widget, or reducer, register it through this `applyConfig` →
> `installSettings` chain (or split `config/` into focused installers
> and call them from `installSettings`).

## Package layout

```
frontend/packages/volto-collective-aitools/
├── package.json           ← the published add-on (name: volto-collective-aitools)
├── src/
│   ├── index.ts           ← applyConfig entry point (Volto add-on hook)
│   ├── config/settings.ts ← installSettings(config) — wire config registrations here
│   └── components/        ← (empty stub) React components / blocks / views / widgets
├── locales/               ← i18n (volto.pot + per-language .po)
├── vitest.config.mjs      ← unit-test config (extends @plone/volto's)
├── tsconfig.json
└── towncrier.toml         ← changelog fragments (news/)
```

## Talking to the backend

The add-on consumes the Plone backend over `plone.restapi`. For AI
features specifically, the LLM endpoints are provided by
`collective.aisettings` (not by this product's backend) — e.g.
`POST /++api++/@ai` and `GET /++api++/@ai-task/<id>`. See
[`../AGENTS.md`](../AGENTS.md) and the `collective.aisettings` frontend
guide for the request/response shapes before wiring an AI call. Use
Volto's action/reducer + `@plone/registry` patterns; don't hardcode LLM
credentials or call providers directly from the browser.

## Conventions

- TypeScript + React 18 (peer dep). Match Volto add-on idioms.
- Lint/format is ESLint + Prettier + Stylelint, run with the
  `VOLTOCONFIG` env set (the Makefile targets handle this).
- Translatable strings go through `react-intl` and are extracted to
  `locales/` by `make i18n`. i18n domain artifacts are committed.
- Add a `news/` changelog fragment (towncrier) for user-facing changes.

## Validation commands

```sh
# From frontend/
make install            # mrs-developer checks out Volto core, pnpm i, build deps
make start              # Volto dev server on :3000 (needs a backend)
make build              # production bundle

make format             # eslint --fix + prettier --write + stylelint --fix
make lint               # eslint + prettier check + stylelint
make test               # vitest unit tests (pnpm --filter volto-collective-aitools)
make i18n               # extract/sync i18n messages

make backend-docker-start   # throwaway Plone backend in Docker for local dev
```

Acceptance tests use Cypress (`make acceptance-frontend-dev-start`,
`make acceptance-backend-start`, `make acceptance-test`); specs live in
[`cypress/tests/`](cypress/tests/).

`make install` must run first — it vendors Volto core into `core/` and
builds `@plone/registry` + `@plone/components`, which the add-on resolves
as workspace packages.

## Editing rules

- **Keep this file and the in-package guide current.** When you add real
  code under `packages/volto-collective-aitools/src/` — a block, view,
  widget, reducer, or config installer — update the layout and wiring
  sections above. If the add-on grows enough that the source tree needs
  its own detailed notes, create an `AGENTS.md` inside
  `packages/volto-collective-aitools/` (or the relevant subfolder) and
  keep it in sync as that code changes. Treat a code change in those
  folders and its `AGENTS.md` update as one unit of work.
- Register everything through the `applyConfig` → `installSettings`
  chain rather than mutating global config from import side effects.
- Don't edit `frontend/core/` (vendored Volto). To change the Volto
  version, update the tag in `mrs.developer.json` and re-run
  `make install`.
- For AI calls, use the `collective.aisettings` REST endpoints; don't
  embed API keys or call LLM providers from the frontend.
- Changes sharing a contract with the backend (a REST service this
  add-on calls, a registry record both UIs read) must land together with
  the backend change — see [`../backend/AGENTS.md`](../backend/AGENTS.md).
