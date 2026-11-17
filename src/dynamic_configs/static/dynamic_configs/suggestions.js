// The dynamic-configs admin's suggestions dropdown: an input marked data-dynamic-configs-suggest shows its datalist as
// the admin's own list, the same in every browser. The admin works without this script: the native datalist remains.
"use strict";
{
    const SUGGEST = "input[data-dynamic-configs-suggest]";
    const ready = new WeakSet();

    // The datalist's suggestions as they are now: a project's script may change them.
    function suggestions(datalist) {
        return [...datalist.options].map((option) => ({ code: option.value, text: option.textContent }));
    }

    // Case-insensitive: the codes that start with the text first, then the suggestions whose text has it, each once.
    function matching(all, typed) {
        const text = typed.toLowerCase();
        const codes = all.filter((item) => item.code.toLowerCase().startsWith(text));
        return codes.concat(all.filter((item) => !codes.includes(item) && item.text.toLowerCase().includes(text)));
    }

    // Scroll the list, not the page, so that the option is in its visible part.
    function reveal(list, option) {
        const top = option.offsetTop;
        const bottom = top + option.offsetHeight;
        if (top < list.scrollTop) {
            list.scrollTop = top;
        } else if (bottom > list.scrollTop + list.clientHeight) {
            list.scrollTop = bottom - list.clientHeight;
        }
    }

    // The input keeps the focus throughout; the list is a popover in the top layer, where the admin's form rows (which
    // hide their overflow) can't clip it, placed from the input's box because it's no longer laid out beside it.
    function setUp(input) {
        ready.add(input);
        const datalist = input.list;
        // Without the list attribute the browser's own popup stays shut.
        input.removeAttribute("list");
        const list = document.createElement("ul");
        list.id = `${input.id || datalist.id}_suggestions`;
        list.className = "dynamic-configs-suggestions";
        list.setAttribute("role", "listbox");
        list.setAttribute("popover", "manual");
        // In the body, away from the admin's styles for lists in forms.
        document.body.append(list);
        input.setAttribute("role", "combobox");
        input.setAttribute("aria-autocomplete", "list");
        input.setAttribute("aria-expanded", "false");
        input.setAttribute("aria-controls", list.id);
        input.autocomplete = "off";
        let options = [];
        let active = -1;
        let open = false;

        // Under the input; above it when the list doesn't fit under it and there's more room above.
        function place() {
            const box = input.getBoundingClientRect();
            const below = document.documentElement.clientHeight - box.bottom;
            const above = below < list.offsetHeight && below < box.top;
            list.style.left = `${box.left}px`;
            list.style.top = `${above ? box.top - list.offsetHeight : box.bottom}px`;
        }

        function highlight(index) {
            active = index;
            options.forEach((option, at) => option.setAttribute("aria-selected", String(at === index)));
            if (index < 0) {
                input.removeAttribute("aria-activedescendant");
            } else {
                input.setAttribute("aria-activedescendant", options[index].id);
                reveal(list, options[index]);
            }
        }

        // A press anywhere else closes it without picking: a finger's press on the input that turns into a scroll
        // never gives it the focus, so no blur would.
        function pressOutside(event) {
            if (event.target !== input && !list.contains(event.target)) {
                close();
            }
        }

        function close() {
            if (open) {
                open = false;
                list.hidePopover();
                input.setAttribute("aria-expanded", "false");
                input.removeAttribute("aria-activedescendant");
                window.removeEventListener("scroll", place, true);
                window.removeEventListener("resize", place);
                document.removeEventListener("pointerdown", pressOutside, true);
            }
        }

        // Every suggestion, with the input's code highlighted; or, as it's typed, the ones that match, with none.
        function show(typed) {
            const all = suggestions(datalist);
            const shown = typed && input.value ? matching(all, input.value) : all;
            if (!shown.length) {
                close();
                return;
            }
            options = shown.map((item, index) => {
                const option = document.createElement("li");
                option.id = `${list.id}_${index}`;
                option.setAttribute("role", "option");
                option.dataset.value = item.code;
                option.textContent = item.text;
                return option;
            });
            list.replaceChildren(...options);
            if (!open) {
                open = true;
                list.showPopover();
                input.setAttribute("aria-expanded", "true");
                window.addEventListener("scroll", place, true);
                window.addEventListener("resize", place);
                document.addEventListener("pointerdown", pressOutside, true);
            }
            list.scrollTop = 0;
            place();
            const code = input.value.toUpperCase();
            highlight(typed ? -1 : shown.findIndex((item) => item.code === code));
        }

        function pick(option) {
            input.value = option.dataset.value;
            input.dispatchEvent(new Event("input", { bubbles: true }));
            input.dispatchEvent(new Event("change", { bubbles: true }));
            close();
        }

        // Opening on the press, before the focus moves, is what makes the first click open it.
        input.addEventListener("pointerdown", (event) => {
            if (event.button === 0 && !open) {
                show(false);
            }
        });
        // Only typing filters: the input events a script sends (a pick's own, say) leave the list alone.
        input.addEventListener("input", (event) => {
            if (event.isTrusted) {
                show(true);
            }
        });
        input.addEventListener("keydown", (event) => {
            if (event.isComposing) {
                return;
            }
            if (event.key === "ArrowDown" || event.key === "ArrowUp") {
                event.preventDefault();
                if (!open) {
                    show(false);
                } else if (!event.altKey) {
                    const last = options.length - 1;
                    const step = event.key === "ArrowDown" ? 1 : -1;
                    highlight(active < 0 ? (step > 0 ? 0 : last) : Math.min(Math.max(active + step, 0), last));
                }
            } else if (event.key === "Enter") {
                // A pick neither saves the page nor adds the list editor's item; otherwise Enter does what it did.
                if (open && active >= 0) {
                    event.preventDefault();
                    event.stopPropagation();
                    pick(options[active]);
                } else {
                    close();
                }
            } else if (event.key === "Escape" && open) {
                event.preventDefault();
                event.stopPropagation();
                close();
            } else if (event.key === "Tab") {
                close();
            }
        });
        // Leaving never picks, so a typed code that isn't suggested stays as typed.
        input.addEventListener("blur", close);
        // A press on the list would take the focus from the input, which would close it before the click.
        list.addEventListener("pointerdown", (event) => event.preventDefault());
        list.addEventListener("click", (event) => {
            const option = event.target instanceof Element ? event.target.closest("[role=option]") : null;
            if (option) {
                pick(option);
            }
        });
    }

    function setUpIfSuggesting(input) {
        const suggesting = input instanceof HTMLInputElement && input.matches(SUGGEST) && !ready.has(input);
        if (suggesting && input.list instanceof HTMLDataListElement) {
            setUp(input);
        }
    }

    // A browser without popovers keeps the native datalist.
    if ("showPopover" in HTMLElement.prototype) {
        document.addEventListener("DOMContentLoaded", () => {
            document.querySelectorAll(SUGGEST).forEach(setUpIfSuggesting);
        });
        // An input added later is set up when it's first pressed or focused, before its own listeners would run.
        for (const type of ["pointerdown", "focusin"]) {
            document.addEventListener(type, (event) => setUpIfSuggesting(event.target), true);
        }
    }
}
