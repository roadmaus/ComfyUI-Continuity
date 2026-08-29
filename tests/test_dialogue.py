"""A quoted line becomes a spoken one, and comes back out as what it was.

The prompt box is a string with chips drawn over it — nothing about a chip is
stored, `build()` recognises it every time the box is redrawn — so the one thing
that can silently go wrong here is the round trip. A spoken line that does not
come back out of `getValue()` exactly as it went in is a prompt quietly edited by
being looked at, and the state is written from `getValue()` on every keystroke,
so the loss is saved as soon as it happens.

The other half is the form itself. `sayLine` writes §4.4 of MiniMax's own guide
— the speaker token, the delivery outside the tag, the language and the words
inside it, and the lips-closed sentence a voiceover has to be followed by — and
`subjects.substitute_speakers` resolves the token at queue time. Those two are
checked here against each other rather than each against its own idea of the
form.

    python3 tests/test_dialogue.py

Skips itself if node is not installed.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

import layout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import harness  # noqa: E402

if shutil.which("node") is None:
    harness.skipped("node is not installed")

from domshim import DOM  # noqa: E402

# One cast, two members, no files: a subject described in words alone is what
# the quote menu's "describe a voice" builds, and the compiler has always been
# able to define one.
CHECK = r"""
import { writeFileSync } from "node:fs";
await import("./dom.mjs");

