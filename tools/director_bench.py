#!/usr/bin/env python3
"""Plan pieces headless, against any OpenAI-compatible server, and measure it.

Director plans a piece in many small calls (`creator/director_calls.py`), and
whether that holds up is a question about the model on the other end, not
about the room. This runs exactly the planning loop the room will run — the
same prompt files, the same readers, the same one re-ask — over the briefs in
`tests/director_briefs.jsonl`, and prints, per brief and per call, how it
went. Nothing is rendered; the plan is the result.

    python3 tools/director_bench.py --model lfm3-omni
    python3 tools/director_bench.py --url http://lab:8000/v1 --model qwen3.8-27b --json lab.json
    python3 tools/director_bench.py --url http://lab:8000/v1 --model qwen3.8-27b --steps large
    python3 tools/director_bench.py --only three --dump

`--steps` picks the planning profile the room's Planning setting picks
(`director_calls.STEPS`): `small`, the default, one decision a call; or
`large`, the structure and the shot list in two. Run both on one model and
compare the reports: that is what decides which the room should be set to.

**What it measures**, for each brief:

- each call valid on the first try, after the re-ask, or failed;
- the length the plan runs against the target, and what the model itself
  said, so a correction by code is visible rather than silent;
- whether every citation resolved (a refused citation is a re-ask, and its
  sentence is printed);
- cast members the brief cited: used in a shot, never listed as an entity
  (code drops them, but the relisting is counted), never given a sheet;
- entities no shot cites, and shots that cite nothing — the two quiet ways a
  plan stops being one piece;
- what code corrected on the way: entities dropped because nothing in the
  brief or beats speaks of them (on a small model, the prompt file's worked
  example copied in) or because they were cast already, and shots that
  repeat an earlier one even after the re-ask (kept, with a warning);
- a question asked when none was wanted, or none when one was;
- wall time and tokens per call;
- plan turns (§5.4 of the spec): each brief's scripted messages about its
  plan, sent one at a time to the plan as it was made. Whether the turn call
  picked an act and row the script accepts, whether the row then actually
  changed, and how the row's own call went. A turn naming a row the plan
  does not have (no heron in a heron piece) is counted as not measurable,
  not as wrong.

**Built to be compared.** `--json` writes the whole report, settings and
replies included, so a run of the 2B model on this Mac and a run of a 27B in
the lab sit side by side. A prompt change is judged across every model
benched, never tuned for the one at hand.

Needs no ComfyUI and no torch: the pure half of the pack, loaded the way the
test suites load it, and the remote client. The node's credential file is not
read; the URL given here is the only one used, with no key.
"""

import argparse
import importlib.util
import json
import os
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import layout  # noqa: E402 — tests' loader, which knows where the family modules live

BRIEFS = os.path.join(ROOT, "tests", "director_briefs.jsonl")


def _load(url):
    pkg = layout.load("canvas", "contextir", "compile", "compile_image", "prompting",
                      "manifest", "registry", "chat", "director", "director_calls",
                      package="mmc")
    spec = importlib.util.spec_from_file_location(
        "mmc.refine_remote", os.path.join(ROOT, "creator", "refine_remote.py"))
    remote = importlib.util.module_from_spec(spec)
    sys.modules["mmc.refine_remote"] = remote
    spec.loader.exec_module(remote)
    remote._read = lambda: {"url": url, "key": ""}
    return pkg, remote


def _rail(pkg, still, edit, video):
    """The rail as the room would snapshot it: the families by id, and the
    video family's own floor and ceiling off its manifest, which is what
    `director.limit_of` clamps the shot limit to."""
    frames = (pkg.manifest.describe(video).get("canvas") or {}).get("frames") or {}
    return {"still": still, "edit": edit, "video": video, "aspect": "16:9",
            "min_seconds": frames.get("min_seconds"), "max_seconds": frames.get("max_seconds")}


def _briefs(path, only):
    out = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                out.append(json.loads(line))
    if only:
        wanted = set(only.split(","))
        out = [b for b in out if b["id"] in wanted]
    return out


