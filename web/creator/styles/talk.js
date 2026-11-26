// What the chat room and Stagehand's window draw the same way (`talk.js`).
//
// Each conversation wears its own classes on a shared row (`mmc-ch-*`,
// `mmc-sh-*`), so only what neither of them styles is here.

export const css = `
.mmc-talk-doors { display: flex; flex-wrap: wrap; gap: 8px; }
.mmc-talk-failtext { white-space: pre-wrap; overflow-wrap: anywhere; }

/* A model's reply drawn from its markdown (markdown.js). The reply's own row
   says how big and what colour its words are; this only spaces the blocks and
   draws the few that are not words. Blocks are spaced by the gap between them,
   never by a margin on the first or the last, so a one-line reply is as tall
   as the text was. */
.mmc-md { white-space: normal; overflow-wrap: anywhere; }
.mmc-md :where(p, ul, ol, pre, blockquote, hr, .mmc-md-table) { margin-top: 0; margin-bottom: 0; }
.mmc-md > * + *, .mmc-md blockquote > * + * { margin-top: .6em; }
.mmc-md li > * + * { margin-top: .25em; }
.mmc-md .mmc-md-h { font-weight: 600; color: var(--mmc-strong); line-height: 1.3; }
.mmc-md .mmc-md-h1 { font-size: 1.22em; }
.mmc-md .mmc-md-h2 { font-size: 1.12em; }
.mmc-md .mmc-md-h3 { font-size: 1.04em; }
.mmc-md .mmc-md-h4 { font-size: 1em; color: var(--mmc-text); }
.mmc-md > .mmc-md-h:not(:first-child) { margin-top: 1em; }
.mmc-md strong { font-weight: 600; color: var(--mmc-strong); }
.mmc-md s { opacity: .7; }
.mmc-md a { color: var(--mmc-accent); text-decoration: underline; text-decoration-color: color-mix(in srgb, currentColor 40%, transparent); text-underline-offset: 2px; }
.mmc-md a:hover { text-decoration-color: currentColor; }
.mmc-md ul, .mmc-md ol { padding-left: 1.4em; }
.mmc-md li + li { margin-top: .25em; }
.mmc-md li::marker { color: var(--mmc-dim); }
.mmc-md li.mmc-md-task { list-style: none; position: relative; }
.mmc-md .mmc-md-box { position: absolute; left: -1.35em; top: .2em; width: .95em; height: .95em; box-sizing: border-box;
  border: 1px solid var(--mmc-dim); border-radius: calc(3px * var(--mmc-round));
  display: flex; align-items: center; justify-content: center; font-size: .7em; line-height: 1; }
.mmc-md .mmc-md-task.done .mmc-md-box { background: var(--mmc-accent); border-color: var(--mmc-accent); color: var(--mmc-on-accent); }
.mmc-md .mmc-md-task.done { color: var(--mmc-dim); }
.mmc-md code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: .88em;
  padding: .1em .35em; border-radius: calc(4px * var(--mmc-round)); background: var(--mmc-tint); border: 1px solid var(--mmc-line); }
.mmc-md pre { padding: 8px 10px; border-radius: calc(8px * var(--mmc-round)); background: var(--mmc-tint); border: 1px solid var(--mmc-line);
  overflow-x: auto; white-space: pre; user-select: text; -webkit-user-select: text; }
.mmc-md pre code { padding: 0; border: 0; background: none; font-size: .86em; line-height: 1.5; }
.mmc-md blockquote { margin-left: 0; margin-right: 0; padding-left: 10px; border-left: 3px solid var(--mmc-line); color: var(--mmc-dim); }
.mmc-md hr { border: 0; border-top: 1px solid var(--mmc-line); }
.mmc-md > hr + *, .mmc-md > * + hr { margin-top: .9em; }
.mmc-md .mmc-md-table { overflow-x: auto; }
.mmc-md table { border-collapse: collapse; font-size: .94em; }
.mmc-md th, .mmc-md td { padding: 4px 10px; border: 1px solid var(--mmc-line); text-align: left; vertical-align: top; }
.mmc-md th { font-weight: 600; color: var(--mmc-strong); background: var(--mmc-tint); }
`;
