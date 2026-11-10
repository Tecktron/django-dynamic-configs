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

    const ZONE_SELECT = "select[data-dynamic-configs-zone]";

    // A zoned datetime posts as <name>_0 (date), <name>_1 (time) and <name>_2 (zone).
    function zoneInputs(select) {
        const base = select.name.slice(0, -"_2".length);
        return [`${base}_0`, `${base}_1`].map((name) => select.form.elements[name]).filter(Boolean);
    }

    // The zone select that a date or time input, or one of its pickers, belongs to; null for anything else. Django puts
    // each input's picker links right after it.
    function zoneSelectFor(target) {
        if (!(target instanceof Element)) {
            return null;
        }
        const input = target.matches("input") ? target : target.closest(".datetimeshortcuts")?.previousElementSibling;
        const match = /^(.*)_[01]$/.exec(input?.name ?? "");
        const select = match && input.form?.elements[`${match[1]}_2`];
        return select instanceof Element && select.matches(ZONE_SELECT) ? select : null;
    }

    // The chosen zone's offset, or null when the browser doesn't know the zone (an older browser and a newer zone
    // raise a RangeError); the pickers then keep the zone they had.
    function zoneOffset(select) {
        try {
            return utcOffset(select.value);
        } catch (error) {
            if (error instanceof RangeError) {
                return null;
            }
            throw error;
        }
    }

    // Django's date and time pickers take Today and Now from the page's one server offset, read on every click. A page
    // may have several zoned datetimes (inline rows, say), so point it at a widget's zone whenever that widget's
    // inputs or pickers are pressed or reached by keyboard, before the click that reads it.
    function followZone(select) {
        const offset = zoneOffset(select);
        if (offset !== null) {
            document.body.dataset.adminUtcOffset = String(offset);
        }
    }

    // Django notes under the pickers how far the browser is from the server's zone, worked out once for the whole page.
    // Redo a widget's note for its chosen zone, with Django's own function, so each Django version keeps its wording
    // and placement. Skipped when the pickers aren't on the page (a skin may replace them).
    function renoteZone(select) {
        const shortcuts = window.DateTimeShortcuts;
        const offset = zoneOffset(select);
        if (typeof shortcuts?.addTimezoneWarning !== "function" || offset === null) {
            return;
        }
        const inputs = zoneInputs(select);
        for (const input of inputs) {
            // Django 6 puts the note beside the field, with an id; Django 5.2 puts it inside the input's parent.
            document.getElementById(`${input.id}_timezone_warning_helptext`)?.remove();
            for (const note of input.parentNode.querySelectorAll(`:scope > .${shortcuts.timezoneWarningClass}`)) {
                note.remove();
            }
        }
        const data = document.body.dataset;
        const [savedOffset, savedZone] = [shortcuts.timezoneOffset, data.adminServerTimezone];
        shortcuts.timezoneOffset = new Date().getTimezoneOffset() * -60 - offset;
        data.adminServerTimezone = select.value;
        try {
            for (const input of inputs) {
                shortcuts.addTimezoneWarning(input);
            }
        } finally {
            shortcuts.timezoneOffset = savedOffset;
            if (savedZone === undefined) {
                delete data.adminServerTimezone;
            } else {
                data.adminServerTimezone = savedZone;
            }
        }
    }

    function browserZone() {
        return Intl.DateTimeFormat().resolvedOptions().timeZone;
    }

    function offers(select, zone) {
        return Boolean(zone) && [...select.options].some((option) => option.value === zone);
    }

    // Start an empty value on the browser's zone. A value that's already shown keeps its zone, since changing the zone
    // alone would change the instant.
    function startOnBrowserZone(select) {
        const empty = zoneInputs(select).every((input) => !input.value);
        if (empty && offers(select, browserZone())) {
            select.value = browserZone();
        }
    }

    const ZONE_SHORTCUTS = "dynamic-configs-zone-shortcuts";
    const PICK_ZONE = "data-dynamic-configs-pick-zone";

    // "My zone | Server zone" after a zone select, styled like Django's Now and Today links, leaving out a zone the
    // select doesn't offer (the page names the server's zone only when it's offered). Inline rows are copied from a
    // template row that already has the links, so a select that has them is skipped.
    function addZoneShortcuts(select) {
        if (select.nextElementSibling?.classList.contains(ZONE_SHORTCUTS)) {
            return;
        }
        const links = [
            ["My zone", browserZone()],
            ["Server zone", select.dataset.serverZone],
        ]
            .filter(([, zone]) => offers(select, zone))
            .map(([text, zone]) => {
                const link = document.createElement("a");
                link.href = "#";
                link.textContent = text;
                link.title = zone;
                link.setAttribute(PICK_ZONE, zone);
                return link;
            });
        if (!links.length) {
            return;
        }
        const shortcuts = document.createElement("span");
        shortcuts.className = `datetimeshortcuts ${ZONE_SHORTCUTS}`;
        links.forEach((link, index) => {
            if (index) {
                shortcuts.append(" | ");
            }
            shortcuts.append(link);
        });
        select.after(shortcuts);
    }

    // Listening on the document covers inline rows added later.
    for (const type of ["pointerdown", "focusin"]) {
        document.addEventListener(
            type,
            (event) => {
                const select = zoneSelectFor(event.target);
                if (select) {
                    followZone(select);
                }
            },
            true,
        );
    }
    document.addEventListener("change", (event) => {
        if (event.target instanceof Element && event.target.matches(ZONE_SELECT)) {
            followZone(event.target);
            renoteZone(event.target);
        }
    });
    // Picking a zone with a link changes the select as choosing it would, so the note and pickers follow.
    document.addEventListener("click", (event) => {
        const link = event.target instanceof Element ? event.target.closest(`a[${PICK_ZONE}]`) : null;
        const select = link?.parentElement.previousElementSibling;
        if (select instanceof Element && select.matches(ZONE_SELECT)) {
            event.preventDefault();
            select.value = link.getAttribute(PICK_ZONE);
            select.dispatchEvent(new Event("change", { bubbles: true }));
        }
    });
    document.addEventListener("formset:added", (event) => {
        const selects = event.target.querySelectorAll(ZONE_SELECT);
        for (const select of selects) {
            startOnBrowserZone(select);
            addZoneShortcuts(select);
        }
        // After Django has set up the new row's pickers and notes.
        setTimeout(() => selects.forEach(renoteZone));
    });

    // DOMContentLoaded comes before the pickers set themselves up (on load), so they start in the first widget's zone.
    document.addEventListener("DOMContentLoaded", () => {
        for (const select of document.querySelectorAll("select[data-dynamic-configs-type]")) {
            setUpTypeChoice(select);
        }
        const selects = document.querySelectorAll(ZONE_SELECT);
        selects.forEach(startOnBrowserZone);
        selects.forEach(addZoneShortcuts);
        if (selects.length) {
            followZone(selects[0]);
        }
    });
    // After Django's notes, drawn on load for the first widget's zone, give each widget its own.
    window.addEventListener("load", () => setTimeout(() => document.querySelectorAll(ZONE_SELECT).forEach(renoteZone)));
}