class Meter:
    """An `ask` with a stopwatch and a token counter round it.

    Tokens come off the server's `usage` block, read by wrapping the remote
    client's one request function; a server that sends none counts as zero
    rather than as a guess.
    """

    def __init__(self, remote, args):
        self.remote, self.args, self.calls, self._usage = remote, args, [], None
        real = remote._request

        def request(url, key, payload=None, **kw):
            body = real(url, key, payload, **kw)
            if isinstance(body, dict) and "usage" in body:
                self._usage = body.get("usage") or {}
            return body
        remote._request = request

    def ask(self, system, message, schema, label):
        if self.args.dump:
            print(f"\n===== {label}: SYSTEM =====\n{system}\n===== {label}: MESSAGE =====\n{message}")
        self._usage = None
        started = time.time()
        reply = self.remote.chat(self.args.model, system, message, [],
                                 temperature=self.args.temperature, seed=self.args.seed,
                                 max_tokens=self.args.max_tokens, prefill="",
                                 schema=None if self.args.no_schema else schema)
        usage = self._usage or {}
        self.calls.append({"label": label, "seconds": round(time.time() - started, 2),
                           "prompt_tokens": usage.get("prompt_tokens") or 0,
                           "completion_tokens": usage.get("completion_tokens") or 0})
        if self.args.dump:
            print(f"===== {label}: REPLY =====\n{reply}")
        return reply


def _measure(pkg, brief, out, error):
    """What the bench reports about one brief's plan."""
    director = pkg.director
    plan = out.get("plan") if out else (error.plan if error else None)
    log = (out or {}).get("log") or (error.log if error else [])
    cast = [director.name_of(m["name"]) for m in brief.get("cast") or ()]
    row = {"id": brief["id"], "target": brief.get("seconds"),
           "asked": bool(out and out.get("questions")), "want_ask": bool(brief.get("asks")),
           "questions": (out or {}).get("questions") or [],
           "failed": str(error) if error else None,
           "first_try": sum(1 for e in log if e["ok"] and e["tries"] == 1),
           "reasked": sum(1 for e in log if e["ok"] and e["tries"] == 2),
           "failed_calls": sum(1 for e in log if not e["ok"]),
           "reask_reasons": [f"{e['label']}: {e['first_error']}" for e in log if e["first_error"]],
           "relisted": (out or {}).get("relisted") or [],
           "invented": (out or {}).get("invented") or [],
           "uncited_dropped": (out or {}).get("uncited") or [],
           "warnings": (out or {}).get("warnings") or []}
    basics = next((e for e in log if e["call"] in ("basics", "structure")), None)
    row["model_seconds"] = ((basics or {}).get("raw") or {}).get("seconds")
    if plan and plan.get("shots") and not error:
        clips = director.clips(plan)
        actions = " ".join(s["action"] for s in plan["shots"])
        cited = {w.lower() for w in director.CITE_RE.findall(actions)}
        rows = director.rows(plan)
        row.update({
            "seconds": sum(c["seconds"] for c in clips),
            "beats": len(plan["beats"]), "entities": len([e for e in plan["entities"]
                                                          if "new" in e.get("source", {})]),
            "shots": len(plan["shots"]), "clips": len(clips),
            "cast_used": sorted(n for n in cast if n in cited),
            "cast_unused": sorted(n for n in cast if n not in cited),
            "cast_sheets": sorted(r["entity"] for r in rows if r["kind"] == "sheet"
                                  and any(e["id"] == r["entity"] and e["name"] in cast
                                          for e in plan["entities"])),
            "uncited_entities": sorted(e["name"] for e in plan["entities"]
                                       if "new" in e.get("source", {}) and e["name"] not in cited),
            "bare_shots": sum(1 for s in plan["shots"]
                              if not director.CITE_RE.search(s["action"])
                              and "@" not in s["action"]),
            "joins": [s["continues"] for s in plan["shots"]],
        })
    return row


def _show(plan, director):
    print(f"  \"{plan['title']}\", {plan['seconds']} s — look: {plan['look'] or '(none)'}")
    for a in plan.get("assumptions") or ():
        print(f"  assumes: {a}")
    seconds = director.allot_plan(plan)
    for beat in plan["beats"]:
        print(f"  {beat['id']} [{beat['weight']}, {seconds[beat['id']]} s] {beat['text']}")
        for shot in (s for s in plan["shots"] if s["beat"] == beat["id"]):
            print(f"      {shot['id']} {shot['continues']:>3} {seconds[shot['id']]:>3} s  {shot['action']}")
    for entity in plan["entities"]:
        source = entity.get("source") or {}
        what = f"cast @{source['cited']}" if "cited" in source else entity["description"]
        print(f"  @{entity['name']} ({entity['kind']}): {what}")


