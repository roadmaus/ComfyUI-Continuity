// What a model writes, drawn as the markdown it is written in.
//
// Chat models answer in markdown whether they are asked to or not, and drawn as
// text a reply is a wall of `**`, `- ` and `###`. This reads the part of it
// models actually write — paragraphs, headings, lists (nested, numbered, with
// checkboxes), quotes, fenced code, pipe tables, rules, emphasis, inline code
// and links — and builds the elements for it by hand.
//
// Nothing is ever parsed as HTML. The text is read into a tree of plain
// objects (`parse`), and the tree is drawn with `el`, whose every word goes in
// as textContent; a `<script>` in a reply stays the eight characters it was. A
// link is kept only when it is http(s), opens in a new tab and carries no
// referrer, and an image is drawn as a link to it, never fetched: a reply does
// not get to make the browser ask anybody for anything.
//
// Two splits so the reading can be tested without a DOM: `parse` is pure, and
// `markdown` only walks what it returns.

import { el } from "./dom.js";

const FENCE = /^ {0,3}(`{3,}|~{3,})\s*([^\s`]*)[^`]*$/;
const HEADING = /^ {0,3}(#{1,6})(?:[ \t]+(.*?))?(?:[ \t]+#+)?[ \t]*$/;
const RULE = /^ {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$/;
const QUOTE = /^ {0,3}> ?(.*)$/;
const ITEM = /^( {0,12})([-*+]|\d{1,9}[.)])(?:[ \t]+(.*))?$/;
const DIVIDER = /^ {0,3}\|?[ \t]*:?-+:?[ \t]*(?:\|[ \t]*:?-+:?[ \t]*)*\|?[ \t]*$/;
// Deeper than this and a reply is not markdown any more, it is a trap.
const DEEPEST = 12;

/** The text as blocks: `{type, ...}` objects, inline runs already read. */
export function parse(text) {
  const lines = String(text ?? "").replace(/\r\n?/g, "\n").replace(/\t/g, "    ").split("\n");
  return blocks(lines, 0);
}

const isBlank = (line) => !line.trim();

/** Whether a line opens a block of its own, and so ends a paragraph. */
function opens(line, next) {
  return FENCE.test(line) || HEADING.test(line) || RULE.test(line) || QUOTE.test(line)
    || startsItem(line) || startsTable(line, next);
}

function startsItem(line) {
  const match = ITEM.exec(line);
  // A bare "1." or "-" is a list item only with something after it; a line of
  // nothing but a dash is far more often a model's divider than an empty item.
  return !!match && match[1].length <= 3 && match[3] !== undefined && match[3].trim() !== "";
}

function startsTable(line, next) {
  return next !== undefined && line.includes("|") && DIVIDER.test(next) && next.includes("-")
    && (next.includes("|") || cells(line).length > 1);
}

function blocks(lines, depth) {
  const out = [];
  let at = 0;
  while (at < lines.length) {
    const line = lines[at];
    if (isBlank(line)) { at++; continue; }

    const fence = FENCE.exec(line);
    if (fence) {
      const mark = fence[1];
      const body = [];
      at++;
      while (at < lines.length && !new RegExp(`^ {0,3}${mark[0] === "`" ? "`" : "~"}{${mark.length},}\\s*$`).test(lines[at])) {
        body.push(lines[at++]);
      }
      at++;   // the closing fence, or past the end when a reply stopped inside one
      out.push({ type: "code", lang: fence[2] || "", text: body.join("\n") });
      continue;
    }

    const heading = HEADING.exec(line);
    if (heading) {
      out.push({ type: "heading", level: heading[1].length, inline: inline(heading[2] ?? "") });
      at++;
      continue;
    }

    if (RULE.test(line)) { out.push({ type: "rule" }); at++; continue; }

    if (QUOTE.test(line)) {
      const inner = [];
      while (at < lines.length && !isBlank(lines[at])) {
        const quoted = QUOTE.exec(lines[at]);
        // A line under a quote without its ">" still belongs to it, unless it
        // opens something of its own.
        if (!quoted && opens(lines[at], lines[at + 1])) break;
        inner.push(quoted ? quoted[1] : lines[at]);
        at++;
      }
      out.push({ type: "quote", blocks: depth < DEEPEST ? blocks(inner, depth + 1) : [paragraph(inner)] });
      continue;
    }

    if (startsItem(line)) {
      const [list, next] = readList(lines, at, depth);
      out.push(list);
      at = next;
      continue;
    }

    if (startsTable(line, lines[at + 1])) {
      const head = cells(line);
      const align = cells(lines[at + 1]).map((cell) =>
        cell.startsWith(":") && cell.endsWith(":") ? "center" : cell.endsWith(":") ? "right" : cell.startsWith(":") ? "left" : "");
      const rows = [];
      at += 2;
      while (at < lines.length && !isBlank(lines[at]) && lines[at].includes("|")) {
        rows.push(cells(lines[at++]));
      }
      const width = head.length;
      const fit = (row) => Array.from({ length: width }, (_, i) => inline(row[i] ?? ""));
      out.push({ type: "table", align: align.slice(0, width), head: fit(head), rows: rows.map(fit) });
      continue;
    }

    const words = [line];
    at++;
    while (at < lines.length && !isBlank(lines[at]) && !opens(lines[at], lines[at + 1])) words.push(lines[at++]);
    out.push(paragraph(words));
  }
  return out;
}

function paragraph(lines) {
  return { type: "paragraph", inline: inline(lines.map((line) => line.trim()).join("\n")) };
}

/** One list from `start`, and the line after it. Items of the other kind
 *  (a number after bullets) end it, as they do in every renderer. */
function readList(lines, start, depth) {
  const first = ITEM.exec(lines[start]);
  const ordered = /\d/.test(first[2]);
  const base = first[1].length;
  const items = [];
  let at = start;
  while (at < lines.length) {
    const match = ITEM.exec(lines[at]);
    if (!match || match[1].length !== base || /\d/.test(match[2]) !== ordered || match[3] === undefined) break;
    // What the item's own lines are measured against: past the marker, but a
    // model that indents its sub-list by two under "1." still means it.
    const inside = Math.min(base + match[2].length + 1, base + 2);
    const body = [match[3]];
    at++;
    while (at < lines.length) {
      const line = lines[at];
      if (isBlank(line)) {
        // A blank line keeps the item going only when what follows is still
        // indented under it.
        let ahead = at;
        while (ahead < lines.length && isBlank(lines[ahead])) ahead++;
        if (ahead < lines.length && indent(lines[ahead]) >= inside) {
          for (; at < ahead; at++) body.push("");
          continue;
        }
        break;
      }
      if (indent(line) >= inside) { body.push(line.slice(inside)); at++; continue; }
      // A line that is not indented and opens nothing carries the item's text on.
      if (!opens(line, lines[at + 1]) && !isBlank(body[body.length - 1])) { body.push(line.trim()); at++; continue; }
      break;
    }
    let check = null;
    const box = /^\[([ xX])\][ \t]+/.exec(body[0]);
    if (box) { check = box[1] !== " "; body[0] = body[0].slice(box[0].length); }
    items.push({ check, blocks: depth < DEEPEST ? blocks(body, depth + 1) : [paragraph(body)] });
    // A blank line between items is not the end of the list.
    let ahead = at;
    while (ahead < lines.length && isBlank(lines[ahead])) ahead++;
    if (ahead > at && ahead < lines.length) {
      const next = ITEM.exec(lines[ahead]);
      if (next && next[1].length === base && /\d/.test(next[2]) === ordered && next[3] !== undefined) at = ahead;
    }
  }
  return [{ type: "list", ordered, start: ordered ? parseInt(first[2], 10) : 1, items }, at];
}

function indent(line) {
  return line.length - line.trimStart().length;
}

/** A table row's cells, without the outer pipes; `\|` is a pipe in a cell. */
function cells(line) {
  let row = line.trim();
  if (row.startsWith("|")) row = row.slice(1);
  if (row.endsWith("|") && !row.endsWith("\\|")) row = row.slice(0, -1);
  const out = [];
  let cell = "";
  let code = false;
  for (let i = 0; i < row.length; i++) {
    const ch = row[i];
    if (ch === "\\" && row[i + 1] === "|") { cell += "|"; i++; continue; }
    if (ch === "`") code = !code;
    if (ch === "|" && !code) { out.push(cell.trim()); cell = ""; continue; }
    cell += ch;
  }
  out.push(cell.trim());
  return out;
}

