// What every conversation with a model shares: the chat room (`chat.js`) and
// Stagehand's window (`stagehandwindow.js`).
//
// The two are different conversations. The room's model answers a turn with
// one action and the server renders it; Stagehand's model calls tools, one
// exchange after another, and the browser runs them on the piece. What a line
// of each *is* stays with its owner: a render card is the room's, a tool's
// line is Stagehand's. What is the same in both is here, once:
//
// - **Asking.** `asking` is the one way a model is asked. A failure that
//   passes by itself (a server that did not answer, a reply that could not be
//   read) is asked again before anybody is told; `failureOf` is the one place
//   that reads a failure for which kind it is.
// - **The transcript.** `Transcript` draws a list of lines into a log, keeps
//   the ones that did not change, keeps the caret where it was and keeps the
//   newest line in view.
// - **A failure's line.** `failRow` is what a failed message looks like and the
//   doors it has: ask again without typing it again, or start over.
// - **A person's pictures.** `scaled`, `isPicture` and `enlarge`.
//
// A third conversation starts here: hold its lines, draw them through a
// `Transcript`, and ask through `asking`.

import { el } from "./dom.js";
import { t } from "./i18n.js";

// ---- asking -----------------------------------------------------------------------

/** How often a model is asked before its failure is said: once, and twice more. */
export const TRIES = 3;

/** How long is waited before asking again, in milliseconds, by which time it is. */
const PAUSES = [1200, 3500];

// What a failure says when it passes by itself. A server's own status, a
// connection, a reply nothing could be read from: the same question may well be
// answered the second time. The sentences are the server half's own
// (`refine_remote._request`, `stagehand.read`, `jobs`).
const PASSES = /answered (5\d\d|408|409|425|429)\b|could not reach|reply could not be read|timed? ?out|failed to fetch|networkerror|network error|load failed|econn|socket hang up|overloaded|rate limit|still working on this conversation|your reply was empty|json in your reply could not be read|has to hold "calls"|has to be an object with "tool"|the job failed|the server queued nothing/i;

// What asking again cannot change: the conversation no longer fits the model.
const TOO_LONG = /context|too long|too many tokens|exceed/i;

/**
 * What kind of failure this is. -> `{kind, text, again}`.
 *
 * `kind` is "stopped" (somebody ended it, and that is not a failure),
 * "limit" (Stagehand's own ceiling on exchanges), "long" (the conversation
 * outgrew the model, so only a new one helps), "passing" (worth asking again
 * unasked) or "other" (said as it is; a person may still ask again).
 * `again` is whether `asking` asks again by itself.
 */
export function failureOf(error) {
  const text = String(error?.message ?? error ?? "");
  if (error?.stopped || error?.cancelled || error?.name === "AbortError") return { kind: "stopped", text, again: false };
  if (error?.limit) return { kind: "limit", text, again: false };
  if (TOO_LONG.test(text)) return { kind: "long", text, again: false };
  if (PASSES.test(text)) return { kind: "passing", text, again: true };
  return { kind: "other", text, again: false };
}

/** Wait, unless `signal` ends the waiting first. */
function pause(ms, signal) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) { reject(signal.reason); return; }
    const done = () => { signal?.removeEventListener("abort", stopped); resolve(); };
    const timer = setTimeout(done, ms);
    const stopped = () => { clearTimeout(timer); reject(signal.reason); };
    signal?.addEventListener("abort", stopped, { once: true });
  });
}

/**
 * Ask a model, and ask again where the failure is one that passes.
 *
 * `ask()` is one whole attempt and must be safe to make twice: it sends what
 * it sent before. `onAgain({attempt, of, text})` is told before each further
 * attempt, so the wait can say what it is waiting for; `signal` ends the
 * waiting between attempts the way it ends an attempt. The last failure is
 * thrown as it was.
 */
export async function asking(ask, { signal = null, tries = TRIES, pauses = PAUSES, onAgain = null } = {}) {
  for (let attempt = 1; ; attempt++) {
    try {
      return await ask(attempt);
    } catch (error) {
      if (attempt >= tries || signal?.aborted || !failureOf(error).again) throw error;
      onAgain?.({ attempt: attempt + 1, of: tries, text: String(error?.message ?? error) });
      await pause(pauses[Math.min(attempt, pauses.length) - 1] ?? 0, signal);
    }
  }
}

/** What the wait says while a model is asked again. */
export function againWords({ attempt, of }) {
  return t("No answer. Asking again, {attempt} of {of}", { attempt, of });
}

// ---- the transcript ---------------------------------------------------------------

/**
 * A conversation's lines, drawn into its log.
 *
 * `show(rows)` takes the whole conversation each time and does as little as
 * it can with it. A row is a node, drawn by the caller and put in as it is, or
 * `{of, key, draw}`: `of` is the thing the row is of (a message, an item),
 * `key` says what it looks like now, and `draw()` makes its node or nodes. A
 * row whose key has not changed keeps the nodes it has, so a picture is not
 * loaded again and a field being typed into is not replaced under the caret.
 */
