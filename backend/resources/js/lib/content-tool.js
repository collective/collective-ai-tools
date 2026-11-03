/*
 * Factory for the "read the body text → call an endpoint → fill one empty
 * field" edit-form tools (Summarize, Suggest tags). Each is a Patternslib
 * pattern whose trigger element (rendered by the viewlet) carries the config;
 * the button is attached next to the target field on the edit/add form.
 */
import Base from "@patternslib/patternslib/src/core/base";
import { findField, getBodyText } from "./fields";
import { createBar, runTask } from "./ui";

// `applyResult(field, result)` writes the model result into `field` and returns
// true when it actually filled it (i.e. the field was empty).
export default function makeContentToolPattern({ name, trigger, targetSuffix, applyResult }) {
    // The scan is global; only attach once even with several trigger elements.
    let started = false;

    function setup(CONFIG) {
        const L = CONFIG.labels || {};
        const field = findField(document, targetSuffix);
        if (!field) {
            return; // target field not on this form; nothing to do
        }
        const form = field.closest("form") || document;
        const wrapper = field.closest(".field") || field.parentNode;
        if (!wrapper) {
            return;
        }

        function onClick() {
            const text = getBodyText(form);
            if (!text) {
                ui.setStatus("error", L.noText || "Add some content first.");
                return;
            }
            ui.setBusy(true);
            ui.setStatus("loading", L.loading || "Working...");
            runTask({
                endpoint: CONFIG.endpoint,
                statusEndpoint: CONFIG.statusEndpoint,
                payload: { text: text },
                fallbackError: L.error,
                syncFallback: true,
            })
                .then(function (data) {
                    const filled = applyResult(field, data && data.result);
                    ui.setBusy(false);
                    if (filled) {
                        ui.setStatus("success", L.done || "Done.");
                    } else {
                        ui.setStatus("error", L.notEmpty || "Field already has a value.");
                    }
                })
                .catch(function (err) {
                    ui.setBusy(false);
                    ui.setStatus("error", (err && err.message) || L.error);
                });
        }

        const ui = createBar(L.button || name, onClick);
        wrapper.appendChild(ui.bar);
    }

    return Base.extend({
        name: name,
        trigger: trigger,
        parser: "mockup",
        defaults: {
            endpoint: "",
            statusEndpoint: "",
            labels: {},
        },
        init: function () {
            if (started) {
                return;
            }
            started = true;
            setup(this.options);
        },
    });
}