const PUNCTUATION = /[!-/:-@[-`{-~]/;
const BARE_LINK = /^https?:\/\/[^\s<>"]+/;

/**
 * A run of text as inline pieces: a string, or `{type: "strong" | "em" |
 * "strike", inline}`, `{type: "code", text}`, `{type: "link", href, inline}`,
 * `{type: "break"}`. A link whose address is not http(s) is its words alone.
 */
export function inline(text, depth = 0) {
  const out = [];
  let plain = "";
  const flush = () => { if (plain) { out.push(plain); plain = ""; } };
  const push = (piece) => { flush(); out.push(piece); };
  const deeper = (inner) => (depth < DEEPEST ? inline(inner, depth + 1) : [inner]);
  let at = 0;
  while (at < text.length) {
    const ch = text[at];
    const rest = text.slice(at);

    if (ch === "\\" && at + 1 < text.length && PUNCTUATION.test(text[at + 1])) {
      plain += text[at + 1];
      at += 2;
      continue;
    }
    if (ch === "\n") { push({ type: "break" }); at++; continue; }

    if (ch === "`") {
      const run = /^`+/.exec(rest)[0];
      const close = text.indexOf(run, at + run.length);
      // The closing run has to be exactly as long, not part of a longer one.
      let end = close;
      while (end !== -1 && text[end + run.length] === "`") {
        let past = end;
        while (text[past] === "`") past++;
        end = text.indexOf(run, past);
      }
      if (end !== -1) {
        let code = text.slice(at + run.length, end).replace(/\n/g, " ");
        if (code.length > 2 && code.startsWith(" ") && code.endsWith(" ")) code = code.slice(1, -1);
        push({ type: "code", text: code });
        at = end + run.length;
        continue;
      }
      plain += run;
      at += run.length;
      continue;
    }

    const br = /^<br\s*\/?>/i.exec(rest);
    if (br) { push({ type: "break" }); at += br[0].length; continue; }

    if (ch === "<") {
      const auto = /^<(https?:\/\/[^\s<>]+)>/.exec(rest);
      if (auto) { push({ type: "link", href: auto[1], inline: [auto[1]] }); at += auto[0].length; continue; }
    }

    if (ch === "[" || (ch === "!" && text[at + 1] === "[")) {
      const link = readLink(text, ch === "!" ? at + 1 : at);
      if (link) {
        const words = ch === "!" ? [link.label || link.href] : deeper(link.label);
        if (safe(link.href)) push({ type: "link", href: link.href, inline: words });
        else { flush(); out.push(...words); }
        at = link.end;
        continue;
      }
    }

    if ((ch === "h" || ch === "H") && !/[A-Za-z0-9]/.test(text[at - 1] ?? "")) {
      const bare = BARE_LINK.exec(rest);
      if (bare) {
        const href = trimLink(bare[0]);
        push({ type: "link", href, inline: [href] });
        at += href.length;
        continue;
      }
    }

    if (ch === "*" || ch === "_" || ch === "~") {
      const span = readSpan(text, at, deeper);
      if (span) { plain += span.lead ?? ""; push(span.piece); at = span.end; continue; }
      // A run that closes nothing is just the characters.
      const run = new RegExp(`^\\${ch}+`).exec(rest)[0];
      plain += run;
      at += run.length;
      continue;
    }

    plain += ch;
    at++;
  }
  flush();
  return out;
}

