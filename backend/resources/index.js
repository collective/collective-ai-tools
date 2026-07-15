// Bundle entry point: load this bundle's actual entry point asynchronously so
// webpack module federation can wire up shared dependencies first.
import("./aitools-config.js");
