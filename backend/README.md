# collective.aitools

This package provides tools powered by AI, both for editors as for anonymous visitors

## Features

All features are individually enabled and configured (model, prompt) from the
**AI Tools** control panel, and reach a model through
[`collective.aisettings`](https://github.com/collective/collective.aisettings)
(configure your provider/models in **AI Settings**).

**Editor tools** (buttons on the classic-UI add/edit forms; fill a field only
when it's empty):

- **Summarize** — generate a Description / summary from the item's body text
  (also usable as the SEO meta description).
- **Suggest tags** — propose `Subject` keywords from the body text, reusing tags
  already in use on the site where possible.
- **Get image details** — title, description (alt text) and tags for an item's
  image, using a vision model.
- **Help me write** — drafting and rewriting assistance (start a draft, grammar
  check, change tone).

**Assistant** — a floating chat widget for authenticated users. It's *agentic*:
it can call capabilities to ground its answers and guide editors, rather than
guessing. Built-in capabilities:

- **Search the site** — full-text search (respects each user's permissions).
- **Where to add** — suggest folders where a given content type can be created.
- **Propose a draft** — from a rough brief, generate a draft (title, summary,
  body) for the editor to confirm and then adjust. Content is only created after
  an explicit confirmation, and always re-validated server-side.

Loose content-type names ("page", "news", "article", …) are accepted, and
add-ons can contribute their own synonyms by registering an
`IContentTypeSynonyms` utility.

## Installation

Install collective.aitools with uv.

```shell
uv add collective.aitools
```

Create the Plone site.

```shell
make create-site
```

## Contribute

- [Issue tracker](https://github.com/collective/collective-ai-tools/issues)
- [Source code](https://github.com/collective/collective-ai-tools/)

### Prerequisites ✅

-   An [operating system](https://6.docs.plone.org/install/create-project-cookieplone.html#prerequisites-for-installation) that runs all the requirements mentioned.
-   [uv](https://6.docs.plone.org/install/create-project-cookieplone.html#uv)
-   [Make](https://6.docs.plone.org/install/create-project-cookieplone.html#make)
-   [Git](https://6.docs.plone.org/install/create-project-cookieplone.html#git)
-   [Docker](https://docs.docker.com/get-started/get-docker/) (optional)

### Installation 🔧

1.  Clone this repository.

    ```shell
    git clone git@github.com:collective/collective-ai-tools.git
    cd collective-ai-tools/backend
    ```

2.  Install this code base.

    ```shell
    make install
    ```


### Add features using `plonecli` or `bobtemplates.plone`

This package provides markers as strings (`<!-- extra stuff goes here -->`) that are compatible with [`plonecli`](https://github.com/plone/plonecli) and [`bobtemplates.plone`](https://github.com/plone/bobtemplates.plone).
These markers act as hooks to add all kinds of features through subtemplates, including behaviors, control panels, upgrade steps, or other subtemplates from `bobtemplates.plone`.
`plonecli` is a command line client for `bobtemplates.plone`, adding autocompletion and other features.

To add a feature as a subtemplate to your package, use the following command pattern.

```shell
make add <template_name>
```

For example, you can add a content type to your package with the following command.

```shell
make add content_type
```

You can add a behavior with the following command.

```shell
make add behavior
```

```{seealso}
You can check the list of available subtemplates in the [`bobtemplates.plone` `README.md` file](https://github.com/plone/bobtemplates.plone/?tab=readme-ov-file#provided-subtemplates).
See also the documentation of [Mockup and Patternslib](https://6.docs.plone.org/classic-ui/mockup.html) for how to build the UI toolkit for Classic UI.
```

## License

The project is licensed under GPLv2.

## Credits and acknowledgements 🙏

Generated using [Cookieplone (2.0.0b3)](https://github.com/plone/cookieplone) and [cookieplone-templates (4aa42c6)](https://github.com/plone/cookieplone-templates/commit/4aa42c6d2055aff6560685382fb319a1c9594a63) on 2026-06-29 18:13:58.341660. A special thanks to all contributors and supporters!
