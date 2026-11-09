// The admin's list editor (see the design document's Admin section): a list or set is edited one item at a time in
// the item type's own input, and the server checks every item, so every rule stays in Python. Every page works
// without this script: the field is then a textarea with one item per line.
"use strict";
{
    const LIST = "[data-dynamic-configs-list]";
    const PREFIX = "dynamic-configs-list";
    const UNFINISHED = "You have an unsaved change to an item: click Update or Clear.";
    const UNREACHABLE = "Couldn't check the item; try again.";

    function make(tag, className, text) {
        const node = document.createElement(tag);
        if (className) {
            node.className = className;
        }
        if (text !== undefined) {
            node.textContent = text;
        }
        return node;
    }

    function makeButton(text) {
        const node = make("button", "button", text);
        node.type = "button";
        return node;
    }

    // Ask the check URL to do `action` with `fields`, [name, value] pairs as a form sends them (a name repeats for each
    // of several values); return its answer, or null after saying in `target` that there's none.
    async function ask(container, action, fields, target) {
        const form = container.closest("form");
        const body = new FormData();
        body.append("action", action);
        body.append("name", `${container.dataset.name}__item`);
        body.append("csrfmiddlewaretoken", form.querySelector("[name=csrfmiddlewaretoken]").value);
        for (const [key, value] of fields) {
            body.append(key, value);
        }
        try {
            const response = await fetch(container.dataset.checkUrl, {
                method: "POST",
                body,
                credentials: "same-origin",
            });
            if (!response.ok) {
                throw new Error(`The check URL answered ${response.status}.`);
            }
            return await response.json();
        } catch {
            target.textContent = UNREACHABLE;
            return null;
        }
    }

    function setUp(container) {
        const name = container.dataset.name;
        const itemName = `${name}__item`;
        const form = container.closest("form");
        const raw = container.querySelector(`.${PREFIX}-raw`);
        const textarea = raw.querySelector("textarea");
        const itemsInput = container.querySelector(`input[name="${name}__items"]`);
        const modeInput = container.querySelector(`input[name="${name}__mode"]`);
        const editor = container.querySelector(`.${PREFIX}-item`);
        let items = JSON.parse(itemsInput.value);
        // null: the page shows text that isn't a list yet (input re-displayed after an error), so the editor opens in
        // raw mode, with no list to cancel back to.
        const startRaw = items === null;
        items ??= [];
        // The item loaded in the editor, and the one chosen in the list since, waiting for or being loaded.
        let selected = null;
        let chosen = null;
        let descending = false;
        let busy = false;

        // ---- The item editor's inputs ----

        const inputs = () =>
            [...editor.querySelectorAll("input, select, textarea")].filter((input) => input.name.startsWith(itemName));
        const checkable = (input) => input.type === "checkbox" || input.type === "radio";
        const multiple = (input) => input instanceof HTMLSelectElement && input.multiple;
        // What an input holds: whether a checkbox or radio button is checked, a <select multiple>'s chosen values, or
        // its value.
        const read = (input) => {
            if (checkable(input)) {
                return input.checked;
            }
            if (multiple(input)) {
                return [...input.selectedOptions].map((option) => option.value);
            }
            return input.value;
        };
        const state = () => JSON.stringify(inputs().map(read));
        // Fill an input with what `read` gave, or with what the check URL loaded: whether a checkbox is checked, the
        // chosen value of radio buttons, or every chosen value of checkboxes sharing a name or a <select multiple>.
        const write = (input, value) => {
            if (checkable(input)) {
                if (Array.isArray(value)) {
                    input.checked = value.includes(input.value);
                } else if (typeof value === "boolean") {
                    input.checked = value;
                } else {
                    input.checked = input.value === value;
                }
            } else if (multiple(input)) {
                for (const option of input.options) {
                    option.selected = value.includes(option.value);
                }
            } else {
                input.value = value;
            }
            // As if chosen by hand, so the admin script's zone notes follow.
            input.dispatchEvent(new Event("change", { bubbles: true }));
        };
        // The editor as the page left it (the admin script has already set an empty datetime's zone): Clear's state.
        const empty = inputs().map(read);
        // What the editor held when it was last loaded or cleared; anything else is an unfinished change.
        let baseline = state();
        const clearEditor = () => {
            inputs().forEach((input, index) => write(input, empty[index]));
            baseline = state();
        };
        const unfinished = () => state() !== baseline;
        // The editor's inputs as a form sends them: [name, value] pairs, a name repeated for each of several values, and
        // nothing for an unchecked checkbox or radio button.
        const editorFields = () =>
            inputs().flatMap((input) => {
                if (checkable(input)) {
                    return input.checked ? [[input.name, input.value]] : [];
                }
                if (multiple(input)) {
                    return [...input.selectedOptions].map((option) => [input.name, option.value]);
                }
                return [[input.name, input.value]];
            });

        // ---- The page's parts ----

        const ordered = container.dataset.set !== "true";
        const sortable = ordered && container.dataset.sortable === "true";
        const message = make("p", `${PREFIX}-message`);
        message.setAttribute("aria-live", "polite");
        const saveButton = makeButton("Add");
        const clearButton = makeButton("Clear");
        const select = make("select", `${PREFIX}-items`);
        select.size = 8;
        select.setAttribute("aria-label", "Items");
        const removeButton = makeButton("Remove");
        const upButton = makeButton("Up");
        const downButton = makeButton("Down");
        const sortButton = makeButton("Sort ↑");

        const editorButtons = make("div", `${PREFIX}-buttons`);
        editorButtons.append(saveButton, clearButton);
        const editorRow = make("div", `${PREFIX}-row`);
        editorRow.append(editor, editorButtons);
        const listButtons = make("div", `${PREFIX}-buttons`);
        listButtons.append(removeButton);
        if (ordered) {
            listButtons.append(upButton, downButton);
        }
        if (sortable) {
            listButtons.append(sortButton);
        }
        const listRow = make("div", `${PREFIX}-row`);
        listRow.append(select, listButtons);
        const listPart = make("div", `${PREFIX}-editor`);
        listPart.append(editorRow, message, listRow);
        // Raw mode: the whole list as text, one item per line, for pasting and bulk edits.
        const rawLink = makeButton("Raw mode");
        rawLink.className = `${PREFIX}-raw-link`;
        listPart.append(rawLink);
        const applyButton = makeButton("Apply");
        const cancelButton = makeButton("Cancel");
        // Its own class: tests and styles find the list's message by `${PREFIX}-message` alone.
        const rawMessage = make("p", `${PREFIX}-raw-message`);
        rawMessage.setAttribute("aria-live", "polite");
        const rawErrors = make("ul", `errorlist ${PREFIX}-raw-errors`);
        const rawButtons = make("div", `${PREFIX}-row`);
        rawButtons.append(applyButton, cancelButton);
        raw.append(rawButtons, rawMessage, rawErrors);
        raw.before(listPart);
        editor.hidden = false;
        raw.hidden = true;
        // The note is for the page without this script, which can't edit such a list.
        container.querySelector(`.${PREFIX}-locked`)?.setAttribute("hidden", "");
        // Likewise for the textarea's read-only state: once the item editor has fixed the list, raw mode can edit it.
        textarea.readOnly = false;
        modeInput.value = "list";

        function render() {
            select.replaceChildren(
                ...items.map((text, index) => {
                    const option = make("option", "", text);
                    option.value = String(index);
                    return option;
                }),
            );
            // Never disabled: the browser would take the focus away, and the keyboard couldn't move on through it.
            select.selectedIndex = chosen ?? selected ?? -1;
            saveButton.textContent = selected === null ? "Add" : "Update";
            saveButton.disabled = busy;
            clearButton.disabled = busy;
            removeButton.disabled = busy || selected === null;
            upButton.disabled = busy || selected === null || selected === 0;
            downButton.disabled = busy || selected === null || selected === items.length - 1;
            sortButton.disabled = busy;
            applyButton.disabled = busy;
            cancelButton.disabled = busy;
            sortButton.textContent = descending ? "Sort ↓" : "Sort ↑";
            sortButton.title = descending ? "Sort largest first" : "Sort smallest first";
            itemsInput.value = JSON.stringify(items);
        }

        // Ask the server, with the buttons disabled until it answers, so a second click can't act twice; then `apply`
        // the answer, if there is one. The list stays enabled: an item chosen in it meanwhile loads after the answer.
        async function request(action, fields, apply, target = message) {
            busy = true;
            const focused = document.activeElement;
            target.textContent = "";
            render();
            const answer = await ask(container, action, fields, target);
            busy = false;
            if (answer) {
                apply(answer);
            } else {
                // Nothing changes, so an item chosen meanwhile isn't loaded either.
                chosen = null;
            }
            render();
            // A button that was disabled lost the focus to the page: give it back, so the keyboard can press it again.
            if (
                document.activeElement === document.body &&
                focused !== document.body &&
                focused?.isConnected &&
                !focused.disabled
            ) {
                focused.focus();
            }
            if (chosen !== null) {
                loadChosen();
            }
        }

        // ---- Actions ----

        saveButton.addEventListener("click", () => {
            const position = selected;
            // What the editor held when it was sent: anything typed while the server checks it is kept.
            const sent = state();
            request(
                "check",
                [
                    ...editorFields(),
                    ["items", JSON.stringify(items)],
                    ["position", position === null ? "" : String(position)],
                ],
                (answer) => {
                    if (answer.errors) {
                        message.textContent = answer.errors.join(" ");
                        // Refused: an item chosen meanwhile isn't loaded, so the error stays to be read.
                        chosen = null;
                        return;
                    }
                    if (position === null) {
                        items.push(answer.text);
                        if (state() === sent) {
                            clearEditor();
                        }
                    } else {
                        items[position] = answer.text;
                        // The item as sent is the one stored: anything typed meanwhile is an unfinished change.
                        baseline = sent;
                    }
                },
            );
        });

        // Load the item last chosen in the list into the editor.
        function loadChosen() {
            const index = chosen;
            request("load", [["text", items[index]]], (answer) => {
                if (chosen !== index) {
                    // Another item was chosen meanwhile: this answer is out of date, and that item loads next.
                    return;
                }
                chosen = null;
                selected = index;
                if (answer.errors) {
                    // An item the type can't read (a hand-edited row): selected anyway, so it can be removed or replaced.
                    clearEditor();
                    message.textContent = answer.errors.join(" ");
                } else {
                    for (const input of inputs()) {
                        if (input.name in answer.values) {
                            write(input, answer.values[input.name]);
                        }
                    }
                    baseline = state();
                }
            });
        }

        select.addEventListener("change", () => {
            const index = select.selectedIndex;
            if (index < 0) {
                return;
            }
            // The last item chosen wins: while a request is pending, it waits for the answer (see `request`).
            chosen = index;
            if (!busy) {
                loadChosen();
            }
        });

        clearButton.addEventListener("click", () => {
            selected = null;
            clearEditor();
            message.textContent = "";
            render();
        });

        // Remove, and Up or Down onto an end, disable the button just pressed, and the browser drops the focus to the
        // page: put it on the list, so the keyboard can carry on.
        const keepFocus = (button, action) => {
            const focused = document.activeElement;
            action();
            if ((focused === button && button.disabled) || !focused?.isConnected) {
                select.focus();
            }
        };

        removeButton.addEventListener("click", () =>
            keepFocus(removeButton, () => {
                items.splice(selected, 1);
                selected = null;
                clearEditor();
                render();
            }),
        );

        const move = (step) => {
            const to = selected + step;
            [items[selected], items[to]] = [items[to], items[selected]];
            selected = to;
            render();
        };
        upButton.addEventListener("click", () => keepFocus(upButton, () => move(-1)));
        downButton.addEventListener("click", () => keepFocus(downButton, () => move(1)));

        sortButton.addEventListener("click", () => {
            request(
                "sort",
                [
                    ["items", JSON.stringify(items)],
                    ["direction", descending ? "descending" : "ascending"],
                ],
                (answer) => {
                    if (answer.errors) {
                        message.textContent = answer.errors.join(" ");
                        // Refused: an item chosen meanwhile isn't loaded, so the error stays to be read.
                        chosen = null;
                        return;
                    }
                    items = answer.texts;
                    descending = !descending;
                    // The order changed under any item chosen meanwhile, so that choice goes too.
                    selected = null;
                    chosen = null;
                    clearEditor();
                },
            );
        });

        editor.addEventListener("keydown", (event) => {
            // Enter in a one-line input adds or updates the item, rather than saving the whole page.
            if (event.key === "Enter" && event.target instanceof HTMLInputElement) {
                event.preventDefault();
                saveButton.click();
            }
        });

        form.addEventListener("submit", (event) => {
            if (modeInput.value === "list" && unfinished()) {
                event.preventDefault();
                message.textContent = UNFINISHED;
                inputs()[0]?.focus();
            }
        });

        function openRaw() {
            listPart.hidden = true;
            raw.hidden = false;
            rawErrors.replaceChildren();
            rawMessage.textContent = "";
            message.textContent = "";
            // Saving now saves the text, which the server reads as it does without this script.
            modeInput.value = "raw";
            textarea.focus();
        }

        function closeRaw() {
            raw.hidden = true;
            listPart.hidden = false;
            cancelButton.hidden = false;
            modeInput.value = "list";
            selected = null;
            clearEditor();
            render();
        }

        rawLink.addEventListener("click", () => {
            // Cancel would throw away an item typed but not added, so the same guard as Save applies.
            if (unfinished()) {
                message.textContent = UNFINISHED;
                return;
            }
            const broken = items.findIndex((text) => /[\r\n]/.test(text));
            if (broken >= 0) {
                message.textContent =
                    `Item ${broken + 1} contains a line break, so the list can't be shown one item per line. ` +
                    "Edit it in the item editor.";
                return;
            }
            // One empty item would show as an empty textarea, which reads back as no items.
            if (items.length === 1 && items[0] === "") {
                message.textContent =
                    "The list is one empty item, which raw mode would show as no items. Edit it in the item editor.";
                return;
            }
            textarea.value = items.join("\n");
            openRaw();
        });

        // Every line is an item, blank ones included; name the blank lines (empty or only spaces), so a stray one is
        // easy to spot. An empty textarea is no items, and no note.
        function blankNote(text) {
            if (text === "") {
                return "";
            }
            const blank = text.split("\n").flatMap((line, index) => (line.trim() === "" ? [index + 1] : []));
            if (blank.length === 0) {
                return "";
            }
            if (blank.length === 1) {
                return `Line ${blank[0]} was blank, so it was added as a blank item.`;
            }
            const named = `${blank.slice(0, -1).join(", ")} and ${blank[blank.length - 1]}`;
            return `Lines ${named} were blank, so they were added as blank items.`;
        }

        applyButton.addEventListener("click", () => {
            rawErrors.replaceChildren();
            const text = textarea.value;
            request(
                "lines",
                [["lines", JSON.stringify(text.split("\n"))]],
                (answer) => {
                    if (answer.errors) {
                        rawErrors.replaceChildren(...answer.errors.map((error) => make("li", "", error)));
                        return;
                    }
                    const note = blankNote(text);
                    items = answer.texts;
                    closeRaw();
                    message.textContent = note;
                },
                rawMessage,
            );
        });

        cancelButton.addEventListener("click", closeRaw);

        render();
        if (startRaw) {
            cancelButton.hidden = true;
            openRaw();
        }
    }

    document.addEventListener("DOMContentLoaded", () => {
        for (const container of document.querySelectorAll(LIST)) {
            setUp(container);
        }
    });
}
