// The blockout's agent: a conversation with the user's own chat model, and the
// tools it stages the piece with.
//
// The system prompt is the server's (`creator/prompts/stagehand/system.txt`) and
// is short. Each tool's docstring says what it does, what it takes and what it
// answers, and none says how a scene should look. A tool does one small thing,
// checks it, and answers with what now stands there or why it does not; nothing
// is put right behind the model's back. When the calls of one reply have changed
// the set, the last of them is answered with a picture of it.
//
// The model is the refiner's: each message asks whatever its settings have
// selected when the message is sent.

import { api } from "../../../scripts/api.js";
import { JSON_HEADERS } from "./api.js";
import * as S from "./state.js";
import { rulesFor } from "./canvas.js";
import { run as runJob, cancelPrompt } from "./queue.js";
import { settings as refinerSettings, chosenModel } from "./refine.js";
import { MODELS, MODEL_GROUPS } from "./setmodels.js";
import { Raster, DEG, stagedAt, filmAt, project, cornersOf, forwardOf, rightOf, upOf, vfovOf, guideSize, faceArrival, facingOf } from "./blockout.js";

/** Where a loop that never ends is ended. */
export const MOST_TURNS = 60;
/** How many pictures a person's message carries. */
export const MOST_PICTURES = 4;
const LOOK_WIDE = 1024;
const FAR = 40, BIG = 60, SMALL = 0.05, MOST_OBJECTS = 200, MOST_ID = 253;

const KINDS = Object.keys(S.SET_KINDS);
const WHATS = [...KINDS, ...MODELS.keys()];

// ---- reading arguments ----------------------------------------------------------

const round = (value) => Math.round(value * 100) / 100;
const degrees = (radians) => Math.round((radians ?? 0) * DEG) || 0;
/** Degrees as the piece keeps them: radians, the short way round. */
const radians = (value) => Math.atan2(Math.sin(value / DEG), Math.cos(value / DEG));

/** A number within bounds, or a sentence about it. */
function number(args, key, low, high, fallback) {
  const value = args?.[key];
  if (value === undefined || value === null) {
    if (fallback === undefined) throw new Error(`${key} is missing`);
    return fallback;
  }
  if (typeof value !== "number" || !Number.isFinite(value)) throw new Error(`${key} has to be a number`);
  if (value < low || value > high) throw new Error(`${key} has to be between ${low} and ${high}, and was ${value}`);
  return value;
}

function text(args, key, fallback, most = 4000) {
  const value = args?.[key];
  if (value === undefined || value === null) {
    if (fallback === undefined) throw new Error(`${key} is missing`);
    return fallback;
  }
  if (typeof value !== "string") throw new Error(`${key} has to be text`);
  if (value.length > most) throw new Error(`${key} can be at most ${most} characters long`);
  return value;
}

function list(args, key) {
  if (!Array.isArray(args?.[key]) || !args[key].length) throw new Error(`${key} has to be a list with something in it`);
  return args[key];
}

const oneOf = (value, names, what) => {
  if (!names.includes(value)) throw new Error(`there is no ${what} "${value}": it is one of ${names.join(", ")}`);
  return value;
};

// ---- saying what is there ---------------------------------------------------------

const whatOf = (piece) => piece.model || piece.kind;
const sizeOf = (piece) => `${round(piece.w)} wide, ${round(piece.h)} tall, ${round(piece.d)} deep`;

function objectLine(piece) {
  return [`#${piece.id} ${whatOf(piece)}`, piece.word && `"${piece.word}"`, piece.plays && `plays @${piece.plays}`,
    `at x ${round(piece.x)}, z ${round(piece.z)}${piece.y ? `, ${round(piece.y)} off the floor` : ""}, facing ${degrees(piece.ry)}`,
    piece.rx || piece.rz ? `tilted ${degrees(piece.rx)}, rolled ${degrees(piece.rz)}` : "", sizeOf(piece),
    piece.model ? piece.detail : ""].filter(Boolean).join(", ").replace(",", "");
}

