/*
 * "Suggest tags" — fills the empty Tags (subjects) widget from the item's body
 * text. Config is read from `data-pat-aitools-suggest-tags` on the trigger.
 */
import makeContentToolPattern from "./lib/content-tool";
import { setTags } from "./lib/fields";

export default makeContentToolPattern({
    name: "aitools-suggest-tags",
    trigger: ".pat-aitools-suggest-tags",
    targetSuffix: "subjects",
    applyResult: function (field, result) {
        return setTags(field, result || []);
    },
});
