"""The stage and retired-take review keep controls below the finished video.

    python3 tests/test_stage_footer.py

Runs the real Stage, timing chips, footer observer, and Fullscreen review/end
methods against the shared DOM shim. Only the private Fullscreen class is
exported in memory; its full shell constructor is not mounted here. Layout,
native video decoding, and browser zoom are not simulated: distinct layout and
screen heights prove which measurement the observer uses, not CSS geometry.
"""

import json
import subprocess

import layout
from domshim import DOM
from harness import check, died, passed

layout.skip_without_node()

SCRIPT = r'''
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
import path from "node:path";

let checks = 0;
const eq = (actual, expected, message) => {
  checks++;
  assert.deepEqual(actual, expected, message);
};
const truth = (value, message) => eq(Boolean(value), true, message);
let locale = "en";
globalThis.app = { extensionManager: { setting: { get: () => locale } } };
// Record the target, retaining the shared shim's disconnect/fire behavior.
ResizeObserver.prototype.observe = function (target) { this.target = target; };
NodeClass.prototype.pause = function () { this.paused = true; };
NodeClass.prototype.getAnimations = () => [];
NodeClass.prototype.animate = () => ({ finished: Promise.resolve() });
const fire = (node, type, extra = {}) => {
  const event = {
    target: node, currentTarget: node, stopped: false,
    stopPropagation() { this.stopped = true; }, ...extra,
  };
  for (const fn of node.listeners[type] ?? []) fn(event);
  return event;
};
const { el } = await import("./web/creator/dom.js");
const { t } = await import("./web/creator/i18n.js");
const { Stage, elapsed, timingChips, watchFooterSize } = await import("./web/creator/stage.js");
const labels = (root) => root.querySelectorAll(".mmc-stage-clock-label").map((n) => n.textContent);
const values = (root) => root.querySelectorAll(".mmc-stage-clock-value").map((n) => n.textContent);
const chipSnapshot = (chips) => chips.map((chip) => ({
  label: chip.querySelector(".mmc-stage-clock-label").textContent,
  value: chip.querySelector(".mmc-stage-clock-value").textContent,
  title: chip.getAttribute("title"),
}));
const clocks = (root) => chipSnapshot(root.querySelectorAll(".mmc-stage-clock"));

// Long jobs retain every hour, including three-digit hours; shorter jobs keep
// the familiar m:ss display. These are elapsed times, never a wall-clock Date.
for (const [ms, expected] of [
  [0, "0:00"], [59000, "0:59"], [3599000, "59:59"],
  [3600000, "1:00:00"], [43384000, "12:03:04"], [360005000, "100:00:05"],
]) eq(elapsed(ms), expected, `elapsed ${ms}`);

const languages = [
  ["en", ["Total execution", "Render window"]],
  ["ko", ["전체 실행", "렌더 구간"]],
  ["ja", ["総実行時間", "レンダー区間"]],
  ["zh", ["总执行时间", "渲染区间"]],
  ["zh-TW", ["总执行时间", "渲染区间"]],
];
for (const [language, expected] of languages) {
  locale = language;
  const chips = timingChips({ totalMs: 43384000, tookMs: 3600000 });
  eq(chipSnapshot(chips).map((chip) => chip.label), expected, `${language} labels`);
  eq(chipSnapshot(chips).map((chip) => chip.value), ["12:03:04", "1:00:00"], `${language} durations`);
  const missing = timingChips();
  eq(chipSnapshot(missing).map((chip) => chip.value), ["—", "—"], `${language} unknown is not zero`);
  for (const chip of missing) truth(chip.getAttribute("title").includes(
    t("Timing is unavailable for this result.")), `${language} unavailable explanation`);
  truth(timingChips({ totalMs: 1000, totalPending: true })[0].getAttribute("title").includes(
    t("The workflow is still running.")), `${language} pending explanation`);
}
locale = "en";
for (const invalid of [undefined, null, NaN, Infinity, -1, "0"]) {
  eq(chipSnapshot(timingChips({ totalMs: invalid, tookMs: invalid })).map((c) => c.value),
    ["—", "—"], "invalid or absent measurements are unavailable");
}
eq(chipSnapshot(timingChips({ totalMs: 0, tookMs: 0 })).map((c) => c.value),
  ["0:00", "0:00"], "a measured zero is still a valid time");
const explanations = timingChips({ totalMs: 1000, tookMs: 500 });
eq(explanations[0].getAttribute("title"),
  "From workflow execution start to completion, including loading and other nodes; queue waiting is excluded.",
  "total scope includes loading, not queue waiting");
eq(explanations[1].getAttribute("title"),
  "From the first detected sampling progress or preview to the saved result, including decoding, post-processing and saving; not sampling alone.",
  "render window is not described as sampling alone");

// Layout pixels are deliberately unlike zoomed screen pixels. Repeated equal
// measurements should not write another style or retrigger a layout cycle.
const measuredRoot = el("div");
const measuredReadout = el("div");
let writes = 0;
const setProperty = measuredRoot.style.setProperty.bind(measuredRoot.style);
measuredRoot.style.setProperty = (...args) => { writes++; setProperty(...args); };
measuredReadout.offsetHeight = 48;
measuredReadout.getBoundingClientRect = () => { throw new Error("screen pixels are zoomed"); };
const stopMeasuring = watchFooterSize(measuredRoot, measuredReadout);
const measuredObserver = __observers.at(-1);
eq(measuredObserver.target, measuredReadout, "observer watches the footer, not the media");
measuredObserver.fire();
eq(measuredRoot.style.getPropertyValue("--mmc-stage-footer-height"), "48px", "uses layout offsetHeight");
measuredObserver.fire();
eq(writes, 1, "an unchanged height is not written again");
measuredReadout.offsetHeight = 92;
measuredObserver.fire();
eq(measuredRoot.style.getPropertyValue("--mmc-stage-footer-height"), "92px", "wrapping or text scale can grow the footer");
measuredReadout.offsetHeight = NaN;
measuredObserver.fire();
eq(writes, 2, "invalid measurements do not overwrite the last height");
measuredReadout.offsetHeight = 0;
measuredObserver.fire();
eq(measuredRoot.style.getPropertyValue("--mmc-stage-footer-height"), "0px", "a hidden footer can be zero height");
stopMeasuring();
truth(measuredObserver.dead, "observer disconnects");
measuredReadout.offsetHeight = 123;
measuredObserver.fire();
eq(writes, 3, "disconnected observer no longer writes");
const observerClass = globalThis.ResizeObserver;
delete globalThis.ResizeObserver;
watchFooterSize(measuredRoot, measuredReadout)();
globalThis.ResizeObserver = observerClass;

// Mount the real Stage and render a retained result. Its lifecycle/timestamp
// derivation is covered separately; here it must display the result's clocks.
let gallery = 0, restyle = 0, handoffs = 0;
const stage = new Stage({ nodeId: () => 7, onGallery: () => gallery++, onRestyle: () => restyle++,
  resultChips: () => [el("button", { text: "Use frame", onclick: () => handoffs++ })],
});
const stageObserver = __observers.at(-1);
document.body.append(stage.root);
const result = {
  url: "/view?filename=lighting.mp4", name: "lighting.mp4", isImage: false,
  saved: { filename: "lighting.mp4", type: "output" },
  totalMs: 43384000, tookMs: 3600000, totalPending: false,
};
stage.state = "done";
stage.result = { ...result };
stage.render();
eq(stage.root.dataset.media, "video", "finished stage identifies video for footer CSS");
eq(stage.root.children, [stage.media, stage.rule, stage.readout], "footer is a sibling of media");
const video = stage.media.querySelector("video");
truth(video, "finished stage has one video");
eq(stage.media.querySelectorAll(".mmc-stage-chip").length, 0, "no actions or clocks are inside media");
eq(stage.readout.children.length, 2, "actions and clocks have separate groups");
truth(stage.readout.children[0].classList.contains("mmc-stage-actions"), "actions are first");
truth(stage.readout.children[1].classList.contains("mmc-stage-times"), "clocks are separate");
eq(clocks(stage.readout), chipSnapshot(timingChips(result)), "stage uses the shared timing rendering");
for (const attr of ["controls", "loop", "playsinline"]) eq(video.getAttribute(attr), "", `stage native ${attr}`);
eq(video.getAttribute("preload"), "metadata", "stage keeps native metadata preload");
truth(fire(video, "pointerdown").stopped, "scrubbing does not pan the canvas");
fire(video, "mouseenter"); eq(video.muted, false, "stage hover enables sound");
fire(video, "mouseleave"); eq(video.muted, true, "stage leaving mutes sound");
Object.assign(video, { currentTime: 12.75, paused: false });
for (const [language, expected] of languages) {
  locale = language;
  stage.renderReadout();
  eq(labels(stage.readout), expected, `${language} real Stage labels`);
  eq(stage.media.querySelector("video"), video, "clock refresh retains the same video element");
  eq([video.currentTime, video.paused], [12.75, false], "clock refresh preserves playback and seek position");
}
locale = "en";
stage.result.totalMs = null;
stage.result.tookMs = null;
stage.renderReadout();
eq(values(stage.readout), ["—", "—"], "unknown saved result clocks are not reconstructed as zero");
const actions = stage.readout.querySelector(".mmc-stage-actions").querySelectorAll("button");
for (const action of actions) fire(action, "click");
eq([gallery, restyle, handoffs], [1, 1, 1], "existing action callbacks remain available");
eq(stageObserver.target, stage.readout, "real Stage registers its footer");
stage.readout.offsetHeight = 64;
stageObserver.fire();
eq(stage.root.style.getPropertyValue("--mmc-stage-footer-height"), "64px", "stage footer reports height");
stage.result = { ...result, isImage: true, url: "/view?filename=lighting.png", name: "lighting.png" };
stage.render();
eq(stage.root.dataset.media, "image", "still media is distinguished from the video footer");
truth(stage.media.querySelector("img"), "still keeps its image element");
stage.state = "idle";
stage.render();
eq(stage.root.dataset.media, undefined, "idle state does not retain video styling");
stage.destroy();
truth(stageObserver.dead, "destroying the Stage disconnects its footer observer");

// Exercise Fullscreen's actual private review methods without constructing the
// unrelated editor shell. Imports and import.meta.url resolve to the packed
// module; the export exists only in this in-memory source, never production.
const moduleUrl = pathToFileURL(path.join(process.cwd(), "web/creator/fullscreen.js"));
const source = readFileSync(moduleUrl, "utf8")
  .replace("class Fullscreen {", "export class Fullscreen {")
  .replace(/from "(\.[^"]+)"/g, (_, spec) => `from "${new URL(spec, moduleUrl).href}"`)
  .replaceAll("import.meta.url", JSON.stringify(moduleUrl.href));
const { Fullscreen } = await import("data:text/javascript;base64," + Buffer.from(source).toString("base64"));
// Deterministic review repaint ticks, independent of a real one-second wait.
let nextTimer = 0;
const reviewTimers = new Map();
globalThis.setInterval = (fn, delay) => {
  const id = ++nextTimer;
  reviewTimers.set(id, { fn, delay });
  return id;
};
globalThis.clearInterval = (id) => reviewTimers.delete(id);
const tickReviews = () => { for (const { fn } of [...reviewTimers.values()]) fn(); };
const shell = Object.create(Fullscreen.prototype);
shell.dock = el("div");
document.body.append(shell.dock);
const tile = el("button");
document.body.append(tile);
shell.review(result, tile);
eq(reviewTimers.size, 0, "a finalized take needs no clock repaint timer");
const reviewCard = shell.reviewCard;
const reviewMedia = shell.reviewing.media;
const reviewReadout = reviewCard.querySelector(".mmc-stage-readout");
const reviewObserver = __observers.at(-1);
eq(reviewCard.dataset.media, "video", "take review uses the same video marker");
eq(reviewCard.children, [reviewMedia, reviewReadout], "take review footer is separate from media");
eq(reviewReadout.children.length, 2, "take review separates action and clock groups");
truth(reviewReadout.children[0].classList.contains("mmc-stage-actions"), "review action group");
truth(reviewReadout.children[1].classList.contains("mmc-stage-times"), "review clock group");
eq(clocks(reviewReadout), chipSnapshot(timingChips(result)), "review displays its result using shared timing chips");
for (const attr of ["autoplay", "controls", "loop", "playsinline"]) {
  eq(reviewMedia.getAttribute(attr), "", `review native ${attr}`);
}
eq(reviewMedia.getAttribute("preload"), "metadata", "review retains metadata preload");
eq(reviewMedia.muted, true, "review starts silent");
fire(reviewMedia, "mouseenter"); eq(reviewMedia.muted, false, "review hover enables sound");
fire(reviewMedia, "mouseleave"); eq(reviewMedia.muted, true, "review leaving mutes sound");
fire(shell.reviewLayer, "click", { target: reviewMedia });
eq(shell.reviewing.media, reviewMedia, "native media clicks do not close the review");
eq(reviewObserver.target, reviewReadout, "take review observes its own footer");
reviewReadout.offsetHeight = 76;
reviewObserver.fire();
eq(reviewCard.style.getPropertyValue("--mmc-stage-footer-height"), "76px", "review measures footer layout height");
const reviewBack = reviewReadout.querySelector(".mmc-fs-review-back");
fire(reviewBack, "click");
await Promise.resolve();
truth(reviewObserver.dead, "back action disconnects review footer observer");
eq(reviewMedia.paused, true, "closing review stops its video");
eq(shell.reviewing, null, "back action returns to the live stage");
eq(shell.stopReviewFooterSize, null, "review releases the observer disposer");
eq(shell.dock.children.length, 0, "closed review layer is removed");

// Opening another take disposes the previous observer, and a historical take
// without timing renders unknown even when the preceding one was measured.
shell.review(result, tile);
const previousObserver = __observers.at(-1);
const nextTile = el("button");
document.body.append(nextTile);
shell.review({ url: "/view?filename=studio-lighting.mp4", name: "studio-lighting.mp4" }, nextTile);
truth(previousObserver.dead, "switching reviewed takes cleans up the old observer");
eq(values(shell.reviewCard), ["—", "—"], "historical review does not borrow another take's clocks");
const currentObserver = __observers.at(-1);
shell.review({ ...result }, nextTile);
await Promise.resolve();
truth(currentObserver.dead, "pressing the current take again disconnects its observer");
eq(shell.reviewing, null, "pressing the current take toggles review off");

for (const [language, expected] of languages) {
  locale = language;
  shell.review(result, tile);
  eq(labels(shell.reviewCard), expected, `${language} real review labels`);
  shell.endReview({ animate: false });
  await Promise.resolve();
}

// A retired result can still be waiting for workflow completion. The Stage
// mutates that same result object; review repaints clocks without rebuilding
// the action group, card, or playing media, then stops after the terminal tick.
locale = "en";
const pendingResult = { ...result, totalMs: 1000, tookMs: 3000, totalPending: true };
shell.review(pendingResult, tile);
eq(reviewTimers.size, 1, "a pending reviewed take gets one repaint timer");
eq([...reviewTimers.values()][0].delay, 1000, "review clocks refresh once per second");
const pendingCard = shell.reviewCard;
const pendingMedia = shell.reviewing.media;
const pendingActions = pendingCard.querySelector(".mmc-stage-actions");
const pendingClocks = pendingCard.querySelector(".mmc-stage-times");
Object.assign(pendingMedia, { currentTime: 6.25, paused: false });
truth(clocks(pendingCard)[0].title.includes("The workflow is still running."), "review explains the pending total");
pendingResult.totalMs = 7000;
tickReviews();
eq(values(pendingCard), ["0:07", "0:03"], "pending tick reads updated timing from the same result");
eq(shell.reviewCard, pendingCard, "clock refresh keeps the review card");
eq(shell.reviewing.media, pendingMedia, "clock refresh keeps the review video");
eq([pendingMedia.currentTime, pendingMedia.paused], [6.25, false], "clock refresh preserves review playback position");
eq(pendingCard.querySelector(".mmc-stage-actions"), pendingActions, "clock refresh leaves action callbacks intact");
eq(pendingCard.querySelector(".mmc-stage-times"), pendingClocks, "clock refresh only replaces clock chips");
eq(reviewTimers.size, 1, "pending tick does not accumulate timers");
pendingResult.totalMs = 9000;
pendingResult.totalPending = false;
tickReviews();
eq(values(pendingCard), ["0:09", "0:03"], "terminal tick paints the final total");
eq(clocks(pendingCard)[0].title.includes("The workflow is still running."), false, "terminal tick removes the pending note");
eq(reviewTimers.size, 0, "terminal repaint stops its timer");
eq([pendingMedia.currentTime, pendingMedia.paused], [6.25, false], "terminal repaint still does not restart video");
shell.endReview({ animate: false });
await Promise.resolve();

const stillPending = { ...result, totalMs: null, totalPending: true };
shell.review(stillPending, tile);
eq(reviewTimers.size, 1, "unknown pending total still has a repaint timer");
eq(values(shell.reviewCard)[0], "—", "unknown pending total stays unavailable until measured");
const oldTimer = [...reviewTimers.keys()][0];
shell.review({ ...stillPending }, nextTile);
eq(reviewTimers.has(oldTimer), false, "switching takes clears the old review timer");
eq(reviewTimers.size, 1, "switching to another pending take leaves only its timer");
shell.endReview({ animate: false });
eq(reviewTimers.size, 0, "closing a pending review clears its timer immediately");
await Promise.resolve();
eq(shell.dock.children.length, 0, "all pending review layers are removed");
console.log(JSON.stringify({ checks }));
'''

with layout.pack(skip=["atlas"]) as target:
    # The DOM plus review scenarios exceed Windows' command-line size limit.
    # stdin runs the same packed modules without passing their source in argv.
    proc = subprocess.run(
        ["node", "--input-type=module"], input=DOM + SCRIPT,
        capture_output=True, text=True, cwd=target, timeout=60,
    )
    if proc.returncode != 0:
        died(f"node failed:\n{proc.stderr}")
    got = json.loads(proc.stdout)

check("the real Stage/review footer checks ran", got["checks"] >= 100, True)
passed("stage and take-review footer structure, clocks, localization, playback preservation and observer cleanup passed")
