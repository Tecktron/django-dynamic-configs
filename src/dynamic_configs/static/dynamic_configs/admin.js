// Optional helpers for the dynamic-configs admin. Every page works without this script; it only fills in defaults
// and saves clicks.
"use strict";
{
    // The add page's first step: move on as soon as a type is chosen.
    function setUpTypeChoice(select) {
        select.addEventListener("change", () => {
            if (select.value) {
                select.form.requestSubmit();
            }
        });
    }

    document.addEventListener("DOMContentLoaded", () => {
        for (const select of document.querySelectorAll("select[data-dynamic-configs-type]")) {
            setUpTypeChoice(select);
        }
    });
}
