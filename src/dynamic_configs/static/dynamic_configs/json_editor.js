// The admin's JSON editor: a Format link, Enter that keeps the indent, a note saying whether the JSON is valid, and
// colours. It never parses values: every token keeps the exact text that was typed, so numbers too large or too
// precise for JavaScript are never rounded. Every page works without this script.
"use strict";
{
    const FIELD = "textarea[data-dynamic-configs-json]";
    const PREFIX = "dynamic-configs-json";
    const INDENT = "  ";

    // ---- Tokens ------------------------------------------------------------------------------------------------

    const PUNCTUATION = "{}[]:,";
    const SPACE = /[ \t\n\r]+/y;
    const NUMBER = /-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/y;
    // A run of anything that isn't JSON's punctuation, a quote or space: a literal, or text JSON doesn't allow.
    const WORD = /[^\s{}[\]:,"]+/y;
    const LITERALS = ["true", "false", "null"];

    function matchAt(pattern, text, at) {
        pattern.lastIndex = at;
        return pattern.test(text) ? pattern.lastIndex : null;
    }

    // Read the string starting at the quote at ``at``; returns its end and, for a string JSON doesn't allow, why.
    function readString(text, at) {
        let problem = null;
        let index = at + 1;
        while (index < text.length) {
            const char = text[index];
            if (char === '"') {
                return { end: index + 1, problem };
            }
            if (char === "\n" || char === "\r") {
                break;
            }
            if (char === "\\") {
                const escape = text[index + 1];
                if (escape === "u" && /^[0-9a-fA-F]{4}$/.test(text.slice(index + 2, index + 6))) {
                    index += 6;
                } else if (escape !== undefined && '"\\/bfnrt'.includes(escape)) {
                    index += 2;
                } else {
                    problem ??= "invalid escape in a string";
                    index += 1;
                }
                continue;
            }
            if (char < " ") {
                problem ??= "a string can't contain a tab or other control character";
            }
            index += 1;
        }
        return { end: index, problem: "unterminated string" };
    }

    // Split ``text`` into tokens, each keeping its exact text: punctuation, string, number, literal, space or invalid.
    function tokenize(text) {
        const tokens = [];
        let at = 0;
        while (at < text.length) {
            const start = at;
            let kind;
            let problem = null;
            const spaceEnd = matchAt(SPACE, text, at);
            const numberEnd = matchAt(NUMBER, text, at);
            if (PUNCTUATION.includes(text[at])) {
                kind = "punctuation";
                at += 1;
            } else if (text[at] === '"') {
                ({ end: at, problem } = readString(text, at));
                kind = problem ? "invalid" : "string";
            } else if (spaceEnd !== null) {
                kind = "space";
                at = spaceEnd;
            } else if (numberEnd !== null && matchAt(WORD, text, numberEnd) === null) {
                kind = "number";
                at = numberEnd;
            } else {
                // A character no rule takes (a no-break space, say) still moves on, as text JSON doesn't allow.
                at = matchAt(WORD, text, at) ?? at + 1;
                kind = LITERALS.includes(text.slice(start, at)) ? "literal" : "invalid";
            }
            tokens.push({ kind, start, end: at, text: text.slice(start, at), problem });
        }
        return tokens;
    }

    // ---- Checking ----------------------------------------------------------------------------------------------

    // Check that the tokens make one JSON object or array, as the server requires, and mark the strings used as
    // keys. Returns null when they do, or the problem: ``{message, token}`` (``token`` is null at the end of the
    // text), or ``{message, plain: true}`` for a message shown without a position. A stack instead of recursion, so
    // deep nesting can't overflow.
    function check(tokens) {
        const stack = [];
        let expecting = "top";
        const opened = (token) => {
            stack.push(token.text);
            expecting = token.text === "{" ? "key or close" : "value or close";
        };
        const valueDone = () => {
            expecting = stack.length ? "comma or close" : "end";
        };
        const closed = () => {
            stack.pop();
            valueDone();
        };
        const isOpening = (token) => token.kind === "punctuation" && (token.text === "{" || token.text === "[");
        const isScalar = (token) => ["string", "number", "literal"].includes(token.kind);
        const value = (token) => {
            if (isOpening(token)) {
                opened(token);
                return null;
            }
            if (isScalar(token)) {
                valueDone();
                return null;
            }
            return { message: "expected a value", token };
        };
        const key = (token) => {
            if (token.kind !== "string") {
                return { message: "expected a property name in double quotes", token };
            }
            token.kind = "key";
            expecting = "colon";
            return null;
        };

        for (const token of tokens) {
            if (token.kind === "space") {
                continue;
            }
            if (token.kind === "invalid") {
                return { message: token.problem ?? "unexpected text", token };
            }
            let problem = null;
            switch (expecting) {
                case "top":
                    if (isOpening(token)) {
                        opened(token);
                    } else if (isScalar(token)) {
                        return { message: "Enter a JSON object or array.", plain: true };
                    } else {
                        problem = { message: "expected a value", token };
                    }
                    break;
                case "value or close":
                    if (token.text === "]" && token.kind === "punctuation") {
                        closed();
                    } else {
                        problem = value(token);
                    }
                    break;
                case "value":
                    problem = value(token);
                    break;
                case "key or close":
                    if (token.text === "}" && token.kind === "punctuation") {
                        closed();
                    } else {
                        problem = key(token);
                    }
                    break;
                case "key":
                    problem = key(token);
                    break;
                case "colon":
                    if (token.text === ":" && token.kind === "punctuation") {
                        expecting = "value";
                    } else {
                        problem = { message: 'expected ":"', token };
                    }
                    break;
                case "comma or close": {
                    const inObject = stack.at(-1) === "{";
                    const closer = inObject ? "}" : "]";
                    if (token.kind === "punctuation" && token.text === ",") {
                        expecting = inObject ? "key" : "value";
                    } else if (token.kind === "punctuation" && token.text === closer) {
                        closed();
                    } else {
                        problem = { message: `expected "," or "${closer}"`, token };
                    }
                    break;
                }
                default:
                    problem = { message: "unexpected text after the end of the JSON", token };
            }
            if (problem) {
                return problem;
            }
        }
        if (expecting === "top") {
            // Nothing but space: an empty value, which the field's own rules allow or not.
            return null;
        }
        return expecting === "end" ? null : { message: "the JSON ends too soon", token: null };
    }

    // ---- Formatting --------------------------------------------------------------------------------------------

    // Rebuild valid JSON from its tokens, indented two spaces per level, every token's text unchanged.
    function format(tokens) {
        const items = tokens.filter((token) => token.kind !== "space");
        let text = "";
        let depth = 0;
        for (let index = 0; index < items.length; index += 1) {
            const token = items[index];
            const isPunctuation = token.kind === "punctuation";
            if (isPunctuation && (token.text === "{" || token.text === "[")) {
                const next = items[index + 1];
                if (next.kind === "punctuation" && (next.text === "}" || next.text === "]")) {
                    text += token.text + next.text;
                    index += 1;
                } else {
                    depth += 1;
                    text += `${token.text}\n${INDENT.repeat(depth)}`;
                }
            } else if (isPunctuation && (token.text === "}" || token.text === "]")) {
                depth -= 1;
                text += `\n${INDENT.repeat(depth)}${token.text}`;
            } else if (isPunctuation && token.text === ",") {
                text += `,\n${INDENT.repeat(depth)}`;
            } else if (isPunctuation && token.text === ":") {
                text += ": ";
            } else {
                text += token.text;
            }
        }
        return text;
    }

    // ---- Editing -----------------------------------------------------------------------------------------------

    // Replace ``start``..``end`` with ``text`` as typing would, so the browser's undo can take it back.
    function replaceText(field, start, end, text) {
        field.focus();
        field.setSelectionRange(start, end);
        if (!document.execCommand("insertText", false, text)) {
            field.setRangeText(text, start, end, "end");
            field.dispatchEvent(new Event("input", { bubbles: true }));
        }
    }

    // Enter keeps the line's indent, adds a level after an opening bracket, and between a pair of brackets puts the
    // closing one on its own line.
    function newLine(event) {
        if (event.key !== "Enter" || event.shiftKey || event.ctrlKey || event.altKey || event.metaKey) {
            return;
        }
        if (event.isComposing) {
            return;
        }
        const field = event.target;
        const { value, selectionStart: start } = field;
        let end = field.selectionEnd;
        const lineStart = value.lastIndexOf("\n", start - 1) + 1;
        const before = value.slice(lineStart, start);
        const indent = /^[ \t]*/.exec(before)[0];
        const opening = before.trimEnd().at(-1);
        const opens = opening === "{" || opening === "[";
        let text = `\n${opens ? indent + INDENT : indent}`;
        const caret = start + text.length;
        const closing = /^[ \t]*([}\]])?/.exec(value.slice(end));
        if (opens && closing[1] === (opening === "{" ? "}" : "]")) {
            // Drop the space before the closing bracket too.
            end += closing[0].length - 1;
            text += `\n${indent}`;
        }
        event.preventDefault();
        replaceText(field, start, end, text);
        field.setSelectionRange(caret, caret);
    }

    // ---- Colours -----------------------------------------------------------------------------------------------

    // Copied from the textarea, so the coloured copy wraps exactly as the textarea does.
    const COPIED_STYLES = [
        "fontFamily",
        "fontSize",
        "fontStyle",
        "fontWeight",
        "fontVariant",
        "fontStretch",
        "fontKerning",
        "fontFeatureSettings",
        "fontVariationSettings",
        "textRendering",
        "hyphens",
        "lineHeight",
        "letterSpacing",
        "wordSpacing",
        "tabSize",
        "textIndent",
        "textTransform",
        "whiteSpace",
        "overflowWrap",
        "wordBreak",
        "direction",
        "paddingTop",
        "paddingRight",
        "paddingBottom",
        "paddingLeft",
    ];

    // Put a coloured copy of the field's text behind it, or return null when the page lacks the stylesheet.
    function colourer(field) {
        const wrapper = document.createElement("div");
        wrapper.className = `${PREFIX}-editor`;
        field.before(wrapper);
        if (getComputedStyle(wrapper).position !== "relative") {
            wrapper.remove();
            return null;
        }
        const copy = document.createElement("pre");
        copy.className = `${PREFIX}-highlight`;
        copy.setAttribute("aria-hidden", "true");
        wrapper.append(copy, field);
        wrapper.classList.add(`${PREFIX}-coloured`);
        let on = true;

        const layOut = () => {
            const style = getComputedStyle(field);
            for (const name of COPIED_STYLES) {
                copy.style[name] = style[name];
            }
            copy.style.boxSizing = "border-box";
            copy.style.borderWidth = "0";
            copy.style.left = `${field.offsetLeft + field.clientLeft}px`;
            copy.style.top = `${field.offsetTop + field.clientTop}px`;
            copy.style.width = `${field.clientWidth}px`;
            copy.style.height = `${field.clientHeight}px`;
            copy.scrollTop = field.scrollTop;
            copy.scrollLeft = field.scrollLeft;
        };
        // If the copy can't take the textarea's text styles (a stylesheet overrides them), or ends up a different
        // height once the textarea scrolls, its colours would sit on the wrong text: show the plain textarea instead,
        // for good.
        const linesUp = () => {
            const fieldStyle = getComputedStyle(field);
            const copyStyle = getComputedStyle(copy);
            if (!COPIED_STYLES.every((name) => fieldStyle[name] === copyStyle[name])) {
                return false;
            }
            return field.scrollHeight <= field.clientHeight || Math.abs(copy.scrollHeight - field.scrollHeight) <= 1;
        };
        const checkAlignment = () => {
            if (on && !linesUp()) {
                on = false;
                wrapper.classList.remove(`${PREFIX}-coloured`);
                copy.hidden = true;
            }
        };
        const paint = (tokens, problem) => {
            if (!on) {
                return;
            }
            const spans = tokens.map((token) => {
                if (token.kind === "space") {
                    return token.text;
                }
                const span = document.createElement("span");
                const kind = token.kind === "invalid" ? "invalid" : token.kind;
                span.className = `${PREFIX}-${kind}`;
                if (problem?.token === token) {
                    span.classList.add(`${PREFIX}-invalid`);
                }
                span.textContent = token.text;
                return span;
            });
            // An empty last line has no height in the copy, as it does in the textarea, without something on it.
            copy.replaceChildren(...spans, "​");
            layOut();
            checkAlignment();
        };

        field.addEventListener("scroll", () => {
            copy.scrollTop = field.scrollTop;
            copy.scrollLeft = field.scrollLeft;
        });
        new ResizeObserver(() => {
            if (on) {
                layOut();
                checkAlignment();
            }
        }).observe(field);
        document.fonts?.ready.then(() => {
            if (on) {
                layOut();
                checkAlignment();
            }
        });
        return paint;
    }

    // ---- The editor --------------------------------------------------------------------------------------------

    function lineAndColumn(text, offset) {
        const before = text.slice(0, offset);
        const line = before.split("\n").length;
        return { line, column: offset - before.lastIndexOf("\n") };
    }

    function setUp(field) {
        const tools = document.createElement("div");
        tools.className = `${PREFIX}-tools`;
        const formatLink = document.createElement("a");
        formatLink.href = "#";
        formatLink.role = "button";
        formatLink.textContent = "Format";
        const status = document.createElement("span");
        status.className = `${PREFIX}-status`;
        status.id = `${field.id || field.name}_json_status`;
        status.setAttribute("aria-live", "polite");
        tools.append(formatLink, " ", status);

        const paint = colourer(field);
        (field.closest(`.${PREFIX}-editor`) ?? field).after(tools);
        const describedBy = field.getAttribute("aria-describedby");
        field.setAttribute("aria-describedby", describedBy ? `${describedBy} ${status.id}` : status.id);

        let tokens = [];
        let problem = null;
        const update = () => {
            const text = field.value;
            tokens = tokenize(text);
            problem = check(tokens);
            if (!text.trim()) {
                status.textContent = "";
            } else if (!problem) {
                status.textContent = "Valid JSON.";
            } else if (problem.plain) {
                status.textContent = problem.message;
            } else {
                const at = lineAndColumn(text, problem.token ? problem.token.start : text.length);
                status.textContent = `Invalid JSON at line ${at.line}, column ${at.column}: ${problem.message}.`;
            }
            status.classList.toggle(`${PREFIX}-has-error`, Boolean(problem));
            paint?.(tokens, problem);
        };

        formatLink.addEventListener("click", (event) => {
            event.preventDefault();
            if (!field.value.trim() || (problem && problem.plain)) {
                return;
            }
            if (problem) {
                const at = problem.token ? problem.token.start : field.value.length;
                field.focus();
                field.setSelectionRange(at, at);
                return;
            }
            const formatted = format(tokens);
            if (formatted !== field.value) {
                replaceText(field, 0, field.value.length, formatted);
            }
        });
        field.addEventListener("keydown", newLine);
        field.addEventListener("input", update);
        update();
    }

    document.addEventListener("DOMContentLoaded", () => {
        for (const field of document.querySelectorAll(FIELD)) {
            setUp(field);
        }
    });
}
