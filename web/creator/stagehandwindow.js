// Stagehand's window in the blockout bench, and the conversation it shows.
//
// The agent itself is `stagehand.js`: a conversation with the refiner's model
// and the tools it stages a piece with. This file is what a person sees of it.
// A `Talk` is one conversation about one piece. It lives for as long as the
// page does, so closing the bench and opening it again finds the conversation
// there, and an agent still working. A `StagehandWindow` is the window a bench
// opens over its inspector: header, transcript, composer.
//
// The piece is changed the way a hand changes it: each call lands through the
// bench's own commit (`Reel.land`) and is drawn before the next is answered,
// editing waits while the agent works, and a whole message is one step back.

import { el } from "./dom.js";
import { t } from "./i18n.js";
import * as S from "./state.js";
import { syncStagingWords } from "./blockout.js";
import { Stagehand, refinerRequest, MOST_PICTURES } from "./stagehand.js";
import { PromptBox } from "./prompt.js";
import { viewUrl } from "./api.js";
import { remoteStatus, openSettings as openRefinerSettings } from "./refine.js";

/** The long edge a person's picture is scaled to before it is sent. */
export const PICTURE_EDGE = 1024;

const TALKS = new WeakMap();

/** The conversation about this piece: the one there is, or a new one. */
export function talkOf(timeline) {
  if (!TALKS.has(timeline)) TALKS.set(timeline, new Talk(timeline));
  return TALKS.get(timeline);
}

// ---- what a call is called ------------------------------------------------------

const count = (content, word) => (typeof content === "string" ? content : "").split("\n").filter((line) => line.startsWith(word)).length;

/** What the agent is doing, for the pill on the glass, read off the call. */
export function statusOf(name, args = {}) {
  const shot = { n: args.shot };
  return ({
    see_scene: () => t("reading the scene"),
    add_objects: () => t("building the set"),
    move_object: () => t("moving #{id}", args),
    resize_object: () => t("resizing #{id}", args),
    describe_object: () => t("describing #{id}", args),
    copy_object: () => t("copying #{id}", args),
    remove_objects: () => t("taking objects out"),
    use_set: () => t("going to the set {name}", { name: args.name ?? "" }),
    look_overview: () => t("looking at the set"),
    look_from: () => t("looking at the set"),
    look_through_camera: () => t("looking through the camera of shot {n}", shot),
    add_cast: () => t("adding to the cast"),
    write_film_text: () => t("writing the scene"),
    add_shot: () => t("adding a shot"),
    change_shot: () => t("changing shot {n}", shot),
    remove_shot: () => t("removing shot {n}", shot),
    move_camera: () => t("placing the camera of shot {n}", shot),
    keep_camera_on: () => t("turning the camera of shot {n}", shot),
    shake_camera: () => t("shaking the camera of shot {n}", shot),
    walk: () => t("moving #{id} through shot {n}", { id: args.id, n: args.shot }),
  }[name] ?? (() => t("working")))();
}