const out = { errors: [], round: {}, lines: {} };
try {
  const { PromptBox } = await import("./web/creator/prompt.js");

  // The same walk `choose` makes: a lead-in decides the default, and the
  // default is what the line is written from.
  const sayFrom = (box, lead, words) => {
    const say = box.defaultSay(lead);
    return `(S${say.who.map((h) => "@" + h).join(",")}) ` + words + `|${say.delivery}`;
  };

  const cast = [
    { handle: "anna", takes: "person", from: [], description: "a quiet, breathy young woman" },
    { handle: "ben", takes: "person", from: [], description: "the man in the grey hoodie" },
  ];
  let value = "";
  const box = new PromptBox({
    getState: () => ({ assets: [], prompt: value }),
    getCast: () => cast,
    getPool: () => [],
    attachBlocked: () => false,
    onInput: (text) => { value = text; },
    onAttach: () => null,
  });

  // What the box is handed, and what it must hand back.
  const cases = {
    plain: "(S@anna) says: <d>[English] I get off at the next station.</d>",
    delivered: "(S@ben) whispers, <d>[French] Reste encore un peu.</d>",
    together: "(S@anna,@ben) shout together, <d>[English] Wait for us!</d>",
    voiceover: "(S@anna) says in an off-screen voiceover: <d>[English] I still remember"
      + " that road.</d> while their lips remain completely closed.",
    // Prose either side, a reference chip in it, and a §4.5 on-screen quote the
    // box must leave entirely alone.
    inSentence: 'A shot of @anna at the window. (S@anna) says: <d>[English] Here.</d>'
      + ' A sign reading "GARE DU NORD" slides past.',
    // Nobody cast Zoe, so this is prose and has to stay prose — the compiler
    // refuses it by name, and a chip drawn over it would hide that.
    uncast: "(S@zoe) says: <d>[English] Hello.</d>",
  };
  for (const [name, text] of Object.entries(cases)) {
    box.setValue(text);
    const chips = [...box.root.childNodes].filter((n) => n.dataset?.say !== undefined);
    out.round[name] = {
      back: box.getValue(),
      same: box.getValue() === text,
      chips: chips.length,
      // The words the chip shows, so a wrong capture group cannot pass by
      // round-tripping the source it never read.
      // `text` and not `textContent`: the shim flattens what is rendered
      // under a node onto the first and leaves the second the node's own.
      shown: chips.map((chip) => chip.text.replace(/\s+/g, " ").trim()).join(" | "),
    };
  }

  // The offsets the caret and the menu are measured in count a spoken line as
  // the text it stands for, not as one node.
  box.setValue(cases.inSentence);
  out.round.offsets = { walked: box.getValue().length, source: cases.inSentence.length };

  // A line that is already written is still editable: the chip is the way back
  // into the menu, and everything the menu needs comes back out of the text.
  {
    box.setValue("(S@ben) whispers, <d>[French] Reste encore un peu.</d>");
    const chip = box.root.childNodes[0];
    box.editSaid(chip);
    out.edit = { say: box.say, said: box.said, editing: box.editing };
    box.closeMenu();

    // Prose this menu did not write survives being edited — the guide's own
    // example of one — and picking a delivery is what replaces it.
    const custom = "(S@ben) exclaims with light annoyance, <d>[English] hey!</d>";
    box.setValue(custom);
    box.editSaid(box.root.childNodes[0]);
    const lead = box.say.lead;
    // Straight through the real path: pick Spoken and read back what landed.
    await box.choose(0);
    out.custom = { lead, again: box.getValue() };
    box.closeMenu();
  }

  // The words themselves. A chip is contenteditable="false" — it has to be —
  // so without a way in, a typo in what somebody says could only be fixed by
  // deleting the whole line and typing the quote again.
  {
    const START = "She waits. (S@anna) says: <d>[English] I get off at the next station.</d> On.";
    const fire = (field, key) => field.listeners.keydown[0](
      { key, preventDefault() {}, stopPropagation() {} });
    const reopen = () => {
      box.closeMenu();
      box.setValue(START);
      box.editSaid(box.root.querySelector("[data-say]"));
    };

    reopen();
    out.words = { offered: box.flat.map((o) => o.kind), showing: box.flat[0].label };

    // Changed, with everything around them left as it was.
    await box.choose(0);
    let field = box.menu.querySelector(".mmc-say-field");
    out.words.prefilled = field.value;
    field.value = "This is my stop.";
    fire(field, "Enter");
    out.words.written = box.getValue();

    // Escape is "leave it as it was".
    reopen();
    await box.choose(0);
    field = box.menu.querySelector(".mmc-say-field");
    field.value = "thrown away";
    fire(field, "Escape");
    out.words.escaped = box.getValue();

    // An emptied field is a question not answered, not an empty line.
    reopen();
    await box.choose(0);
    field = box.menu.querySelector(".mmc-say-field");
    field.value = "   ";
    fire(field, "Enter");
    out.words.emptied = box.getValue();

    // Over a written line, on screen is an undo: §4.5's form is where the
    // words came from.
    reopen();
    await box.choose(2);
    out.words.unwrapped = box.getValue();
    box.closeMenu();
  }

  // A press anywhere else is "not this". The blur path only fires while the box
  // has focus, and a menu reopened on a written line never gives it any — the
  // chip's press is cancelled so that pressing a line does not select it — so
  // without a listener of its own that menu could only be closed by answering
  // it. Asserted as "is something listening on the document", because the shim
  // has no pointer to press with.
  {
    box.closeMenu();
    box.setValue("(S@anna) says: <d>[English] Here.</d>");
    box.editSaid(box.root.querySelector("[data-say]"));
    await new Promise((f) => setTimeout(f, 0));
    // The handler itself, because the shim's document takes listeners and
    // forgets them. It is registered on a timeout and torn down by `closeMenu`,
    // and both halves matter: one left behind would close the next menu the
    // moment it opened.
    out.away = { open: !!box.away };

    // A press in the sentence closes it and takes nothing: the caret is going
    // where you put it, and a menu still standing over a caret three words away
    // is a menu nobody asked for. Leaving the box is the other answer, and the
    // half-typed trigger goes with it — which is what blurring has always done.
    const held = box.getValue();
    box.away({ target: box.root });
    out.away.inside = { menu: !!box.menu, text: box.getValue() === held };

    box.setValue("(S@anna) says: <d>[English] Here.</d>");
    box.editSaid(box.root.querySelector("[data-say]"));
    await new Promise((f) => setTimeout(f, 0));
    // A press on the menu itself is somebody using it.
    box.away({ target: box.menu });
    out.away.onMenu = !!box.menu;
    box.away({ target: document.body });
    out.away.outside = !!box.menu;

    box.closeMenu();
    out.away.closed = !!box.away;
  }

  // Who a spoken line cites. The census is what tells the host a name has
  // arrived or gone, and a line is the only place a speaker appears once the
  // menu has absorbed the lead-in they were written in.
  box.setValue("(S@anna,@ben) shout together, <d>[English] Wait!</d>");
  out.census = [...box.chipped].sort();

  // Everything in the menu that can be pressed keeps focus in the box.
  //
  // Not a style question. Leaving a contenteditable blurs it, and a blurred
  // prompt box dismisses its own menu 120ms later — so a control here without a
  // `pointerdown` that prevents the default is a control that tears the menu
  // down under the press and never receives the click. The rows always had it;
  // the three dials never did, and neither did the `/` menu's way back out of a
  // branch, which is why that one could only ever be taken with the left arrow.
  //
  // Asserted as "does this element listen for pointerdown", because that is the
  // whole of the fix and the shim has no focus to lose.
  {
    box.setValue('@anna "hold still"');
    box.said = "hold still";
    box.say = box.defaultSay();
    box.mode = String.fromCharCode(34);
    box.menu = { replaceChildren() {}, appendChild() {}, remove() {},
                 getBoundingClientRect: () => ({ width: 0, height: 0 }) };
    const pressable = [];
    // The bar, built as `renderMenu` builds it.
    for (const dial of box.sayBar().children) {
      if (String(dial.className).includes("mmc-say-dial")) {
        pressable.push(["dial", !!dial.listeners?.pointerdown?.length]);
      }
    }
    // A row, for the contrast that says the check is measuring something.
    box.rows = [];
    const row = box.sayRow({ kind: "say", label: "Spoken" }, 0);
    pressable.push(["row", !!row.listeners?.pointerdown?.length]);
    out.pressable = pressable;
    box.menu = null;
  }

  // What somebody has already written in front of their own quote. Without
  // this the line says who is speaking twice — "@vera is saying" and then
  // "<Subject 1> (S1) says:" — which is what the first build of this did.
  for (const [name, before] of Object.entries({
    verb: '@anna is saying ',
    delivery: '@ben whispers ',
    bare: '@anna ',
    // "reading" is not a speech verb, so the sentence keeps every word of
    // itself and the quote is only the quote.
    prose: '@anna looks at the sign reading ',
    // Nobody declared Zoe, so `@zoe` is prose like any other word.
    uncast: '@zoe says ',
    // A name is the only thing worth acting on: a pronoun and a verb say how,
    // and the whole question is who.
    pronoun: 'they say ',
  })) {
    out.lines[name] = box.leadIn(before);
  }
  // And the line each of those defaults to.
  out.lines.written = {
    verb: (() => { const l = box.leadIn('@anna is saying ');
                   return sayFrom(box, l, 'take this!'); })(),
    delivery: (() => { const l = box.leadIn('@ben whispers ');
                       return sayFrom(box, l, 'stay a little'); })(),
  };
} catch (error) {
  out.errors.push(`prompt box: ${error.stack}`);
}
console.log(JSON.stringify(out));
"""

work = tempfile.mkdtemp(prefix="mmc-say-")
try:
    pack = os.path.join(work, "pack")
    shutil.copytree(os.path.join(ROOT, "web"), os.path.join(pack, "web"),
                    # The atlas's half a thousand stills, and nothing else: the
                    # modules under presets/ are imported by api.js.
                    ignore=shutil.ignore_patterns("*.jpg", "*.png", "*.webp"))
    os.makedirs(os.path.join(work, "scripts"), exist_ok=True)
    for name, source in layout.STUBS.items():
        with open(os.path.join(work, "scripts", name), "w", encoding="utf-8") as handle:
            handle.write(source)
    with open(os.path.join(work, "scripts", "families.json"), "w", encoding="utf-8") as handle:
        handle.write(layout.catalog_json())
    with open(os.path.join(pack, "dom.mjs"), "w", encoding="utf-8") as handle:
        handle.write(DOM)
    with open(os.path.join(pack, "check.mjs"), "w", encoding="utf-8") as handle:
        handle.write(CHECK)
    result = subprocess.run(["node", os.path.join(pack, "check.mjs")],
                            capture_output=True, text=True, cwd=pack)
finally:
    shutil.rmtree(work, ignore_errors=True)

if result.returncode != 0:
    print("the prompt box did not load:\n" + (result.stderr.strip() or result.stdout.strip()))
    sys.exit(1)

report = json.loads(result.stdout.strip().splitlines()[-1])

from harness import FAILURES, check, passed  # noqa: E402

FAILURES.extend(report["errors"])
if report["errors"]:
    print(report["errors"][0])
    sys.exit(1)
round_trip = report["round"]

# The whole contract of a chip in this box: it is drawn from the text and the
# text is what survives.
for name in ("plain", "delivered", "together", "voiceover", "inSentence", "uncast"):
    check(f"{name}: the text comes back exactly as it went in",
          round_trip.get(name, {}).get("same"), True)

check("a spoken line is one chip", round_trip["plain"]["chips"], 1)
check("...and shows the speaker and the words",
      round_trip["plain"]["shown"], "@anna “I get off at the next station.”")
# The delivery and the language show only where they are not the ordinary
# answer, which is the whole reason the plain one above shows neither.
check("a delivery that is not `says` is on the chip",
      "WHISPERS" in round_trip["delivered"]["shown"].upper(), True)
check("...and so is a language that is not English",
      "FR" in round_trip["delivered"]["shown"], True)
check("two speakers are one chip naming both",
      round_trip["together"]["shown"].split("“")[0].strip(), "@anna @ben shouts")
check("a voiceover is one chip, tail and all", round_trip["voiceover"]["chips"], 1)

# §4.5: plain double quotes are what a sign or a subtitle already is, so the
# box has one chip in that sentence and not two.
check("an on-screen quote is left as the text it is",
      round_trip["inSentence"]["chips"], 1)
# A speaker nobody cast stays prose, exactly as an uncited `@name` does.
check("a line by somebody uncast is not drawn as one",
      round_trip["uncast"]["chips"], 0)
check("the walk counts a spoken line as its own length",
      round_trip["offsets"]["walked"], round_trip["offsets"]["source"])

# --- the lead-in somebody already wrote ---------------------------------------
lines = report["lines"]
check("`@anna is saying` in front of a quote is the speaker, and is replaced",
      lines["verb"], {"start": 0, "who": "anna", "delivery": "says"})
check("...and the verb they used is the delivery",
      lines["delivery"], {"start": 0, "who": "ben", "delivery": "whispers"})
check("a bare name in front of a quote is enough",
      lines["bare"], {"start": 0, "who": "anna", "delivery": None})
# The promise the cast is built on, held here too: prose is not reinterpreted.
check("a sentence that happens to end in a name is left whole",
      lines["prose"], None)
check("a name nobody cast is prose", lines["uncast"], None)
check("a pronoun says how but not who, so it is not acted on",
      lines["pronoun"], None)
check("the line is written to whoever the sentence already named",
      lines["written"]["verb"], "(S@anna) take this!|says")
check("...in the delivery it already used",
      lines["written"]["delivery"], "(S@ben) stay a little|whispers")

# Every dial, and the row beside them, keeps focus in the box.
for kind, guarded in report["pressable"]:
    check(f"a {kind} in the quote menu survives its own press", guarded, True)
check("all three dials are there", sum(1 for k, _ in report["pressable"] if k == "dial"), 3)

# --- changing a line that is already written -----------------------------------
edit = report["edit"]
check("clicking a line reads its speaker, language and delivery back out",
      edit["say"], {"who": ["ben"], "language": "French", "delivery": "whispers",
                    "lead": None})
check("...and the words it is holding", edit["said"], "Reste encore un peu.")
check("...and the span it will be written back over",
      edit["editing"], {"at": 0, "length": 54})
check("a lead-in this menu did not write is kept verbatim",
      report["custom"]["lead"], "exclaims with light annoyance,")
check("...and is still there after the line is saved again",
      report["custom"]["again"],
      "(S@ben) exclaims with light annoyance, <d>[English] hey!</d>")

# --- changing the words ---------------------------------------------------------
words = report["words"]
check("a written line offers its words first",
      words["offered"], ["words", "say", "onscreen"])
check("...and the row shows them", words["showing"], "\u201cI get off at the next station.\u201d")
check("the field opens holding what is said now",
      words["prefilled"], "I get off at the next station.")
check("new words are written, and nothing around them moves",
      words["written"],
      "She waits. (S@anna) says: <d>[English] This is my stop.</d> On.")
check("Escape leaves the line as it was",
      words["escaped"],
      "She waits. (S@anna) says: <d>[English] I get off at the next station.</d> On.")
# An empty `<d>` is a line the model is asked to say nothing in.
check("an emptied field writes nothing",
      words["emptied"],
      "She waits. (S@anna) says: <d>[English] I get off at the next station.</d> On.")
check("on screen, over a written line, puts the words back on screen",
      words["unwrapped"], 'She waits. "I get off at the next station." On.')

# The way out of a menu that was opened without the box ever taking focus.
check("an open menu listens for a press somewhere else", report["away"]["open"], True)
check("...and stops listening when it closes", report["away"]["closed"], False)
check("a press in the sentence closes the menu",
      report["away"]["inside"]["menu"], False)
check("...and leaves every word of it alone",
      report["away"]["inside"]["text"], True)
check("a press on the menu is somebody using it",
      report["away"]["onMenu"], True)
check("a press anywhere else closes it", report["away"]["outside"], False)

# The census is the host's "has this name arrived or gone". Converting a quote
# folds `@vera` into the line, so a census that could not see inside one read
# the conversion as that name being deleted, and detached their pictures.
check("a spoken line cites the people speaking it",
      report["census"], ["anna", "ben"])

passed("a quoted line becomes a spoken one and survives the round trip")
