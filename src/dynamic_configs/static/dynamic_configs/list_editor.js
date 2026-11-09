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

    // Ask the check URL to do `action`; return its answer, or null after saying in `target` that there's none.
    async function ask(container, action, fields, target) {
        const form = container.closest("form");
        const body = new FormData();
        body.append("action", action);
        body.append("name", `${container.dataset.name}__item`);
        body.append("csrfmiddlewaretoken", form.querySelector("[name=csrfmiddlewaretoken]").value);
        for (const [key, value] of Object.entries(fields)) {
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
        if (items === null) {
            // The page shows text that isn't a list yet (input re-displayed after an error): leave it as text.
            return;
        }
        let selected = null;
        let descending = false;
        let busy = false;

        // ---- The item editor's inputs ----

        const inputs = () =>
            [...editor.querySelectorAll("input, select, textarea")].filter((input) => input.name.startsWith(itemName));
        const read = (input) => (input.type === "checkbox" ? input.checked : input.value);
        const state = () => JSON.stringify(inputs().map(read));
        const write = (input, value) => {
            if (input.type === "checkbox") {
                input.checked = Boolean(value);
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
        const editorFields = () => {
            const fields = {};
            for (const input of inputs()) {
                if (input.type !== "checkbox" || input.checked) {
                    fields[input.name] = input.value;
                }
            }
            return fields;
        };

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
        raw.before(listPart);
        editor.hidden = false;
        raw.hidden = true;
        // The note is for the page without this script, which can't edit such a list.
        container.querySelector(`.${PREFIX}-locked`)?.setAttribute("hidden", "");
        modeInput.value = "list";

        function render() {
            select.replaceChildren(
                ...items.map((text, index) => {
                    const option = make("option", "", text);
                    option.value = String(index);
                    return option;
                }),
            );
            select.selectedIndex = selected ?? -1;
            select.disabled = busy;
            saveButton.textContent = selected === null ? "Add" : "Update";
            saveButton.disabled = busy;
            clearButton.disabled = busy;
            removeButton.disabled = busy || selected === null;
            upButton.disabled = busy || selected === null || selected === 0;
            downButton.disabled = busy || selected === null || selected === items.length - 1;
            sortButton.disabled = busy;
            sortButton.textContent = descending ? "Sort ↓" : "Sort ↑";
            sortButton.title = descending ? "Sort largest first" : "Sort smallest first";
            itemsInput.value = JSON.stringify(items);
        }

        // Ask the server, with every button disabled until it answers, so a second click can't act twice.
        async function request(action, fields, target = message) {
            busy = true;
            target.textContent = "";
            render();
            try {
                return await ask(container, action, fields, target);
            } finally {
                busy = false;
                render();
            }
        }

        // ---- Actions ----

        saveButton.addEventListener("click", async () => {
            const position = selected;
            const answer = await request("check", {
                ...editorFields(),
                items: JSON.stringify(items),
                position: position === null ? "" : String(position),
            });
            if (!answer) {
                return;
            }
            if (answer.errors) {
                message.textContent = answer.errors.join(" ");
                return;
            }
            if (position === null) {
                items.push(answer.text);
                clearEditor();
            } else {
                items[position] = answer.text;
                baseline = state();
            }
            render();
        });

        select.addEventListener("change", async () => {
            const index = select.selectedIndex;
            const answer = await request("load", { text: items[index] });
            if (!answer) {
                return;
            }
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
            render();
        });

        clearButton.addEventListener("click", () => {
            selected = null;
            clearEditor();
            message.textContent = "";
            render();
        });

        removeButton.addEventListener("click", () => {
            items.splice(selected, 1);
            selected = null;
            clearEditor();
            render();
        });

        const move = (step) => {
            const to = selected + step;
            [items[selected], items[to]] = [items[to], items[selected]];
            selected = to;
            render();
        };
        upButton.addEventListener("click", () => move(-1));
        downButton.addEventListener("click", () => move(1));

        sortButton.addEventListener("click", async () => {
            const answer = await request("sort", {
                items: JSON.stringify(items),
                direction: descending ? "descending" : "ascending",
            });
            if (!answer) {
                return;
            }
            if (answer.errors) {
                message.textContent = answer.errors.join(" ");
                return;
            }
            items = answer.texts;
            descending = !descending;
            selected = null;
            clearEditor();
            render();
        });

        editor.addEventListener("keydown", (event) => {
            // Enter in a one-line input adds or updates the item, rather than saving the whole page.
            if (event.key === "Enter" && event.target instanceof HTMLInputElement) {
                event.preventDefault();
                saveButton.click();
            }
        });

        form.addEventListener("submit", (event) => {
            if (modeInput.value === "list" && state() !== baseline) {
                event.preventDefault();
                message.textContent = UNFINISHED;
                inputs()[0]?.focus();
            }
        });

        render();
    }

    document.addEventListener("DOMContentLoaded", () => {
        for (const container of document.querySelectorAll(LIST)) {
            setUp(container);
        }
    });
}