def _verdict(row):
    if row["failed"]:
        return "FAILED"
    if row["asked"] != row["want_ask"]:
        return "ASKED" if row["asked"] else "NO-ASK"
    if row["asked"]:
        return "ok (asked)"
    problems = []
    if row.get("target") and row.get("seconds") != row["target"]:
        problems.append("length")
    if row.get("cast_unused") or row.get("cast_sheets"):
        problems.append("cast")
    if row.get("uncited_entities"):
        problems.append("uncited")
    if row.get("warnings"):
        problems.append("repeat")
    return "ok" if not problems else "weak: " + ",".join(problems)


def _table(rows, calls):
    print("\n########## per brief")
    head = f"{'brief':<10} {'verdict':<16} {'calls 1st/re/fail':<18} {'len (model)':<13} " \
           f"{'b/e/s/c':<10} {'cast used':<12} {'uncited':<20} {'dropped':<16} bare"
    print(head)
    print("-" * len(head))
    for r in rows:
        calls_col = f"{r['first_try']}/{r['reasked']}/{r['failed_calls']}"
        length = f"{r.get('seconds', '-')} ({r['model_seconds'] if r['model_seconds'] is not None else '-'})"
        shape = "/".join(str(r.get(k, "-")) for k in ("beats", "entities", "shots", "clips"))
        cast = ",".join(r.get("cast_used") or []) or ("-" if not r.get("cast_unused") else "NONE")
        print(f"{r['id']:<10} {_verdict(r):<16} {calls_col:<18} {length:<13} {shape:<10} "
              f"{cast:<12} {','.join(r.get('uncited_entities') or []) or '-':<20} "
              f"{','.join(r['invented'] + r['relisted'] + r['uncited_dropped']) or '-':<16} "
              f"{r.get('bare_shots', '-')}")

    print("\n########## per call")
    print(f"{'call':<10} {'n':>3} {'1st':>5} {'re':>4} {'fail':>5} {'s/call':>8} {'tok in':>8} {'tok out':>8}")
    for name, stats in calls.items():
        print(f"{name:<10} {stats['n']:>3} {stats['first']:>5} {stats['re']:>4} {stats['fail']:>5} "
              f"{stats['seconds']:>8.1f} {stats['in']:>8.0f} {stats['out']:>8.0f}")


def _per_call(logs, meters, names=("brief", "basics", "beats", "entities", "shots",
                                    "structure", "shotlist"), key="call"):
    out = {}
    for name in names:
        entries = [e for log in logs for e in log if (e[key] if key == "call" else e["label"]) == name]
        timed = [c for c in meters if (c["label"].split(".")[0] if key == "call" else c["label"]) == name]
        if not entries:
            continue
        out[name] = {
            "n": len(entries),
            "first": sum(1 for e in entries if e["ok"] and e["tries"] == 1),
            "re": sum(1 for e in entries if e["ok"] and e["tries"] == 2),
            "fail": sum(1 for e in entries if not e["ok"]),
            "seconds": statistics.mean(c["seconds"] for c in timed) if timed else 0.0,
            "in": statistics.mean(c["prompt_tokens"] for c in timed) if timed else 0,
            "out": statistics.mean(c["completion_tokens"] for c in timed) if timed else 0,
        }
    return out


# ---- plan turns ------------------------------------------------------------------

def _wanted(calls, plan, want):
    """A script's `want` list -> `[(act, row id or None)]` the plan can
    satisfy. `edit:shot:2`, `edit:beat:last`, `edit:entity:keeper` (any
    entity whose name holds the word), `edit:header`, `replan`, `say`; and
    for the acts that arrange shots, `add`, `remove:shot:2`, `move:shot:last`
    (a bare `remove` or `move` takes any row)."""
    out = []
    for item in want:
        act, _, where = item.partition(":")
        if act not in ("edit", "remove", "move") or not where:
            out.append((act, None))
            continue
        kind, _, which = where.partition(":")
        if kind == "header":
            out.append((act, "header"))
        elif kind in ("beat", "shot"):
            rows = plan["beats" if kind == "beat" else "shots"]
            at = len(rows) if which == "last" else int(which)
            if 1 <= at <= len(rows):
                out.append((act, rows[at - 1]["id"]))
        elif kind == "entity":
            out += [(act, e["id"]) for e in plan["entities"] if which in e["name"]]
    return out


