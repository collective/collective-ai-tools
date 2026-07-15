# AGENTS.md

Top-level guide for AI agents working in this repository. It describes
what the product is, where its pieces live, and how the backend and
frontend halves connect. Before editing inside `backend/` or
`frontend/`, read the deeper `AGENTS.md` next to the code you're about
to touch.

## What this repo is

`collective.aitools` is a Plone 6 add-on that provides tools powered by
AI — for both editors (classic Plone UI and Volto) and anonymous site
visitors. It is a monorepo scaffolded with
[Cookieplone](https://github.com/plone/cookieplone-templates/), split
into two installable packages:

- **`collective.aitools`** — Python (Plone backend, classic UI + REST).
  Source under `backend/src/collective/aitools/`.
- **`volto-collective-aitools`** — TypeScript/React Volto add-on.
  Source under `frontend/packages/volto-collective-aitools/src/`.

> **Status:** this is an early-stage scaffold. The package structure,
> ZCML wiring, profiles, and test harness are in place, but most feature
> subpackages are still empty stubs. When you add the first real feature,
> you are also setting the conventions — keep both halves and their
> `AGENTS.md` files in sync as you go.

## The hard dependency: `collective.aisettings`

This product does **not** talk to LLMs directly. It has a fixed
dependency on [`collective.aisettings`](https://github.com/collective/collective-ai-settings),
which owns all model configuration and the LLM connection layer. That
add-on is declared in [`backend/pyproject.toml`](backend/pyproject.toml)
(`dependencies`) and checked out locally via `mxdev` into
`backend/sources/collective.aisettings/` (see [`backend/mx.ini`](backend/mx.ini)).

When you need to call a model, go through `collective.aisettings`:

- In Python, look up its `IAIService` utility (`chat` / `think` /
  `analyze_image` / `embed`) rather than calling an LLM SDK.
- From the frontend, call its REST endpoints (`POST /++api++/@ai`,
  `GET /++api++/@ai-task/<id>`, etc.).

The contracts (registry JSON shape, capability tokens, REST body
shapes) are documented in `backend/sources/collective.aisettings/AGENTS.md`
and its `backend/`/`frontend/` guides. Read those before wiring an AI
call. **Do not edit anything under `backend/sources/`** — it is a
read-only checkout of a separate project managed by mxdev, not part of
this repo.

## Repository layout

```
collective-ai-tools/
├── README.md                  ← user-facing intro + quickstart
├── AGENTS.md                  ← (this file)
├── Makefile                   ← orchestrates backend + frontend (delegates to each)
├── docker-compose.yml         ← local Traefik + Postgres + images stack
├── backend/
│   ├── README.md              ← Plone add-on user docs
│   ├── AGENTS.md              ← agent guide for the Plone add-on  ← READ before editing backend
│   ├── mx.ini                 ← mxdev sources (pulls collective.aisettings)
│   ├── sources/               ← mxdev checkouts (READ-ONLY, not part of this repo)
│   └── src/collective/aitools/   ← add-on source (see backend/AGENTS.md)
├── frontend/
│   ├── README.md              ← Volto add-on user docs
│   ├── AGENTS.md              ← agent guide for the Volto add-on  ← READ before editing frontend
│   ├── core/                  ← vendored Volto core via mrs-developer (READ-ONLY)
│   └── packages/volto-collective-aitools/   ← add-on source (see frontend/AGENTS.md)
├── docs/                      ← Sphinx/MyST documentation scaffold
└── .github/workflows/         ← per-area CI (backend.yml, frontend.yml, …)
```

## How the two halves connect

The backend exposes data and behavior over Plone's REST API
(`plone.restapi`); the Volto add-on consumes it. Both halves are
independent installs designed to be used together: the classic Plone UI
works without Volto, and Volto talks to the REST API regardless of
whether the classic add-on UI is mounted.

There are no cross-language contracts of this product's own *yet* (no
custom content types, endpoints, or registry records have been added).
The only shared contract today is the one inherited from
`collective.aisettings`. **When you add a feature that crosses the
language boundary** (a REST service the Volto add-on calls, a registry
record both UIs read, a vocabulary, a content type), document that
contract here and update both `AGENTS.md` files in the same change.

## Validation commands (whole repo)

The root `Makefile` fans out to `backend/` and `frontend/`. Run
`make help` for the full list.

```sh
make install            # install backend (uv) + frontend (pnpm), then create a site
make backend-create-site
make backend-start      # Plone backend on :8080
make frontend-start     # Volto frontend on :3000 (separate shell)

make check              # format + lint across both halves
make format
make lint
make test               # backend-test + frontend-test
make i18n               # update locales on both halves
```

Per-half validation (and the faster, targeted commands) live in the
respective `AGENTS.md`.

## Editing rules

- Read this file, then the `AGENTS.md` in whichever subtree you're
  editing, before touching code.
- Backend and frontend changes that share a contract must land
  together, in the same change, with both sides updated.
- Never edit `backend/sources/` (mxdev checkout of `collective.aisettings`
  and friends) or `frontend/core/` (vendored Volto core). Both are
  read-only dependencies.
- For anything AI/LLM-related, route through `collective.aisettings`
  rather than adding a direct LLM client or API key handling here.
- Keep the nested package `AGENTS.md` files current — see the
  maintenance rule in each half's guide.

## Where to look next

- Backend (Plone add-on, REST, profiles, content types) →
  [`backend/AGENTS.md`](backend/AGENTS.md).
- Frontend (Volto add-on, blocks, widgets, views) →
  [`frontend/AGENTS.md`](frontend/AGENTS.md).
- The LLM connection layer this product builds on →
  `backend/sources/collective.aisettings/AGENTS.md` (read-only).
- End-user / integrator questions → the matching `README.md` at each
  level.
