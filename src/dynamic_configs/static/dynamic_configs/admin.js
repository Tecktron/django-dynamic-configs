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

    // The UTC offset, in seconds, that a time zone has right now.
    function utcOffset(zone) {
        const now = new Date(Math.floor(Date.now() / 1000) * 1000);
        const format = new Intl.DateTimeFormat("en-US", {
            timeZone: zone,
            hourCycle: "h23",
            year: "numeric",
            month: "numeric",
            day: "numeric",
            hour: "numeric",
            minute: "numeric",
            second: "numeric",
        });
        const parts = {};
        for (const part of format.formatToParts(now)) {
            parts[part.type] = Number(part.value);
        }
        const wallClock = Date.UTC(parts.year, parts.month - 1, parts.day, parts.hour, parts.minute, parts.second);
        return (wallClock - now.getTime()) / 1000;
    }

    // Django's date and time pickers take Today and Now from the page's server offset, read on every click, so point
    // it at the chosen zone. (A config's page has one value, so one zone.)
    function followZone(select) {
        document.body.dataset.adminUtcOffset = String(utcOffset(select.value));
    }

    // A zoned datetime: start an empty value on the browser's zone, then keep the pickers in the chosen zone. A value
    // that's already shown keeps its zone, since changing the zone alone would change the instant.
    function setUpZoneChoice(select) {
        const base = select.name.slice(0, -"_2".length);
        const empty = [`${base}_0`, `${base}_1`].every((name) => !select.form.elements[name]?.value);
        const browserZone = Intl.DateTimeFormat().resolvedOptions().timeZone;
        if (empty && [...select.options].some((option) => option.value === browserZone)) {
            select.value = browserZone;
        }
        followZone(select);
        select.addEventListener("change", () => followZone(select));
    }

    // DOMContentLoaded comes before the pickers set themselves up (on load), so they see the chosen zone's offset.
    document.addEventListener("DOMContentLoaded", () => {
        for (const select of document.querySelectorAll("select[data-dynamic-configs-type]")) {
            setUpTypeChoice(select);
        }
        for (const select of document.querySelectorAll("select[data-dynamic-configs-zone]")) {
            setUpZoneChoice(select);
        }
    });
}