def _row_of(plan, row_id):
    if row_id == "header":
        return {k: plan.get(k) for k in ("title", "seconds", "look")}
    for key in ("beats", "entities", "shots"):
        for row in plan[key]:
            if row["id"] == row_id:
                return row
    return None


def _turns(pkg, brief, plan, meter, steps="small"):
    """Each scripted turn, on the plan as it was made. -> one row per turn."""
    calls = pkg.director_calls
    out = []
    for script in brief.get("turns") or ():
        wanted = _wanted(calls, plan, script["want"])
        row = {"brief": brief["id"], "say": script["say"], "want": script["want"],
               "measurable": bool(wanted), "act": None, "row": None, "right": None,
               "changed": None, "failed": None, "log": [], "reply": None}
        started = time.time()
        try:
            got = calls.plan_turn(plan, script["say"], meter.ask,
                                  cast=brief.get("cast") or (), ledger=brief.get("ledger") or (),
                                  steps=steps)
        except calls.PlanningFailed as failed:
            row.update(failed=str(failed), log=failed.log)
        else:
            row.update(act=got["act"], row=got["row"], log=got["log"],
                       label=calls.label_of(plan, got["row"]) if got["row"] else None,
                       reply=got["say"] if got["act"] == "say" else None,
                       render=bool(got.get("render")), recast=got.get("recast"))
            if wanted:
                row["right"] = any(act == got["act"] and (rid is None or rid == got["row"])
                                   for act, rid in wanted)
            new = got["plan"]
            if got["act"] == "edit" and new:
                row["changed"] = _row_of(plan, got["row"]) != _row_of(new, got["row"])
            elif got["act"] == "replan" and new:
                row["changed"] = [b["text"] for b in new["beats"]] != [b["text"] for b in plan["beats"]]
            elif got["act"] in ("add", "remove", "move") and new:
                # A shot came, went, or the order moved.
                row["changed"] = [s["id"] for s in new["shots"]] != [s["id"] for s in plan["shots"]]
        row["wall"] = round(time.time() - started, 1)
        row["overruled"] = next((e.get("overruled") for e in row["log"] if e.get("overruled")), None)
        row["doubted"] = [e["warning"] for e in row["log"] if e.get("warning")]
        out.append(row)
        if row["failed"]:
            verdict = "FAILED: " + row["failed"]
        else:
            what = row["act"] + (f" {row['label']}" if row.get("label") else "")
            mark = "" if row["right"] is None else ("ok" if row["right"] else "WRONG, want " + " or ".join(script["want"]))
            if not row["measurable"]:
                mark = "not measurable here"
            tail = "" if row["changed"] in (None, True) else " (nothing changed)"
            verdict = f"{what} — {mark}{tail}" + (f": {row['reply']}" if row["reply"] else "")
            if row["overruled"]:
                verdict += f" [code: {row['overruled']}]"
        print(f"  turn \"{script['say']}\" -> {verdict}")
    return out


