# Collective AI Tools (volto-collective-aitools)

This package provides tools powered by AI, both for editors as for anonymous visitors

[![npm](https://img.shields.io/npm/v/volto-collective-aitools)](https://www.npmjs.com/package/volto-collective-aitools)
[![](https://img.shields.io/badge/-Storybook-ff4785?logo=Storybook&logoColor=white&style=flat-square)](https://collective.github.io/volto-collective-aitools/)
[![CI](https://github.com/collective/collective-ai-tools/actions/workflows/main.yml/badge.svg)](https://github.com/collective/collective-ai-tools/actions/workflows/main.yml)


## Features

> **Not implemented yet.** The AI tools currently ship for **Classic UI only**
> (the `collective.aitools` backend). This Volto add-on is a scaffold with no
> features wired in. A work-in-progress implementation — a chat assistant plus
> edit-form tool widgets — lives on the `volto-wip` branch and will land in a
> later release.

## Installation

To install your project, you must choose the method appropriate to your version of Volto.


### Volto 18 and later

Add `volto-collective-aitools` to your `package.json`.

```json
"dependencies": {
    "volto-collective-aitools": "*"
}
```

Add `volto-collective-aitools` to your `volto.config.js`.

```javascript
const addons = ['volto-collective-aitools'];
```

If this package provides a Volto theme, and you want to activate it, then add the following to your `volto.config.js`.

```javascript
const theme = 'volto-collective-aitools';
```

### Volto 17 and earlier

Create a new Volto project.
You can skip this step if you already have one.

```
npm install -g yo @plone/generator-volto
yo @plone/volto my-volto-project --addon volto-collective-aitools
cd my-volto-project
```

Add `volto-collective-aitools` to your `package.json`.

```JSON
"addons": [
    "volto-collective-aitools"
],

"dependencies": {
    "volto-collective-aitools": "*"
}
```

Download and install the new add-on.

```
yarn install
```

Start Volto.

```
yarn start
```

## Test installation

Visit http://localhost:3000/ in a browser, login, and check the awesome new features.


## Development

The development of this add-on is done in isolation using pnpm workspaces, the latest `mrs-developer`, and other Volto core improvements.
For these reasons, it only works with pnpm and Volto 18.


### Prerequisites ✅

-   An [operating system](https://6.docs.plone.org/install/create-project-cookieplone.html#prerequisites-for-installation) that runs all the requirements mentioned.
-   [nvm](https://6.docs.plone.org/install/create-project-cookieplone.html#nvm)
-   [Node.js and pnpm](https://6.docs.plone.org/install/create-project.html#node-js) 24
-   [Make](https://6.docs.plone.org/install/create-project-cookieplone.html#make)
-   [Git](https://6.docs.plone.org/install/create-project-cookieplone.html#git)
-   [Docker](https://docs.docker.com/get-started/get-docker/) (optional)

### Installation 🔧

1.  Clone this repository, then change your working directory.

    ```shell
    git clone git@github.com:collective/collective-ai-tools.git
    cd collective-ai-tools/frontend
    ```

2.  Install this code base.

    ```shell
    make install
    ```


### Make convenience commands

Run `make help` to list the available Make commands.


### Set up development environment

Install package requirements.

```shell
make install
```

### Start developing

Start the backend.

```shell
make backend-docker-start
```

In a separate terminal session, start the frontend.

```shell
make start
```

### Lint code

Run ESlint, Prettier, and Stylelint in analyze mode.

```shell
make lint
```

### Format code

Run ESlint, Prettier, and Stylelint in fix mode.

```shell
make format
```

### i18n

Extract the i18n messages to locales.

```shell
make i18n
```

### Unit tests

Run unit tests.

```shell
make test
```

### Run Cypress tests

Run each of these steps in separate terminal sessions.

In the first session, start the frontend in development mode.

```shell
make acceptance-frontend-dev-start
```

In the second session, start the backend acceptance server.

```shell
make acceptance-backend-start
```

In the third session, start the Cypress interactive test runner.

```shell
make acceptance-test
```

## License

The project is licensed under the MIT license.