/** What a call did, as one quiet line in the bench's vocabulary. */
export function lineOf(name, args = {}, content = "", set = "") {
  const shot = { n: args.shot };
  const added = count(content, "Added");
  return ({
    see_scene: () => t("Read the scene"),
    add_objects: () => t(added === 1 ? "Added {n} object to the set {set}" : "Added {n} objects to the set {set}", { n: added, set }),
    move_object: () => t("Moved #{id}", args),
    resize_object: () => t("Resized #{id}", args),
    describe_object: () => t("Described #{id}", args),
    copy_object: () => t(added === 1 ? "Copied #{id} once" : "Copied #{id} {n} times", { id: args.id, n: added }),
    remove_objects: () => t((args.ids?.length ?? 0) === 1 ? "Removed {n} object" : "Removed {n} objects", { n: args.ids?.length ?? 0 }),
    use_set: () => t("Went to the set {name}", { name: args.name ?? "" }),
    look_overview: () => (args.above === true ? t("Looked at the set from above") : t("Looked at the whole set")),
    look_from: () => t("Looked at the set from a point"),
    look_through_camera: () => t("Looked through the camera of shot {n}", shot),
    add_cast: () => t("Added @{handle} to the cast", { handle: args.handle ?? "" }),
    write_film_text: () => t("Wrote the film's text"),
    add_shot: () => t("Added a shot, {s} s", { s: args.seconds }),
    change_shot: () => (args.seconds != null && args.text == null ? t("Shot {n} is {s} s now", { n: args.shot, s: args.seconds }) : t("Changed shot {n}", shot)),
    remove_shot: () => t("Removed shot {n}", shot),
    move_camera: () => t("Camera of shot {n}", shot),
    keep_camera_on: () => (args.id === 0 ? t("Camera of shot {n} let go", shot) : t("Camera of shot {n} kept on #{id}", { n: args.shot, id: args.id })),
    shake_camera: () => t("Camera shake of shot {n}: {kind}", { n: args.shot, kind: args.kind ?? "" }),
    walk: () => t("#{id} moves through shot {n}", { id: args.id, n: args.shot }),
  }[name] ?? (() => name))();
}