def _turn_table(turns, stats):
    if not turns:
        return
    print("\n########## plan turns")
    measured = [t for t in turns if t["measurable"] and not t["failed"]]
    edits = [t for t in turns if t["changed"] is not None]
    print(f"turns {len(turns)}, measurable {len(measured)}, right act and row "
          f"{sum(1 for t in measured if t['right'])}/{len(measured)}, failed "
          f"{sum(1 for t in turns if t['failed'])}, edits that changed their row "
          f"{sum(1 for t in edits if t['changed'])}/{len(edits)}, overruled by code "
          f"{sum(1 for t in turns if t['overruled'])}")
    print(f"{'call':<16} {'n':>3} {'1st':>5} {'re':>4} {'fail':>5} {'s/call':>8} {'tok in':>8} {'tok out':>8}")
    for name, st in stats.items():
        print(f"{name:<16} {st['n']:>3} {st['first']:>5} {st['re']:>4} {st['fail']:>5} "
              f"{st['seconds']:>8.1f} {st['in']:>8.0f} {st['out']:>8.0f}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--model", default="lfm3-omni")
    parser.add_argument("--url", default="http://localhost:11434/v1")
    parser.add_argument("--briefs", default=BRIEFS)
    parser.add_argument("--only", help="comma-separated brief ids")
    parser.add_argument("--still", default="krea2", help="the rail's still family")
    parser.add_argument("--edit", default="qwenedit", help="the rail's edit family")
    parser.add_argument("--video", default="h3", help="the rail's video family")
    parser.add_argument("--temperature", type=float, default=0.3)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--max-tokens", type=int, default=None)
    parser.add_argument("--steps", choices=("small", "large"), default="small",
                        help="the planning profile: one decision a call, or the structure "
                             "and the shot list in two (the room's Planning setting)")
    parser.add_argument("--no-schema", action="store_true",
                        help="send no response_format: the reply rides on the prompt alone, "
                             "as it does on a server that cannot constrain one")
    parser.add_argument("--quiet", action="store_true", help="the tables only, not each plan")
    parser.add_argument("--no-turns", action="store_true",
                        help="plan only: skip each brief's scripted plan turns")
    parser.add_argument("--dump", action="store_true",
                        help="print every system prompt, message and reply")
    parser.add_argument("--json", help="write the whole report to this file")
    args = parser.parse_args()

    pkg, remote = _load(args.url)
    calls = pkg.director_calls
    rail = _rail(pkg, args.still, args.edit, args.video)
    meter = Meter(remote, args)

    rows, logs, plans, turns, turn_timings = [], [], {}, [], []
    for brief in _briefs(args.briefs, args.only):
        print(f"\n########## {brief['id']}: {brief['brief']}")
        out, error = None, None
        started = time.time()
        try:
            out = calls.plan_piece(brief["brief"], rail, meter.ask,
                                   cast=brief.get("cast") or (), ledger=brief.get("ledger") or (),
                                   steps=args.steps)
        except calls.PlanningFailed as failed:
            error = failed
        except pkg.prompting.RefineError as unreachable:
            # Not the model planning badly: the model not answering. Every
            # brief after this would say the same, so the run stops here.
            print(f"STOPPED: {unreachable}")
            return 1
        logs.append((out or {}).get("log") or (error.log if error else []))
        row = _measure(pkg, brief, out, error)
        row["wall"] = round(time.time() - started, 1)
        rows.append(row)
        for reason in row["reask_reasons"]:
            print(f"  re-asked {reason}")
        for warning in row["warnings"]:
            print(f"  kept with a warning: {warning}")
        if error:
            print(f"  FAILED: {error}")
            if error.plan and not args.quiet:
                _show(error.plan, pkg.director)
        elif out["questions"]:
            print("  asks: " + " / ".join(out["questions"]))
        elif not args.quiet:
            _show(out["plan"], pkg.director)
        plan = (out or {}).get("plan") or (error.plan if error else None)
        if plan:
            plans[brief["id"]] = plan
        print(f"  ({row['wall']} s)")
        if out and out.get("plan") and not args.no_turns:
            # Timed apart from the plan's calls: a turn re-runs the beats or
            # shots call, and those must not blur the planning numbers.
            planned = len(meter.calls)
            turns += _turns(pkg, brief, out["plan"], meter, args.steps)
            turn_timings += meter.calls[planned:]
            del meter.calls[planned:]

    per_call = _per_call(logs, meter.calls)
    _table(rows, per_call)
    labels = sorted({e["label"] for t in turns for e in t["log"]})
    turn_calls = _per_call([t["log"] for t in turns], turn_timings, labels, key="label")
    _turn_table(turns, turn_calls)
    if args.json:
        report = {"model": args.model, "url": args.url, "rail": rail, "steps": args.steps,
                  "schema": not args.no_schema, "temperature": args.temperature,
                  "seed": args.seed, "when": time.strftime("%Y-%m-%d %H:%M:%S"),
                  "briefs": rows, "calls": per_call, "timings": meter.calls,
                  "logs": logs, "plans": plans, "turns": turns, "turn_calls": turn_calls,
                  "turn_timings": turn_timings}
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=1)
        print(f"\nreport: {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