export class Transcript {
  /** `near`: how far from the end still counts as reading the newest line. */
  constructor(log, { near = 60 } = {}) {
    this.log = log;
    this.near = near;
    this.kept = new Map();
  }

  /** The nodes a thing is drawn as now, or none. */
  nodesOf(of) {
    return this.kept.get(of)?.nodes ?? [];
  }

  /** Draw it afresh next time, whatever its key says. */
  forget(of) {
    this.kept.delete(of);
  }

  /** Draw what changed and say what each row is drawn as: one list of nodes
   *  for each row given, in order. Nothing is put in the log yet, for a
   *  caller that has rows of its own to put between them (`put`). */
  settle(rows) {
    const seen = new Set();
    const drawn = rows.filter(Boolean).map((row) => {
      if (!("draw" in row)) return [row];
      seen.add(row.of);
      let kept = this.kept.get(row.of);
      if (!kept || kept.key !== row.key) {
        kept = { key: row.key, nodes: [row.draw()].flat().filter(Boolean) };
        this.kept.set(row.of, kept);
      }
      return kept.nodes;
    });
    for (const of of this.kept.keys()) if (!seen.has(of)) this.kept.delete(of);
    return drawn;
  }

  /** `settle` and `put` in one, for a conversation that is only its rows. */
  show(rows, options) {
    return this.put(this.settle(rows).flat(), options);
  }

  /** Put these nodes in the log, as the whole of it. `follow`: "near" keeps
   *  the newest line in view for somebody who was reading it, "always" for
   *  everybody. */
  put(nodes, { follow = "near" } = {}) {
    const log = this.log;
    const reading = follow === "always" || log.scrollHeight - log.scrollTop - log.clientHeight < this.near;
    const now = [...log.children];
    if (now.length !== nodes.length || now.some((node, at) => node !== nodes[at])) {
      // Putting kept rows back takes the focus out of the one a person is in.
      const focused = log.contains(document.activeElement) ? document.activeElement : null;
      const caret = focused && typeof focused.selectionStart === "number" ? [focused.selectionStart, focused.selectionEnd] : null;
      log.replaceChildren(...nodes);
      if (focused?.isConnected && document.activeElement !== focused) {
        focused.focus({ preventScroll: true });
        if (caret) focused.setSelectionRange(...caret);
      }
    }
    if (reading) log.scrollTop = log.scrollHeight;
    return nodes;
  }
}

// ---- a failure's line -------------------------------------------------------------

/**
 * A message that failed, with what can be done about it.
 *
 * `again` asks the same thing again and `restart` starts a new conversation;
 * each is a door only where it is given. `more` are doors of the caller's
 * own. Nothing a model or a server wrote is drawn as markup. `cls` is the
 * owner's class for the row, `words` for what it says and `door` for a door,
 * since each conversation wears its own.
 */
export function failRow({ text, again = null, againWords = t("Try again"), againTitle = t("Ask the same thing again. Nothing is typed again."),
  restart = null, cls = "", door = "", words = "", more = [] }) {
  const button = (words, title, onclick) => el("button", { class: `${door} mmc-talk-door`.trim(), text: words, title, onclick });
  const doors = [
    again ? button(againWords, againTitle, again) : null,
    restart ? button(t("New conversation"), t("Forget what was said. The piece is not changed."), restart) : null,
    ...more,
  ].filter(Boolean);
  return el("div", { class: `${cls} mmc-talk-fail`.trim(), role: "alert" }, [
    el("div", { class: `${words} mmc-talk-failtext`.trim(), text }),
    doors.length ? el("div", { class: "mmc-talk-doors" }, doors) : null,
  ].filter(Boolean));
}

// ---- a person's pictures ----------------------------------------------------------

/** The long edge a person's picture is scaled to before it is sent. */
export const PICTURE_EDGE = 1024;

export const isPicture = (file) => /^image\//.test(file?.type ?? "");

/** A picture file -> a `data:` URL, scaled so its long edge is at most `PICTURE_EDGE`. */
export async function scaled(file) {
  const bitmap = await createImageBitmap(file);
  const k = Math.min(1, PICTURE_EDGE / Math.max(bitmap.width, bitmap.height));
  const canvas = Object.assign(document.createElement("canvas"), { width: Math.max(1, Math.round(bitmap.width * k)), height: Math.max(1, Math.round(bitmap.height * k)) });
  canvas.getContext("2d").drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close?.();
  return canvas.toDataURL("image/jpeg", 0.9);
}

/** A picture at its full size over `host`, closed by a click or Escape. */
export function enlarge(url, host, cls = "") {
  const close = () => zoom.remove();
  const zoom = el("button", { class: `${cls} mmc-talk-zoom`.trim(), "aria-label": t("Close the picture"), onclick: close,
    onkeydown: (event) => { if (event.key === "Escape") { event.stopPropagation(); close(); } } }, [el("img", { src: url, alt: "" })]);
  host.append(zoom);
  zoom.focus();
  return zoom;
}