/** What in the bench a call touched, so the eye can be led there for a moment. */
function touchedBy(name, args = {}, content = "") {
  const text = typeof content === "string" ? content : (content.find?.((part) => part.type === "text")?.text ?? "");
  const ids = [...text.matchAll(/^Added #(\d+)/gm)].map((match) => Number(match[1]));
  if (["move_object", "resize_object", "describe_object"].includes(name)) return { things: [args.id] };
  if (name === "add_objects" || name === "copy_object") return { things: ids };
  if (name === "walk") return { things: [args.id], shot: args.shot };
  if (name === "write_film_text") return { texts: ["look", "sound", "music"].filter((key) => args[key] != null) };
  if (name === "add_shot") return { shot: Number(/^Shot (\d+)/.exec(text)?.[1]) || null };
  if (["change_shot", "move_camera", "keep_camera_on", "shake_camera"].includes(name)) return { shot: args.shot };
  return {};
}

// ---- one conversation -------------------------------------------------------------

export class Talk {
  constructor(timeline) {
    this.timeline = timeline;
    this.bench = null;       // the window on the piece, while one is open
    this.write = null;       // how the node is written when none is
    this.items = [];         // the transcript
    this.working = false;
    this.status = "";
    this.held = null;        // the piece as it stood when the message was sent
    this.draft = "";
    this.pictures = [];      // attached to the message being written, as data URLs
    this.listeners = new Set();
    this.hand = this.fresh();
  }

  fresh() {
    return new Stagehand({
      timeline: () => this.timeline,
      apply: (next) => this.land(next),
      windowState: () => this.bench?.agentSees() ?? "",
      told: (event) => this.heard(event),
    });
  }

  attach(bench, write) {
    this.bench = bench;
    this.write = write ?? this.write;
  }

  detach(bench) {
    if (this.bench === bench) this.bench = null;
  }

  changed() {
    for (const listener of this.listeners) listener();
  }

  /** A changed piece, put where the piece is. Through the bench's commit while
   *  a bench is open; with none open, the same things by hand: the words
   *  follow the staging, a kept take whose shot changed is released, and the
   *  node is written. */
  land(next) {
    if (this.bench) { this.bench.land(next); return; }
    for (const key of Object.keys(this.timeline)) delete this.timeline[key];
    Object.assign(this.timeline, structuredClone(next));
    syncStagingWords(this.timeline);
    S.syncTimeline(this.timeline);
    S.releaseEdited(this.timeline);
    this.write?.();
  }

  /** Forget what was said. The piece is not changed. */
  restart() {
    if (this.working) return;
    this.items = [];
    this.hand = this.fresh();
    this.changed();
  }

  stop() {
    this.hand.stop();
  }

  async send(words, pictures = []) {
    if (this.working || !refinerRequest().model) return;
    this.items.push({ kind: "user", text: words, pictures });
    this.working = true;
    this.status = "";
    this.held = { state: structuredClone(this.timeline), text: S.serializeTimeline(this.timeline) };
    // It starts on the set the glass shows.
    const shown = this.bench?.set()?.id;
    if (shown) this.hand.setId = shown;
    this.bench?.renderLock();
    this.changed();
    try {
      await this.hand.send(words, pictures);
    } catch (exc) {
      if (exc?.stopped) this.items.push({ kind: "note", text: t("Stopped. What was done stays, as one step to undo.") });
      else if (exc?.limit) this.items.push({ kind: "note", text: t("Stagehand stopped after {n} exchanges. Send another message and it goes on.", { n: exc.limit }) });
      else {
        const text = String(exc?.message ?? exc);
        this.items.push({ kind: "error", text, restart: /context|too long|too many tokens|exceed/i.test(text) });
      }
    } finally {
      // However it ended, the bench is the person's again at once, and what
      // the message did is one step back.
      this.working = false;
      this.status = "";
      const held = this.held;
      this.held = null;
      this.bench?.oneStep(held);
      this.bench?.renderLock();
      this.changed();
    }
  }

  heard(event) {
    if (event.kind === "call") {
      this.status = statusOf(event.name, event.args);
      this.bench?.paintAgent();
      return;
    }
    if (event.kind === "note") this.items.push({ kind: "note", text: event.text });
    else if (event.kind === "reply") {
      // Its words, as text: a line of what it is about to do, or its last.
      const words = String(event.message.content ?? "").trim();
      if (words) this.items.push({ kind: "say", text: words });
    } else if (event.kind === "result") {
      const { content } = event;
      const text = typeof content === "string" ? content : content.filter((part) => part.type === "text").map((part) => part.text).join("\n");
      const set = (this.timeline.sets ?? []).find((item) => item.id === this.hand.setId)?.name ?? "";
      this.items.push({
        kind: "call", id: event.id, refused: event.refused, answer: text,
        line: lineOf(event.name, event.args, text, set),
        looks: event.name.startsWith("look_") && !event.refused,
        pictures: typeof content === "string" ? [] : content.map((part) => part.image_url?.url).filter(Boolean),
      });
      if (!event.refused && this.bench) {
        // The glass keeps the person's view, except to follow a change of set.
        if (event.name === "use_set") this.bench.onSet(this.hand.setId);
        this.bench.lit(touchedBy(event.name, event.args, content));
      }
    } else if (event.kind === "picture") {
      const item = this.items.findLast((entry) => entry.kind === "call" && entry.id === event.id);
      if (item) { item.pictures = [...item.pictures, event.url]; item.redraw = true; }
    }
    this.changed();
  }
}

// ---- a person's pictures ------------------------------------------------------------

/** A picture file -> a `data:` URL, scaled so its long edge is at most `PICTURE_EDGE`. */
export async function scaled(file) {
  const bitmap = await createImageBitmap(file);
  const k = Math.min(1, PICTURE_EDGE / Math.max(bitmap.width, bitmap.height));
  const canvas = Object.assign(document.createElement("canvas"), { width: Math.max(1, Math.round(bitmap.width * k)), height: Math.max(1, Math.round(bitmap.height * k)) });
  canvas.getContext("2d").drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close?.();
  return canvas.toDataURL("image/jpeg", 0.9);
}

const isPicture = (file) => /^image\//.test(file?.type ?? "");

// ---- the window ---------------------------------------------------------------------

const PICTURE_ICON = "M2.5 3.5h13v11h-13z M3 13l3.5-3.5 3 3 2-2 3.5 3.5";

function glyph(path, size = 18) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  for (const [key, value] of Object.entries({ width: size, height: size, viewBox: "0 0 18 18", fill: "none", stroke: "currentColor",
    "stroke-width": "1.4", "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true" })) svg.setAttribute(key, value);
  const line = document.createElementNS("http://www.w3.org/2000/svg", "path");
  line.setAttribute("d", path);
  svg.append(line);
  return svg;
}

export class StagehandWindow {
  /** `bench`: the window this one is over. `talk`: the conversation it shows. */
  constructor(bench, talk) {
    this.bench = bench;
    this.talk = talk;
    this.open = false;
    this.host = null;
    this.drawn = new Map();
    this.modelName = el("b", {});
    this.modelWhere = el("span", {});
    this.changeButton = el("button", { class: "mmc-sh-btn", text: t("Change"),
      title: t("Opens the refiner's settings. Stagehand runs on the model selected there."),
      onclick: () => this.openSettings(this.changeButton) });
    this.restartButton = el("button", { class: "mmc-sh-btn", text: t("New conversation"), title: t("Forget what was said. The piece is not changed."),
      onclick: () => this.talk.restart() });
    this.log = el("div", { class: "mmc-sh-log", role: "log", "aria-label": t("The conversation") });
    this.chips = el("div", { class: "mmc-sh-chips", hidden: true });
    this.file = el("input", { type: "file", accept: "image/*", multiple: "", hidden: true,
      onchange: () => { this.attach([...this.file.files]); this.file.value = ""; } });
    this.pictureButton = el("button", { class: "mmc-sh-picture", "aria-label": t("Attach a picture"),
      title: t("Attach a picture: a reference for the set, or a frame to match"), onclick: () => this.file.click() }, [glyph(PICTURE_ICON)]);
    // The node's own prompt box, as the chat has it: `@` cites who is in the
    // piece's cast and offers the cast library, and somebody picked from there
    // is cast onto the piece, so the scene the model is told names them.
    this.box = new PromptBox({
      placeholder: t("Say what to build or change"),
      getState: () => ({ assets: [] }),
      onInput: (text) => { this.talk.draft = text; },
      onSubmit: () => this.send(),
      // A picture out of the input folder rides the message, as a dropped one does.
      onAttach: (row) => { this.attachRow(row); return null; },
      attachBlocked: () => null,
      getCast: () => this.talk.timeline.subjects ?? [],
      castFromLibrary: (member) => this.bench.castFromLibrary(member),
    });
    this.box.root.classList.add("mmc-sh-box");
    this.box.root.setAttribute("aria-label", t("Message to Stagehand"));
    this.box.root.addEventListener("paste", (event) => {
      const files = [...(event.clipboardData?.files ?? [])].filter(isPicture);
      if (!files.length) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      this.attach(files);
    }, true);
    this.sendButton = el("button", { class: "mmc-sh-send", onclick: () => (this.talk.working ? this.talk.stop() : this.send()) });
    this.note = el("div", { class: "mmc-sh-note", hidden: true });
    this.node = el("section", {
      class: "mmc-sh", hidden: true, "aria-label": t("Stagehand"),
      ondragover: (event) => { if ([...(event.dataTransfer?.types ?? [])].includes("Files")) event.preventDefault(); },
      ondrop: (event) => {
        const files = [...(event.dataTransfer?.files ?? [])].filter(isPicture);
        if (!files.length) return;
        event.preventDefault();
        event.stopPropagation();
        this.attach(files);
      },
    }, [
      el("div", { class: "mmc-sh-head" }, [
        el("div", { class: "mmc-sh-row" }, [
          el("span", { class: "mmc-sh-title", text: t("Stagehand") }),
          this.restartButton,
          el("button", { class: "mmc-sh-btn mmc-sh-x", text: "✕", "aria-label": t("Close Stagehand"), title: t("Close. It goes on working."), onclick: () => this.toggle(false) }),
        ]),
        el("div", { class: "mmc-sh-row" }, [el("span", { class: "mmc-sh-model" }, [this.modelName, this.modelWhere]), this.changeButton]),
        el("div", { class: "mmc-sh-size", text: t("Designed for larger models, 27B and up.") }),
      ]),
      this.log,
      el("div", { class: "mmc-sh-composer" }, [
        this.chips,
        el("div", { class: "mmc-sh-row mmc-sh-write" }, [this.pictureButton, this.box.root, this.sendButton, this.file]),
        this.note,
      ]),
    ]);
    this.onTalk = () => this.render();
    talk.listeners.add(this.onTalk);
  }

  /** Whether the box's menu is up: Escape is the menu's then, not the window's. */
  get mentioning() { return Boolean(this.box.menu); }

  /** Taken out of its bench: the conversation goes on without a window. */
  unmount() {
    this.talk.listeners.delete(this.onTalk);
  }

  toggle(open = !this.open) {
    this.open = open;
    this.node.hidden = !open;
    this.bench.handOpened?.();
    if (!open) return;
    this.render();
    this.box.root.focus();
    // Whose server it is on is the server's to say, once.
    remoteStatus().then((status) => { this.remote = status; this.renderModel(); }, () => {});
  }

  openSettings(anchor) {
    openRefinerSettings(anchor, () => this.render(), S.pieceFamily(this.talk.timeline));
  }

  async attachRow(row) {
    if (row.kind !== "image") { this.said = t("Only a picture can go with a message."); this.render(); return; }
    const blob = await (await fetch(viewUrl(row.path))).blob();
    this.attach([new File([blob], row.path.split("/").pop(), { type: blob.type })]);
  }

  async attach(files) {
    for (const file of files.filter(isPicture)) {
      if (this.talk.pictures.length >= MOST_PICTURES) { this.said = t("A message carries up to {n} pictures.", { n: MOST_PICTURES }); break; }
      try {
        this.talk.pictures.push({ name: file.name || t("a picture"), url: await scaled(file) });
      } catch {
        this.said = t("{name} could not be read as a picture.", { name: file.name || t("That file") });
      }
    }
    this.render();
  }

  send() {
    const words = this.box.getValue().trim();
    if (!words || this.talk.working || !refinerRequest().model) return;
    const pictures = this.talk.pictures.map((picture) => picture.url);
    this.talk.draft = "";
    this.talk.pictures = [];
    this.said = "";
    this.box.setValue("");
    this.talk.send(words, pictures);
  }

  // ---- drawing ---------------------------------------------------------------------

  renderModel() {
    const { backend, model } = refinerRequest();
    let host = "";
    try { host = this.remote?.url ? new URL(this.remote.url).hostname : ""; } catch { /* not a URL: said without */ }
    this.modelName.textContent = model || t("No model selected");
    this.modelWhere.textContent = !model ? "" : ` · ${backend !== "remote" ? t("in ComfyUI") : host ? t("on {host}", { host }) : t("on your server")}`;
    return { backend, model };
  }

  render() {
    if (!this.open) return;
    const { backend, model } = this.renderModel();
    const { working } = this.talk;
    this.restartButton.disabled = working || !this.talk.items.length;
    this.renderLog();
    // The composer: free unless it is working, and shut only by having no model.
    this.box.root.contentEditable = working || !model ? "false" : "true";
    this.box.root.classList.toggle("off", working || !model);
    this.box.root.dataset.placeholder = working ? t("Stagehand is working") : t("Say what to build or change");
    if (this.box.getValue() !== this.talk.draft && document.activeElement !== this.box.root) this.box.setValue(this.talk.draft);
    this.pictureButton.disabled = working || !model;
    this.sendButton.textContent = working ? t("Stop") : t("Send");
    this.sendButton.classList.toggle("stop", working);
    this.sendButton.disabled = !working && !model;
    this.chips.hidden = !this.talk.pictures.length;
    this.chips.replaceChildren(...this.talk.pictures.map((picture, at) => el("span", { class: "mmc-sh-chip" }, [
      el("img", { src: picture.url, alt: "" }), el("span", { text: picture.name }),
      el("button", { text: "×", "aria-label": t("Remove {name}", { name: picture.name }),
        onclick: () => { this.talk.pictures.splice(at, 1); this.render(); } }),
    ])));
    const none = model ? "" : backend === "remote"
      ? t("No model chosen. Pick one of the server's models in the refiner's settings.")
      : t("No text encoder chosen. Put a Qwen3-VL or Qwen3.5 text encoder in models/text_encoders and pick it in the refiner's settings.");
    this.note.hidden = !none && !this.said;
    const link = el("button", { class: "mmc-sh-link", text: t("Open the refiner's settings"), onclick: () => this.openSettings(link) });
    this.note.replaceChildren(el("span", { text: none || this.said || "" }), ...(none ? [link] : []));
  }

  renderLog() {
    const { items, working } = this.talk;
    const nodes = items.map((item) => {
      if (item.redraw) { this.drawn.delete(item); item.redraw = false; }
      if (!this.drawn.has(item)) this.drawn.set(item, this.draw(item));
      return this.drawn.get(item);
    });
    for (const item of this.drawn.keys()) if (!items.includes(item)) this.drawn.delete(item);
    this.workingLine ??= el("div", { class: "mmc-sh-working" }, [el("i", {}), el("span", { text: t("Working") })]);
    const all = [...nodes, ...(working ? [this.workingLine] : [])];
    if (!all.length) all.push(this.empty ??= el("div", { class: "mmc-sh-empty", text: t("Say what the set should be, who is in it and what the shots are. Stagehand builds it here while you watch, and never renders.") }));
    const now = [...this.log.children];
    if (now.length !== all.length || now.some((node, at) => node !== all[at])) this.log.replaceChildren(...all);
    // The newest line stays in view.
    this.log.scrollTop = this.log.scrollHeight;
  }

  /** One line of the transcript. Nothing the agent wrote is drawn as markup. */
  draw(item) {
    const thumbs = (urls, name) => (urls.length ? [el("div", { class: "mmc-sh-pics" }, urls.map((url) => el("button", {
      class: "mmc-sh-pic", "aria-label": name, title: t("Enlarge"), onclick: () => this.enlarge(url) }, [el("img", { src: url, alt: "" })])))] : []);
    if (item.kind === "user") {
      return el("div", { class: "mmc-sh-user" }, [...thumbs(item.pictures, t("A picture you sent")), el("div", { class: "mmc-sh-words", text: item.text })]);
    }
    if (item.kind === "say") return el("div", { class: "mmc-sh-say", text: item.text });
    if (item.kind === "note") return el("div", { class: "mmc-sh-quiet", text: item.text });
    if (item.kind === "error") {
      return el("div", { class: "mmc-sh-error", role: "alert" }, [el("span", { text: item.text }),
        ...(item.restart ? [el("button", { class: "mmc-sh-btn", text: t("New conversation"), onclick: () => this.talk.restart() })] : [])]);
    }
    const reason = item.refused ? item.answer.replace(/^Error: /, "") : "";
    return el("div", { class: `mmc-sh-call${item.refused ? " refused" : item.looks ? " looks" : ""}` }, [
      el("details", {}, [
        el("summary", {}, [el("i", { "aria-hidden": "true", text: item.refused ? "✕" : item.looks ? "◉" : "✓" }),
          el("span", { text: item.refused ? t("Refused: {line}. {reason}", { line: item.line, reason }) : item.line })]),
        el("pre", { class: "mmc-sh-answer", text: item.answer || t("A picture.") }),
      ]),
      ...thumbs(item.pictures, t("What Stagehand looked at")),
    ]);
  }

  enlarge(url) {
    const close = () => zoom.remove();
    const zoom = el("button", { class: "mmc-sh-zoom", "aria-label": t("Close the picture"), onclick: close,
      onkeydown: (event) => { if (event.key === "Escape") { event.stopPropagation(); close(); } } }, [el("img", { src: url, alt: "" })]);
    this.bench.modal.append(zoom);
    zoom.focus();
  }
}