/** `[label](href "title")` from `at`, or null. Brackets and parens nest once. */
function readLink(text, at) {
  let depth = 0;
  let close = -1;
  for (let i = at; i < text.length; i++) {
    if (text[i] === "\\") { i++; continue; }
    if (text[i] === "[") depth++;
    else if (text[i] === "]" && --depth === 0) { close = i; break; }
  }
  if (close === -1 || text[close + 1] !== "(") return null;
  let parens = 0;
  let end = -1;
  for (let i = close + 2; i < text.length; i++) {
    if (text[i] === "\n") return null;
    if (text[i] === "(") parens++;
    else if (text[i] === ")") { if (parens === 0) { end = i; break; } parens--; }
  }
  if (end === -1) return null;
  let target = text.slice(close + 2, end).trim();
  target = target.replace(/\s+(?:"[^"]*"|'[^']*')$/, "");
  if (target.startsWith("<") && target.endsWith(">")) target = target.slice(1, -1);
  return { label: text.slice(at + 1, close), href: target, end: end + 1 };
}

/** A bare address without the sentence's punctuation after it. A closing paren
 *  stays when the address opened one, as a wiki link does. */
function trimLink(href) {
  for (;;) {
    const last = href[href.length - 1];
    if (/[.,;:!?'"*_]/.test(last)) { href = href.slice(0, -1); continue; }
    if (last === ")" && (href.match(/\(/g)?.length ?? 0) < (href.match(/\)/g)?.length ?? 0)) { href = href.slice(0, -1); continue; }
    return href;
  }
}

/** Only addresses a browser can open as a page, never `javascript:` or `data:`. */
export function safe(href) {
  try {
    const url = new URL(href);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}

/**
 * Emphasis from `at`: `**strong**`, `*em*`, `***both***`, `__strong__`,
 * `_em_` and `~~struck~~`. Underscores inside a word are the word's — LoRA
 * and file names are full of them — and a delimiter with a space on its inner
 * side opens or closes nothing, so `2 * 3 * 4` stays arithmetic.
 */
function readSpan(text, at, deeper) {
  const ch = text[at];
  const run = new RegExp(`^\\${ch}+`).exec(text.slice(at))[0];
  if (ch === "~") return run.length === 2 ? spanOf(text, at, 2, deeper) : null;
  // `***a**` is not `***` closed: it is `**` closing, with a `*` in front.
  for (let size = Math.min(run.length, 3); size >= 1; size--) {
    const span = spanOf(text, at + run.length - size, size, deeper);
    if (span) return run.length > size ? { lead: ch.repeat(run.length - size), ...span } : span;
  }
  return null;
}

function spanOf(text, at, size, deeper) {
  const ch = text[at];
  const after = text[at + size];
  if (after === undefined || /\s/.test(after)) return null;
  if (ch === "_" && /[\p{L}\p{N}]/u.test(text[at - 1] ?? "")) return null;
  const mark = ch.repeat(size);
  for (let close = text.indexOf(mark, at + size + 1); close !== -1; close = text.indexOf(mark, close + 1)) {
    if (/\s/.test(text[close - 1])) continue;
    // Part of a longer run is not this one closing: `**a*` is not `*` closing.
    if (text[close + size] === ch) { while (text[close + size] === ch) close++; continue; }
    if (ch === "_" && /[\p{L}\p{N}]/u.test(text[close + size] ?? "")) continue;
    if (text.slice(at + size, close).includes("\n\n")) return null;
    const inner = deeper(text.slice(at + size, close));
    const piece = ch === "~" ? { type: "strike", inline: inner }
      : size === 3 ? { type: "strong", inline: [{ type: "em", inline: inner }] }
      : { type: size === 2 ? "strong" : "em", inline: inner };
    return { piece, end: close + size };
  }
  return null;
}

const INLINE_TAG = { strong: "strong", em: "em", strike: "s" };

function drawInline(pieces) {
  return pieces.map((piece) => {
    if (typeof piece === "string") return document.createTextNode(piece);
    if (piece.type === "break") return el("br");
    if (piece.type === "code") return el("code", { text: piece.text });
    if (piece.type === "link") {
      return el("a", { href: piece.href, target: "_blank", rel: "noopener noreferrer", title: piece.href },
        drawInline(piece.inline));
    }
    return el(INLINE_TAG[piece.type], {}, drawInline(piece.inline));
  });
}

function drawBlock(block) {
  switch (block.type) {
    case "heading": return el("p", { class: `mmc-md-h mmc-md-h${Math.min(block.level, 4)}` }, drawInline(block.inline));
    case "rule": return el("hr");
    case "code": return el("pre", { "data-lang": block.lang || null }, [el("code", { text: block.text })]);
    case "quote": return el("blockquote", {}, block.blocks.map(drawBlock));
    case "list": {
      const items = block.items.map((item) => {
        // An item that is one paragraph is its words, not a <p> in an <li>.
        const body = item.blocks.length === 1 && item.blocks[0].type === "paragraph"
          ? drawInline(item.blocks[0].inline) : item.blocks.map(drawBlock);
        if (item.check === null) return el("li", {}, body);
        return el("li", { class: `mmc-md-task${item.check ? " done" : ""}` }, [
          el("span", { class: "mmc-md-box", "aria-hidden": "true", text: item.check ? "✓" : "" }), ...body]);
      });
      return block.ordered
        ? el("ol", { start: block.start !== 1 ? String(block.start) : null }, items)
        : el("ul", {}, items);
    }
    case "table": {
      const cell = (tag, pieces, i) => el(tag, { style: block.align[i] ? { textAlign: block.align[i] } : {} }, drawInline(pieces));
      return el("div", { class: "mmc-md-table" }, [el("table", {}, [
        el("thead", {}, [el("tr", {}, block.head.map((pieces, i) => cell("th", pieces, i)))]),
        el("tbody", {}, block.rows.map((row) => el("tr", {}, row.map((pieces, i) => cell("td", pieces, i))))),
      ])]);
    }
    default: return el("p", {}, drawInline(block.inline));
  }
}

/** The elements for `text`, to go inside an element with the `mmc-md` class. */
export function markdown(text) {
  return parse(text).map(drawBlock);
}
