// `{day|night}` in a prompt: a choice the seed makes — the browser's half.
//
// The mirror of `creator/variations.py`, and the compiler's copy is the one
// that counts: what a render reads is chosen there, on the piece, before a
// request exists. This copy exists so the prompt box can light the alternative
// the seed on the node will take *while you type it*, which it can only do
// honestly by making the very same choice. `tests/test_variations.py` runs the
// two against each other on one set of sentences and seeds.
//
// The grammar, once: a brace pair with a bar directly inside it is a group;
// `{like this}` is prose, so is a `{` nothing closes; groups nest; an
// alternative may be empty. The choice is a hash of the seed, the card and the
// group's number in reading order — a hash because it is the same twelve lines
// in both languages, where a seeded generator is not.

/** One `{a|b|c}`: where it sits, what it offers, and its number in reading
 *  order. `alternatives` are `{start, end, parts}`, each part a string or a
 *  nested group. */
export function parse(text) {
  text = String(text ?? "");
  const root = [];
  // Open brace pairs, innermost last: the offset of the `{`, and the
  // alternatives read so far, each with the offset its text starts at.
  const stack = [];
  const parts = () => (stack.length ? stack[stack.length - 1].alternatives.at(-1).parts : root);
  let buffer = "";
  const flush = () => { if (buffer) { parts().push(buffer); buffer = ""; } };
  // A brace pair that was not a group after all, put back as typed.
  const literal = (frame) => {
    const target = parts();
    target.push("{");
    frame.alternatives.forEach((alternative, number) => {
      if (number) target.push("|");
      target.push(...alternative.parts);
    });
  };

  for (let offset = 0; offset < text.length; offset += 1) {
    const char = text[offset];
    if (char === "{") {
      flush();
      stack.push({ start: offset, alternatives: [{ start: offset + 1, end: -1, parts: [] }] });
    } else if (char === "|" && stack.length) {
      flush();
      const frame = stack[stack.length - 1];
      frame.alternatives.at(-1).end = offset;
      frame.alternatives.push({ start: offset + 1, end: -1, parts: [] });
    } else if (char === "}" && stack.length) {
      flush();
      const frame = stack.pop();
      frame.alternatives.at(-1).end = offset;
      if (frame.alternatives.length === 1) {
        literal(frame);
        parts().push("}");
      } else {
        parts().push({ start: frame.start, end: offset + 1,
                       alternatives: frame.alternatives, index: -1 });
      }
    } else buffer += char;
  }
  flush();
  // Whatever is still open was never a group. Innermost first, so each lands
  // in its parent.
  while (stack.length) literal(stack.pop());
  number(root, { next: 0 });
  return root;
}

function number(parts, counter) {
  for (const part of parts) {
    if (typeof part === "string") continue;
    part.index = counter.next;
    counter.next += 1;
    for (const alternative of part.alternatives) number(alternative.parts, counter);
  }
}

function fnv1a(key) {
  let value = 0x811c9dc5;
  for (const byte of new TextEncoder().encode(key)) {
    value = Math.imul(value ^ byte, 0x01000193) >>> 0;
  }
  return value;
}

/* MurmurHash3's finaliser: FNV alone leaves the low bits of short keys too
   alike for `% n` to be fair, and the low bits are the ones taken. */
function fmix(value) {
  value ^= value >>> 16;
  value = Math.imul(value, 0x85ebca6b) >>> 0;
  value ^= value >>> 13;
  value = Math.imul(value, 0xc2b2ae35) >>> 0;
  value ^= value >>> 16;
  return value >>> 0;
}

/** Which of `count` alternatives group `index` takes, on `card` under `seed`.
 *  `card` is the card's number on the strip, or `"piece"` for the piece's own
 *  fields. The key is spelled as text, as it is on the other side. */
export function choose(seed, card, index, count) {
  return fmix(fnv1a(`${seed}:${card}:${index}`)) % count;
}

function write(parts, seed, card, out) {
  for (const part of parts) {
    if (typeof part === "string") { out.push(part); continue; }
    const taken = choose(seed, card, part.index, part.alternatives.length);
    write(part.alternatives[taken].parts, seed, card, out);
  }
}

/** The text with every choice made. Text with no group comes back as is. */
export function resolve(text, seed, card) {
  text = String(text ?? "");
  if (!text.includes("{")) return text;
  const out = [];
  write(parse(text), seed, card, out);
  return out.join("");
}

/**
 * Where to paint: the marks and the dimming for the choice `seed` makes.
 *
 * Only the groups the choice actually reaches are marked — a group inside an
 * alternative that is not taken is part of a span already dimmed whole, and a
 * second mark inside it would say something about a sentence the render never
 * reads. `marks` are the `{`, `|` and `}` of every live group, `off` the
 * alternatives not taken, both as `[start, end)` offsets into the bare text.
 */
export function layout(text, seed, card) {
  const marks = [];
  const off = [];
  const walk = (parts) => {
    for (const part of parts) {
      if (typeof part === "string") continue;
      const taken = choose(seed, card, part.index, part.alternatives.length);
      marks.push([part.start, part.start + 1]);
      part.alternatives.forEach((alternative, number) => {
        if (number) marks.push([alternative.start - 1, alternative.start]);
        if (number === taken) walk(alternative.parts);
        else off.push([alternative.start, alternative.end]);
      });
      marks.push([part.end - 1, part.end]);
    }
  };
  walk(parse(text));
  return { marks, off };
}
