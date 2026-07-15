/*
 * "Summarize" — fills the empty Description field from the item's body text.
 * Config is read from `data-pat-aitools-summarize` on the viewlet's trigger.
 */
import makeContentToolPattern from "./lib/content-tool";
import { setTextField } from "./lib/fields";

export default makeContentToolPattern({
    name: "aitools-summarize",
    trigger: ".pat-aitools-summarize",
    targetSuffix: "description",
    applyResult: function (field, result) {
        return setTextField(field, (result || "").trim());
    },
});