function shotLines(timeline, segment, index) {
  if (S.isClip(segment)) return [`Shot ${index + 1}: a finished clip, ${round(segment.duration_s)} s`];
  const set = S.setOf(timeline, segment), staging = segment.staging;
  // A kept take is the shot as it was rendered: changing the shot lets it go.
  const kept = S.takeOn(segment) ? ", has a kept take that a change to the shot releases" : "";
  const out = [`Shot ${index + 1}: ${round(segment.duration_s)} s, ${set ? `on set "${set.name}"` : "not staged yet"}${kept}. Text: ${segment.prompt || "none"}`];
  if (!staging) return out;
  const at = (mark) => `${round(mark.t)} s (${[mark.x, mark.y ?? 0, mark.z].map(round).join(", ")})`;
  if (staging.camera.length) {
    out.push(`  camera: ${staging.camera.map((mark) => `${at(mark)} ${degrees(mark.yaw)}/${degrees(mark.pitch)} ${round(mark.mm)} mm`).join(" -> ")}`
      + `${staging.look ? `, kept on #${staging.look}` : ""}${staging.shake ? `, shake ${staging.shake.kind}` : ""}`);
  }
  for (const [id, marks] of Object.entries(staging.people)) out.push(`  #${id}: ${marks.map(at).join(" -> ")}`);
  return out;
}

/** A film nobody has put a shot in yet still has one empty card. */
function untouched({ segments }) {
  const [only] = segments;
  return segments.length === 1 && !S.isClip(only) && !only.prompt && !only.staging && !only.assets?.length && !only.take;
}

export function sceneText(timeline, setId) {
  const set = (timeline.sets ?? []).find((item) => item.id === setId);
  return [
    timeline.prompt && `Film: ${timeline.prompt}`,
    timeline.soundscape && `Sound: ${timeline.soundscape}`,
    timeline.music && `Music: ${timeline.music}`,
    timeline.subjects?.length && `Cast: ${timeline.subjects.map((member) => `@${member.handle}${member.description ? ` (${member.description})` : ""}`).join("; ")}`,
    timeline.sets?.length > 1 && `Sets: ${timeline.sets.map((item) => `"${item.name}"`).join(", ")}`,
    set ? `Set "${set.name}", ${set.objects.length} objects:` : "There is no set yet.",
    ...(set?.objects ?? []).map(objectLine),
    ...(untouched(timeline) ? ["There are no shots yet."] : timeline.segments.flatMap((segment, index) => shotLines(timeline, segment, index))),
  ].filter(Boolean).join("\n");
}

// ---- pictures ------------------------------------------------------------------------

function aimed(eye, at, mm) {
  const dx = at.x - eye.x, dy = at.y - eye.y, dz = at.z - eye.z;
  return { ...eye, mm, yaw: Math.atan2(dx, dz), pitch: Math.max(-1.5, Math.min(1.5, Math.atan2(dy, Math.hypot(dx, dz)))) };
}

/** The pixels a picture of the piece is drawn at. */
function lookSize(timeline) {
  const { w, h } = guideSize(timeline);
  const wide = Math.round(w >= h ? LOOK_WIDE : (LOOK_WIDE * w) / h);
  return [wide, Math.round((wide * h) / w)];
}

/** The nearest camera that has every object in frame: from a corner, or from above. */
function wholeSet(objects, above, [wide, tall]) {
  const points = objects.length ? objects.flatMap(cornersOf) : [[-3, 0, -3], [3, 2, 3]];
  const yaw = above ? 0 : 0.5, pitch = above ? -1.5 : -0.6;
  const cam = { x: 0, y: 0, z: 0, yaw, pitch, mm: 32 };
  const ahead = forwardOf(cam), right = rightOf(cam), up = upOf(cam);
  const dot = (point, axis) => point[0] * axis[0] + point[1] * axis[1] + point[2] * axis[2];
  // Along each of the frame's two ways: how far back the edges of the set ask
  // for, and the place between them.
  const lens = Math.tan(vfovOf(cam.mm) / 2) * 0.9;
  const across = [[right, (lens * wide) / tall], [up, lens]].map(([axis, slope]) => {
    const high = Math.max(...points.map((point) => dot(point, axis) - slope * dot(point, ahead)));
    const low = Math.min(...points.map((point) => dot(point, axis) + slope * dot(point, ahead)));
    return { axis, middle: (high + low) / 2, depth: (low - high) / (2 * slope) };
  });
  const depth = Math.min(...across.map((way) => way.depth), Math.min(...points.map((point) => dot(point, ahead))) - 1);
  const at = [0, 1, 2].map((k) => ahead[k] * depth + across[0].axis[k] * across[0].middle + across[1].axis[k] * across[1].middle);
  return { ...cam, x: at[0], y: at[1], z: at[2] };
}

/** Write each object's number above it, or close by where another number is. */
function writeNumbers(context, objects, cam, [wide, tall]) {
  Object.assign(context, { font: "13px sans-serif", textAlign: "center", textBaseline: "middle", lineWidth: 3, strokeStyle: "#000", fillStyle: "#fff" });
  const taken = [];
  for (const piece of objects) {
    const spots = cornersOf(piece).map((point) => project(cam, point, wide, tall));
    if (spots.includes(null)) continue;
    const middle = spots.reduce((sum, spot) => sum + spot.x, 0) / spots.length;
    const top = Math.min(...spots.map((spot) => spot.y));
    const words = `#${piece.id}`, half = context.measureText(words).width / 2 + 2;
    for (const [dx, dy] of [[0, -8], [-28, -8], [28, -8], [0, -22], [-28, -22], [28, -22], [-28, 6], [28, 6], [0, -36]]) {
      const x = Math.min(wide - half, Math.max(half, middle + dx)), y = Math.min(tall - 8, Math.max(8, top + dy));
      if (taken.some((box) => Math.abs(box.x - x) < box.half + half && Math.abs(box.y - y) < 14)) continue;
      taken.push({ x, y, half });
      context.strokeText(words, x, y);
      context.fillText(words, x, y);
      break;
    }
  }
}

/** A colour for a number, far from those of the numbers beside it. */
function hueOf(id) {
  const hue = (id * 137.5) % 360;
  return [0, 8, 4].map((n) => {
    const k = (n + hue / 30) % 12;
    return Math.round(255 * (0.6 - 0.36 * Math.max(-1, Math.min(k - 3, 9 - k, 1))));
  });
}

function picture(timeline, objects, cam, { labels = false, mode = "stage" } = {}) {
  const size = lookSize(timeline);
  const canvas = Object.assign(document.createElement("canvas"), { width: size[0], height: size[1] });
  const context = canvas.getContext("2d");
  const raster = new Raster(...size);
  raster.raster(objects, cam);
  // Each object in a colour of its own, where they are to be told apart.
  raster.shade(context, mode, labels ? { tints: Object.fromEntries(objects.map((piece) => [piece.id, hueOf(piece.id)])) } : {});
  if (labels) writeNumbers(context, objects, cam, size);
  return { type: "image_url", image_url: { url: canvas.toDataURL("image/png") } };
}

// ---- the tools -------------------------------------------------------------------------

const num = { type: "number" }, str = { type: "string" }, whole = { type: "integer" }, flag = { type: "boolean" };
const items = (properties, required) => ({ type: "array", items: { type: "object", properties, required } });
const modelSizes = MODEL_GROUPS.map((group) =>
  group.models.map((model) => `${model.id} ${model.w} x ${model.h} x ${model.d}`).join(", ")).join(", ");

/** One tool: its docstring, its arguments, and what it does to a draft of the
 *  piece. `set` marks the ones that change how the set stands. */
const TOOLS = {
  see_scene: {
    doc: `Read everything that is there now: the film's text, the cast, the set you are working on with all its objects, and the shots.

Args:
    None.

Returns:
    str: One line for each object and shot.`,
    run: (hand) => hand.scene(),
  },

  add_objects: {
    set: true,
    doc: `Put one or more new objects into the set. Distances are metres and angles are degrees. x runs to the right, z runs forward, y runs up, and the floor is at y 0.

Args:
    objects (list): The objects to add, at least one. Each has:
        what (str): "person", "block", "wall" and "post" are plain shapes. Every other name is a ready model.
        x (float): Centre of the object, -40 to 40.
        z (float): Centre of the object, -40 to 40.
        y (float, optional): How far its underside is off the floor, 0 to 20. Default 0.
        facing (float, optional): The way its front points. 0 is +z, 90 is +x, 180 is -z, -90 is -x. Default 0.
        width (float, optional): Size along x before it is turned, 0.05 to 20. Default is the object's own size.
        height (float, optional): Size along y, 0.05 to 20.
        depth (float, optional): Size along z before it is turned, 0.05 to 20.
        name (str, optional): What the object is called, such as "kitchen table".
        plays (str, optional): The handle of the cast member this person is.
        detail (str, optional): How a ready model is drawn: "block", "shape" or "detailed". Default "shape".

    Sizes as width x height x depth: person 0.5 x 1.75 x 0.35, block 1.2 x 0.9 x 0.8, wall 3.2 x 2.6 x 0.14, post 0.16 x 2.4 x 0.16, ${modelSizes}.

Returns:
    str: One line for each object with the number (#id) it was given, or why it was not added. A picture of the set follows.`,
    properties: { objects: items({ what: { type: "string", enum: WHATS }, x: num, z: num, y: num, facing: num, width: num, height: num, depth: num, name: str, plays: str, detail: { type: "string", enum: S.SET_DETAILS } }, ["what", "x", "z"]) },
    required: ["objects"],
    run: (hand, draft, args) => {
      const set = hand.setIn(draft, true);
      return list(args, "objects").map((given, at) => {
        try {
          return `Added ${objectLine(newObject(draft, set, given))}`;
        } catch (exc) {
          return `Object ${at + 1} of the list was not added: ${exc.message}`;
        }
      }).join("\n");
    },
  },

  move_object: {
    set: true,
    doc: `Move one object somewhere else, turn it, or both. What is left out stays as it is.

Args:
    id (int): Number of the object.
    x (float, optional): New centre, -40 to 40.
    z (float, optional): New centre, -40 to 40.
    y (float, optional): How far its underside is off the floor, 0 to 20.
    facing (float, optional): The way its front points, in degrees. 0 is +z, 90 is +x.
    tilt (float, optional): Turn about its own x axis, in degrees.
    roll (float, optional): Turn about its own z axis, in degrees.

Returns:
    str: The object as it stands now. A picture of the set follows.`,
    properties: { id: whole, x: num, z: num, y: num, facing: num, tilt: num, roll: num },
    required: ["id"],
    run: (hand, draft, args) => {
      const piece = hand.objectIn(draft, args.id);
      piece.x = number(args, "x", -FAR, FAR, piece.x);
      piece.z = number(args, "z", -FAR, FAR, piece.z);
      piece.y = number(args, "y", 0, BIG, piece.y);
      for (const [key, name] of [["ry", "facing"], ["rx", "tilt"], ["rz", "roll"]]) {
        if (args[name] !== undefined && args[name] !== null) piece[key] = radians(number(args, name, -3600, 3600));
      }
      return objectLine(piece);
    },
  },

  resize_object: {
    set: true,
    doc: `Change the size of one object. What is left out stays as it is.

Args:
    id (int): Number of the object.
    width (float, optional): Size along x before it is turned, 0.05 to 20.
    height (float, optional): Size along y, 0.05 to 20.
    depth (float, optional): Size along z before it is turned, 0.05 to 20.

Returns:
    str: The object as it stands now. A picture of the set follows.`,
    properties: { id: whole, width: num, height: num, depth: num },
    required: ["id"],
    run: (hand, draft, args) => {
      const piece = hand.objectIn(draft, args.id);
      for (const [key, name] of [["w", "width"], ["h", "height"], ["d", "depth"]]) piece[key] = number(args, name, SMALL, BIG, piece[key]);
      return objectLine(piece);
    },
  },

  describe_object: {
    doc: `Change what one object is called, who it plays, or how it is drawn. What is left out stays as it is.

Args:
    id (int): Number of the object.
    name (str, optional): What it is called. "" takes the name away.
    plays (str, optional): The handle of the cast member this person is. "" takes it away.
    detail (str, optional): How a ready model is drawn: "block", "shape" or "detailed".

Returns:
    str: The object as it is now, and whether a person plays nobody.`,
    properties: { id: whole, name: str, plays: str, detail: { type: "string", enum: S.SET_DETAILS } },
    required: ["id"],
    run: (hand, draft, args) => {
      const piece = hand.objectIn(draft, args.id);
      if (args.name !== undefined) piece.word = text(args, "name", "", 48);
      if (args.plays !== undefined) piece.plays = castHandle(draft, args);
      if (args.detail !== undefined) {
        if (!piece.model) throw new Error(`#${piece.id} is a plain ${piece.kind} and has no detail`);
        piece.detail = oneOf(args.detail, S.SET_DETAILS, "detail");
      }
      // The bench draws such a person grey and leaves them out of the cast row.
      return `${objectLine(piece)}${piece.kind === "person" && !piece.plays ? "\nThis person plays nobody in the cast." : ""}`;
    },
  },

  copy_object: {
    set: true,
    doc: `Put copies of one object in other places.

Args:
    id (int): Number of the object to copy.
    places (list): Where the copies go, at least one. Each has:
        x (float): Centre of the copy, -40 to 40.
        z (float): Centre of the copy, -40 to 40.
        facing (float, optional): The way its front points, in degrees. Default is the same as the object.

Returns:
    str: One line for each copy with the number (#id) it was given, or why it was not added. A picture of the set follows.`,
    properties: { id: whole, places: items({ x: num, z: num, facing: num }, ["x", "z"]) },
    required: ["id", "places"],
    run: (hand, draft, args) => {
      const piece = hand.objectIn(draft, args.id), set = hand.setIn(draft);
      return list(args, "places").map((place, at) => {
        try {
          const copy = { ...piece, id: freeId(set), x: number(place, "x", -FAR, FAR), z: number(place, "z", -FAR, FAR) };
          if (place.facing !== undefined && place.facing !== null) copy.ry = radians(number(place, "facing", -3600, 3600));
          set.objects.push(copy);
          return `Added ${objectLine(copy)}`;
        } catch (exc) {
          return `Copy ${at + 1} of the list was not added: ${exc.message}`;
        }
      }).join("\n");
    },
  },

  remove_objects: {
    set: true,
    doc: `Take objects out of the set.

Args:
    ids (list): Numbers of the objects.

Returns:
    str: What was removed. A picture of the set follows.`,
    properties: { ids: { type: "array", items: whole } },
    required: ["ids"],
    run: (hand, draft, args) => {
      const gone = list(args, "ids").map((id) => hand.objectIn(draft, id));
      const set = hand.setIn(draft);
      set.objects = set.objects.filter((piece) => !gone.includes(piece));
      for (const segment of draft.segments) {
        if (segment.set !== set.id || !segment.staging) continue;
        for (const piece of gone) {
          delete segment.staging.people[piece.id];
          if (segment.staging.look === piece.id) delete segment.staging.look;
        }
      }
      return `Removed ${gone.map((piece) => `#${piece.id} ${whatOf(piece)}`).join(", ")}`;
    },
  },

  use_set: {
    doc: `Choose the set the other tools work on, or start a new one. A set is a place, and several shots can share it. Without this call there is one set.

Args:
    name (str): Name of the set. If no set has that name, an empty one is made.

Returns:
    str: The set's name and its objects.`,
    properties: { name: str },
    required: ["name"],
    run: (hand, draft, args) => {
      const name = text(args, "name", undefined, 48).trim();
      if (!name) throw new Error("name is empty");
      hand.setId = ((draft.sets ?? []).find((set) => set.name === name) ?? newSet(draft, name)).id;
      return sceneText(draft, hand.setId);
    },
  },

  look_overview: {
    doc: `Look at the whole set, with each object's number written above it and each object in a colour of its own. The colours are only to tell them apart.

Args:
    above (bool, optional): true looks straight down, with +x to the right and +z to the top. false looks from a corner. Default false.

Returns:
    image: The set.`,
    properties: { above: flag },
    run: (hand, draft, args) => [hand.overview(args.above === true)],
  },

  look_from: {
    doc: `Look at the set from any point.

Args:
    x (float): Where to look from.
    y (float): Where to look from, height off the floor. Eye height is about 1.6.
    z (float): Where to look from.
    at_x (float): What to look towards.
    at_y (float): What to look towards.
    at_z (float): What to look towards.

Returns:
    image: What is seen from there.`,
    properties: { x: num, y: num, z: num, at_x: num, at_y: num, at_z: num },
    required: ["x", "y", "z", "at_x", "at_y", "at_z"],
    run: (hand, draft, args) => {
      const of = (key) => number(args, key, -1000, 1000);
      const cam = aimed({ x: of("x"), y: of("y"), z: of("z") }, { x: of("at_x"), y: of("at_y"), z: of("at_z") }, 24);
      return [picture(draft, hand.setIn(draft).objects, cam)];
    },
  },

  look_through_camera: {
    doc: `Look through a shot's camera at one moment, with everything where it is in that moment.

Args:
    shot (int): Number of the shot, from 1.
    time (float, optional): Seconds into the shot. Default 0.

Returns:
    image: The frame as the camera has it.`,
    properties: { shot: whole, time: num },
    required: ["shot"],
    run: (hand, draft, args) => {
      const { segment, index } = shotIn(draft, args);
      const set = S.setOf(draft, segment);
      if (!set || !segment.staging?.camera.length) throw new Error(`shot ${index + 1} has no camera yet`);
      const time = number(args, "time", 0, segment.duration_s, 0);
      return [picture(draft, stagedAt(set, segment.staging, time), filmAt(set, segment.staging, time, S.shakeRun(draft, index)), { mode: "as_staged" })];
    },
  },

  add_cast: {
    doc: `Add somebody to the cast, so that texts can name them as @handle and a person in the set can play them.

Args:
    handle (str): A short name in lowercase letters, digits and dashes.
    description (str): Who they are and what they look like.

Returns:
    str: The cast.`,
    properties: { handle: str, description: str },
    required: ["handle", "description"],
    run: (hand, draft, args) => {
      const handle = text(args, "handle", undefined, 32);
      if (!/^[a-z][a-z0-9-]*$/.test(handle)) throw new Error("handle has to be lowercase letters, digits and dashes");
      if ((draft.subjects ?? []).some((member) => member.handle === handle)) throw new Error(`@${handle} is in the cast already`);
      draft.subjects = [...(draft.subjects ?? []), { handle, takes: "person", from: [], description: text(args, "description") }];
      return draft.subjects.map((member) => `@${member.handle}`).join(", ");
    },
  },

  write_film_text: {
    doc: `Write the text for the film as a whole. What is left out stays as it is.

Args:
    look (str, optional): The look and setting of the film.
    sound (str, optional): What is heard.
    music (str, optional): The music.

Returns:
    str: "Done."`,
    properties: { look: str, sound: str, music: str },
    run: (hand, draft, args) => {
      draft.prompt = text(args, "look", draft.prompt);
      draft.soundscape = text(args, "sound", draft.soundscape);
      draft.music = text(args, "music", draft.music);
      return "Done.";
    },
  },

  add_shot: {
    doc: `Add a shot at the end of the film, on the set you are working on.

Args:
    text (str): What happens in the shot. Cast members are named as @handle.
    seconds (float): How long it lasts, from 1 to the longest shot the film's model renders.

Returns:
    str: The shot and its number.`,
    properties: { text: str, seconds: num },
    required: ["text", "seconds"],
    run: (hand, draft, args) => {
      const set = hand.setIn(draft, true);
      const words = text(args, "text"), seconds = number(args, "seconds", 1, longestShot(draft));
      const unused = untouched(draft);
      const segment = unused ? draft.segments[0] : S.emptySegment();
      Object.assign(segment, { prompt: words, duration_s: seconds, set: set.id, staging: { camera: [], people: {} } });
      if (!unused) draft.segments.push(segment);
      return shotLines(draft, segment, draft.segments.indexOf(segment)).join("\n");
    },
  },

  change_shot: {
    doc: `Change the text or the length of a shot. What is left out stays as it is.

Args:
    shot (int): Number of the shot, from 1.
    text (str, optional): What happens in the shot.
    seconds (float, optional): How long it lasts, from 1 to the longest shot the film's model renders.

Returns:
    str: The shot as it is now.`,
    properties: { shot: whole, text: str, seconds: num },
    required: ["shot"],
    run: (hand, draft, args) => {
      const { segment, index } = shotIn(draft, args);
      segment.prompt = text(args, "text", segment.prompt);
      if (args.seconds !== undefined && args.seconds !== null) segment.duration_s = number(args, "seconds", 1, longestShot(draft));
      return shotLines(draft, segment, index).join("\n");
    },
  },

  remove_shot: {
    doc: `Take a shot out of the film. The shots after it move up by one number.

Args:
    shot (int): Number of the shot, from 1.

Returns:
    str: How many shots are left.`,
    properties: { shot: whole },
    required: ["shot"],
    run: (hand, draft, args) => {
      const { index } = shotIn(draft, args);
      if (draft.segments.length === 1) throw new Error("it is the only shot");
      draft.segments.splice(index, 1);
      return `${draft.segments.length} shots`;
    },
  },

  move_camera: {
    doc: `Set where a shot's camera is and what it points at. With one point it stands still. With more it travels through them in order. This replaces the camera the shot had.

Args:
    shot (int): Number of the shot, from 1.
    points (list): At least one. Each has:
        time (float): Seconds into the shot.
        x (float): Where the camera is, -40 to 40.
        y (float): Height of the camera off the floor, 0 to 40.
        z (float): Where the camera is, -40 to 40.
        at_x (float): What it points at.
        at_y (float): What it points at.
        at_z (float): What it points at.
        lens (float, optional): Focal length in millimetres, 8 to 300. 24 is wide, 85 is narrow. Default 32.

Returns:
    str: The shot as it is now. The first frame follows as a picture.`,
    properties: { shot: whole, points: items({ time: num, x: num, y: num, z: num, at_x: num, at_y: num, at_z: num, lens: num }, ["time", "x", "y", "z", "at_x", "at_y", "at_z"]) },
    required: ["shot", "points"],
    run: (hand, draft, args) => {
      const { segment, index } = stagedIn(hand, draft, args);
      let before = 0;
      segment.staging.camera = list(args, "points").map((point) => {
        const at = (key) => number(point, key, -1000, 1000);
        const cam = aimed({ x: number(point, "x", -FAR, FAR), y: number(point, "y", 0, FAR), z: number(point, "z", -FAR, FAR) },
          { x: at("at_x"), y: at("at_y"), z: at("at_z") }, number(point, "lens", 8, 300, 32));
        // Turning on from where it pointed, the short way round.
        cam.yaw = before + radians((cam.yaw - before) * DEG);
        before = cam.yaw;
        return { t: number(point, "time", 0, segment.duration_s), ...cam };
      }).sort((a, b) => a.t - b.t);
      const set = S.setOf(draft, segment);
      return [{ type: "text", text: shotLines(draft, segment, index).join("\n") },
        picture(draft, stagedAt(set, segment.staging, 0), filmAt(set, segment.staging, 0, null), { mode: "as_staged" })];
    },
  },

  keep_camera_on: {
    doc: `Keep a shot's camera turned to one object all through the shot, wherever either of them goes.

Args:
    shot (int): Number of the shot, from 1.
    id (int): Number of the object. 0 turns this off.

Returns:
    str: The shot as it is now.`,
    properties: { shot: whole, id: whole },
    required: ["shot", "id"],
    run: (hand, draft, args) => {
      const { segment, index } = stagedIn(hand, draft, args);
      if (args.id === 0) delete segment.staging.look;
      else segment.staging.look = hand.objectIn(draft, args.id, S.setOf(draft, segment)).id;
      return shotLines(draft, segment, index).join("\n");
    },
  },

  shake_camera: {
    doc: `Make a shot's camera shake as if somebody held it.

Args:
    shot (int): Number of the shot, from 1.
    kind (str): "none", "barely", "hand", "walking" or "running".

Returns:
    str: The shot as it is now.`,
    properties: { shot: whole, kind: { type: "string", enum: ["none", ...S.SHAKES] } },
    required: ["shot", "kind"],
    run: (hand, draft, args) => {
      const { segment, index } = stagedIn(hand, draft, args);
      if (oneOf(args.kind, ["none", ...S.SHAKES], "shake") === "none") delete segment.staging.shake;
      else segment.staging.shake = { kind: args.kind, amount: 1, rate: 1, seed: index + 1 };
      return shotLines(draft, segment, index).join("\n");
    },
  },

  walk: {
    doc: `Move one object along points during a shot: somebody walking, a car driving, a door opening. It faces the way it goes. This replaces the way it moved in that shot; other shots are not changed.

Args:
    shot (int): Number of the shot, from 1.
    id (int): Number of the object.
    points (list): At least one; with one point it stands there. Each has:
        time (float): Seconds into the shot.
        x (float): -40 to 40.
        z (float): -40 to 40.
        y (float, optional): How far its underside is off the floor, 0 to 20. Default is as it stands in the set.
        facing (float, optional): The way its front points there, in degrees, instead of the way it goes.

Returns:
    str: The shot as it is now.`,
    properties: { shot: whole, id: whole, points: items({ time: num, x: num, z: num, y: num, facing: num }, ["time", "x", "z"]) },
    required: ["shot", "id", "points"],
    run: (hand, draft, args) => {
      const { segment, index } = stagedIn(hand, draft, args);
      const piece = hand.objectIn(draft, args.id, S.setOf(draft, segment));
      const given = list(args, "points").map((point) => ({
        mark: { t: number(point, "time", 0, segment.duration_s), x: number(point, "x", -FAR, FAR), y: number(point, "y", 0, BIG, piece.y ?? 0),
          z: number(point, "z", -FAR, FAR), rx: piece.rx ?? 0, ry: piece.ry ?? 0, rz: piece.rz ?? 0 },
        facing: point.facing === undefined || point.facing === null ? null : radians(number(point, "facing", -3600, 3600)),
      })).sort((a, b) => a.mark.t - b.mark.t);
      const marks = given.map((point) => point.mark);
      given.forEach(({ mark, facing }, k) => {
        const next = marks[k + 1];
        if (facing !== null) mark.ry = facing;
        else if (k > 0) { mark.ry = marks[k - 1].ry; faceArrival(marks, k, piece); }
        else if (next && Math.hypot(next.x - mark.x, next.z - mark.z) > 0.3) mark.ry = facingOf(piece, next.x - mark.x, next.z - mark.z, mark.ry);
      });
      segment.staging.people[piece.id] = marks;
      return shotLines(draft, segment, index).join("\n");
    },
  },
};

export const tools = () => Object.entries(TOOLS).map(([name, { doc, properties = {}, required = [] }]) =>
  ({ type: "function", function: { name, description: doc, parameters: { type: "object", properties, required } } }));

/** The longest shot the piece's family renders, in seconds. */
export const longestShot = (timeline) => rulesFor(S.pieceFamily(timeline)).maxSeconds;

function freeId(set) {
  if (set.objects.length >= MOST_OBJECTS) throw new Error(`a set holds at most ${MOST_OBJECTS} objects`);
  // After the last, so a number is not soon given to something else.
  const last = Math.max(0, ...set.objects.map((piece) => piece.id));
  if (last < MOST_ID) return last + 1;
  const taken = new Set(set.objects.map((piece) => piece.id));
  return Array.from({ length: MOST_ID }, (_, k) => k + 1).find((id) => !taken.has(id));
}

function castHandle(draft, args) {
  const handle = text(args, "plays", "", 33).replace(/^@/, "");
  if (handle && !(draft.subjects ?? []).some((member) => member.handle === handle)) throw new Error(`there is no @${handle} in the cast`);
  return handle;
}

function newObject(draft, set, given) {
  const what = oneOf(given?.what, WHATS, "object");
  const own = S.SET_KINDS[what] ?? MODELS.get(what);
  const piece = {
    id: freeId(set), kind: KINDS.includes(what) ? what : "block",
    x: number(given, "x", -FAR, FAR), y: number(given, "y", 0, BIG, 0), z: number(given, "z", -FAR, FAR),
    w: number(given, "width", SMALL, BIG, own.w), h: number(given, "height", SMALL, BIG, own.h), d: number(given, "depth", SMALL, BIG, own.d),
    rx: 0, ry: radians(number(given, "facing", -3600, 3600, 0)), rz: 0,
    plays: castHandle(draft, given), word: text(given, "name", "", 48),
  };
  if (MODELS.has(what)) Object.assign(piece, { model: what, detail: oneOf(given.detail ?? "shape", S.SET_DETAILS, "detail") });
  set.objects.push(piece);
  return piece;
}

function newSet(draft, name) {
  const taken = new Set((draft.sets ?? []).map((set) => set.id));
  let n = 1;
  while (taken.has(`set-${n}`)) n += 1;
  const set = { id: `set-${n}`, name, objects: [] };
  draft.sets = [...(draft.sets ?? []), set];
  return set;
}

function shotIn(draft, args) {
  if (untouched(draft)) throw new Error("there are no shots yet");
  const index = number(args, "shot", 1, draft.segments.length) - 1;
  const segment = draft.segments[index];
  if (!segment) throw new Error("shot has to be a whole number");
  if (S.isClip(segment)) throw new Error(`shot ${index + 1} is a finished clip`);
  return { segment, index };
}

/** A shot to be staged: on the set it has, or the one being worked on. */
function stagedIn(hand, draft, args) {
  const found = shotIn(draft, args);
  if (!S.setOf(draft, found.segment)) found.segment.set = hand.setIn(draft, true).id;
  found.segment.staging ??= { camera: [], people: {} };
  return found;
}

// ---- the conversation ----------------------------------------------------------------

/**
 * One conversation about one piece. The caller owns the piece and the window:
 * `timeline()` is the piece, `apply(next)` puts a changed one in its place,
 * `windowState()` is what the user has open and selected, or "", and
 * `told(event)` hears what happens. `request()` is which model to ask, and is
 * the refiner's own answer unless the caller has another.
 *
 * What is told, in order: `{kind: "call", id, name, args}` before a call is
 * answered; `{kind: "result", id, name, args, content, refused, changed}` once
 * it is, the piece already changed; `{kind: "picture", id, url}` for the
 * picture of the set put on the last changing call of a reply; and
 * `{kind: "reply", message}` for each of the model's replies. `{kind: "note",
 * text}` is a sentence from the server half about how the model was asked.
 */
export function refinerRequest(current = refinerSettings()) {
  const backend = current.backend === "remote" ? "remote" : "local";
  return { backend, model: chosenModel(current), device: current.chatDevice || "", eject: backend === "remote" && current.eject === true };
}

const ROUTE = "/continuity/stagehand";

export class Stagehand {
  constructor({ timeline, apply, request = refinerRequest, windowState = () => "", told = () => {} }) {
    Object.assign(this, { timeline, apply, request, windowState, told });
    this.session = `${new Date().toISOString().slice(0, 19).replace(/[^0-9]/g, "-")}-${Math.random().toString(36).slice(2, 8)}`;
    this.messages = [];
    this.logged = 0;
    this.known = null;      // the scene as the model last knew it
    this.setId = null;      // the set it is working on
    this.abort = null;
    this.asking = null;     // the backend and model of the message being worked on
  }

  /** End the work at once. What was done stays. A job in ComfyUI is cancelled
   *  the way ComfyUI's own Cancel cancels it; a server's connection is closed
   *  by `release`. */
  stop() {
    if (!this.abort) return;
    if (this.queued) cancelPrompt(this.queued).catch(() => {});
    this.abort.abort(Object.assign(new Error("Stopped."), { stopped: true }));
  }

  /** Tell the server a message ended without the model's closing words: it
   *  closes what it has out, and drops the model if the settings ask for that. */
  release() {
    api.fetchApi(`${ROUTE}/stop`, { method: "POST", headers: JSON_HEADERS, body: JSON.stringify({ session: this.session }) }).catch(() => {});
  }

  /** The set being worked on: the one chosen, or the first. */
  setIn(timeline, make = false) {
    const sets = timeline.sets ?? [];
    const set = sets.find((item) => item.id === this.setId) ?? sets[0] ?? (make ? newSet(timeline, "Set") : null);
    if (!set) throw new Error("there is no set yet: nothing has been added");
    this.setId = set.id;
    return set;
  }

  objectIn(timeline, id, set = this.setIn(timeline)) {
    const piece = set.objects.find((item) => item.id === id);
    if (!piece) throw new Error(`there is no object #${id} in the set "${set.name}"`);
    return piece;
  }

  scene() {
    const timeline = this.timeline();
    return sceneText(timeline, (timeline.sets?.length ? this.setIn(timeline) : null)?.id);
  }

  overview(above = false) {
    const timeline = this.timeline();
    const { objects } = this.setIn(timeline);
    return picture(timeline, objects, wholeSet(objects, above, lookSize(timeline)), { labels: true });
  }

  /** Say something, with up to `MOST_PICTURES` pictures as `data:` URLs, and let
   *  the model work until it has nothing left to call. -> its last words. */
  async send(words, pictures = []) {
    if (this.abort) throw new Error("it is still working");
    this.abort = new AbortController();
    // A change of model applies from the next message, never under this one.
    this.asking = this.request();
    const scene = this.scene();
    const beside = [this.windowState(), scene !== this.known ? scene : ""].filter(Boolean);
    const said = [words, ...beside].join("\n\n");
    // A plain string where nothing is attached: the one shape every server reads.
    this.messages.push({ role: "user", content: !pictures.length ? said
      : [...pictures.slice(0, MOST_PICTURES).map((url) => ({ type: "image_url", image_url: { url } })), { type: "text", text: said }] });
    this.known = scene;
    try {
      for (let turn = 0; turn < MOST_TURNS; turn++) {
        const message = await this.ask();
        this.messages.push(message);
        this.told({ kind: "reply", message });
        if (!message.tool_calls?.length) return message.content;
        let dressed = null;
        for (const call of message.tool_calls) if (await this.answer(call)) dressed = this.messages.at(-1);
        // One picture for all the changes of a reply, on the last of them.
        if (dressed) {
          const shown = this.overview();
          dressed.content = [{ type: "text", text: dressed.content }, shown];
          this.told({ kind: "picture", id: dressed.tool_call_id, url: shown.image_url.url });
        }
        this.known = this.scene();
      }
      throw Object.assign(new Error(`stopped after ${MOST_TURNS} turns`), { limit: MOST_TURNS });
    } catch (exc) {
      this.release();
      throw exc;
    } finally {
      this.settle();
      this.abort = null;
    }
  }

  /** Every call needs its result, or the conversation cannot go on. */
  settle() {
    const last = this.messages.findLastIndex((message) => message.role === "assistant");
    if (last < 0) return;
    const done = new Set(this.messages.slice(last + 1).map((message) => message.tool_call_id));
    for (const call of this.messages[last].tool_calls ?? []) {
      if (!done.has(call.id)) this.messages.push({ role: "tool", tool_call_id: call.id, content: "Stopped by the user." });
    }
  }

  /** One exchange. The answer comes on the socket, as a chat turn's does: a
   *  model building a set outlasts a fetch. */
  async ask() {
    const { signal } = this.abort;
    signal.throwIfAborted();
    this.queued = null;
    const asked = runJob(ROUTE, { session: this.session, ...this.asking, messages: this.messages, tools: tools(), seen: this.logged },
      { onQueued: (id) => { this.queued = id; } });
    // Left behind by a Stop, it still ends, and nobody is listening.
    asked.catch(() => {});
    const body = await Promise.race([asked, new Promise((_, reject) => {
      signal.addEventListener("abort", () => reject(signal.reason), { once: true });
    })]);
    this.queued = null;
    const { message } = body.choices[0];
    this.usage = body.usage;
    // Something the server half has to say about how it asked, said once.
    if (body.note) this.told({ kind: "note", text: body.note });
    // Its own reply is in the log already.
    this.logged = this.messages.length + 1;
    return { ...message, role: "assistant", content: message.content ?? "" };
  }

  /** Answer one call. -> whether the set stands differently now. */
  async answer(call) {
    this.abort.signal.throwIfAborted();
    const { name } = call.function;
    const tool = Object.hasOwn(TOOLS, name) ? TOOLS[name] : null;
    let content, changed = false, refused = false, args = {};
    try {
      if (!tool) throw new Error(`there is no tool ${name}`);
      args = JSON.parse(call.function.arguments || "{}");
      this.told({ kind: "call", id: call.id, name, args });
      const draft = S.parseTimeline(S.serializeTimeline(this.timeline()));
      content = tool.run(this, draft, args);
      S.ensureCardIds(draft);
      S.syncTimeline(draft);
      changed = S.serializeTimeline(draft) !== S.serializeTimeline(this.timeline());
      if (changed) this.apply(draft);
    } catch (exc) {
      content = `Error: ${exc.message ?? exc}`;
      refused = true;
    }
    this.messages.push({ role: "tool", tool_call_id: call.id, content });
    this.told({ kind: "result", id: call.id, name, args, content, refused, changed });
    // Let the window draw what was done before the next is.
    await new Promise((resolve) => setTimeout(resolve));
    return changed && Boolean(tool.set);
  }
}
