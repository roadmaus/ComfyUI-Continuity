// The guide switch: whether the ControlNet branch is loaded, and how hard it
// pulls.
//
// **It does not pick anything, and that is the whole design.** The drawing is
// attached the way every other clip is — the "Add guide" tool, the picker's
// Guide tab, a chip on the card with its own thumbnail and its own trim. A
// guide is media and the pack already knew how to attach media; an earlier
// version of this file put a file picker on the sampler row and it was a
// dropdown standing where a preview card belonged.
//
// What is left for a pill is the part that is genuinely a machine decision.
// Loading a control branch costs several gigabytes beside the checkpoint, so it
// is something you throw rather than something that happens because a clip
// landed on a card — and the strength is a number about the weights, not about
// the footage, which is why it sits here beside the accelerators and not on the
// chip. `editor.addGuide` throws the switch on when the first drawing arrives,
// so the common path needs no press at all; off stays one press away and stays
// where it is put.
//
// Drawn only where the family declares a ControlNet, and only where there is
// something to aim: a switch over a strip with no drawing on it would load a
// branch to discover there is nothing to follow.

import { el, icon } from "./dom.js";
import * as S from "./state.js";
import { t } from "./i18n.js";

/** What each stop means, in the words the tooltip uses. Keyed by the family's
 *  own stop names — a family that declares a fourth gets no line here and shows
 *  its number instead, which is honest rather than blank. */
const STOP_TITLE = {
  loose: "Half strength. The drawing suggests the composition and the model is "
       + "free to disagree with it — the one to reach for when the tracing is "
       + "rougher than the shot needs to be.",
  firm: "Most of the way. The render follows the drawing and still has room to "
      + "put its own light and surface on it. The comfortable default.",
  locked: "Full strength, which is what the checkpoint was trained at. The "
        + "drawing decides the frame; everything else is the prompt's.",
};

/**
 * The switch, and while it is on, the strength stops.
 *
 * Two pills in the turbo switch's shape, because it is the same kind of control
 * — a thing thrown for the whole run, with a dial that only matters while it is
 * thrown. The parts are `.mmc-pill` and `.mmc-pill-set`, the general segmented
 * form rather than turbo's own bespoke classes.
 *
 * Lit in the accent rather than the accelerators' blue. Blue on this row means
 * "this render is not native", and a guide does not make it native or otherwise
 * — it decides the composition. The accent is what this pack lights the control
 * that is doing the deciding, the same reading the duration pill's auto switch
 * gets.
 *
 * @param {object} spec
 * @param {object} spec.container   a piece or a timeline: `.guide`, `.segments`
 * @param {() => void} spec.onCommit  serialize the container and redraw
 */
export function guidePills({ container, onCommit }) {
  const family = S.pieceFamily(container);
  const control = S.controlOf(family);
  if (!control) return [];

  // Nothing attached anywhere is nothing to switch on. The pill is not drawn
  // rather than drawn disabled: a disabled control says "not right now", and
  // the way to make this one available is to attach a drawing, which is a tool
  // in the rail and not a state of this pill. A switch left *on* from a piece
  // whose drawings have since been detached still draws, so that turning it off
  // is possible and so the row does not silently change under a detach.
  const guide = container.guide;
  const attached = S.guidedAnywhere(container);
  if (!attached && !guide.on) return [];

  const on = guide.on;
  const pills = [];

  // A drawing the weights were never post-trained on. Not a refusal — the file
  // is a picture and the branch will read it — but the render comes out looking
  // like the drawing rather than aimed by it. Counted across the piece, because
  // the switch is the piece's and one shot carrying an odd tracing is still
  // worth the word.
  const untrained = S.guidesUntrained(container, control.tracings ?? []);

  pills.push(el("div", { class: `mmc-pill${on ? " mmc-guide-on" : ""}` }, [
    el("button", {
      class: "mmc-guide-main",
      title: on
        ? t("The ControlNet branch is loaded and every shot with a drawing on it "
          + "is aimed at it. Switching off leaves the drawings where they are "
          + "and renders without the branch.")
        : t("Guide off. The drawings on the cards are ignored and no ControlNet "
          + "branch is loaded. On, each shot follows the one attached to it."),
      onclick: () => { guide.on = !guide.on; onCommit(); },
    }, [
      icon("pen", 16),
      el("span", { text: on ? t("guide") : t("guide off") }),
      ...(on && untrained ? [el("span", {
        class: "mmc-pill-sub mmc-guide-warn",
        text: t("untrained"),
        title: t("A drawing on this piece is a tracing these weights were not "
               + "post-trained on. That shot will look like the drawing rather "
               + "than be aimed by it. {list} are the ones they know.",
               { list: (control.tracings ?? []).join(", ") }),
      })] : []),
    ]),
  ]));

  // Only while it is doing something, like the turbo qualities and the spectrum
  // blend: off, the stops are a setting for a feature not in use.
  if (on) {
    const stops = S.guideStopNames(family);
    const pressed = S.guideStopOf(guide, family);
    pills.push(el("div", { class: "mmc-pill mmc-pill-set" }, stops.map((stop) => el("button", {
      class: `mmc-pill-seg${pressed === stop ? " mmc-guide-on" : ""}`,
      // Derived from the real strength, so a hand-edited number un-presses all
      // of them rather than leaving one lying about it.
      "aria-pressed": pressed === stop,
      title: t(STOP_TITLE[stop] ?? "Strength {value}.",
               { value: S.guideStopStrength(stop, family) }),
      onclick: () => {
        guide.strength = S.guideStopStrength(stop, family);
        onCommit();
      },
    }, [el("span", { text: t(stop) })]))));
  }

  return pills;
}
