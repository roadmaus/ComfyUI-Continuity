"""`MANIFEST.md`: the project's asset list, written out.

The lua-25d-game skill's asset manifest, generated rather than kept by hand
(spec §5.4): every asset on one row with its size, alpha, layer, pivot, seed,
family, full prompt and status. It is both the documentation of the game's art
and the queue — a planned row is a placeholder, and "make what is missing"
walks it. Never edited by hand; `project.save` rewrites it on every change.
"""

from . import project as projects, style as styles, targets


def _cell(value):
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def _size(recipe):
    size = recipe.get("size")
    return f"{size[0]}×{size[1]}" if size else "—"


def _pivot(recipe):
    pivot = recipe.get("pivot")
    return f"{pivot[0]}, {pivot[1]}" if pivot else "feet"


def render(base, project):
    style = project["style"]
    lines = [
        f"# {project['name']}",
        "",
        "Written by Game Forge from `project.json`. Do not edit: change the project and this follows.",
        "",
        "## Style",
        "",
        f"- **Mode:** {style['mode']} — {targets.MODES[style['mode']]['help']}",
        f"- **Clause:** {style['clause'] or '—'}",
        f"- **Family:** {style['family']}",
        f"- **Seed:** {style['seed']}",
    ]
    if style["references"]:
        lines.append("- **References:** " + ", ".join(f"`{r}`" for r in style["references"]))
    if style["loras"]:
        lines.append("- **LoRAs:** " + ", ".join(f"`{l['name']}` × {l['strength']:g}" for l in style["loras"]))
    if style["palette"]:
        lines.append("- **Palette:** " + " ".join(f"`{c}`" for c in style["palette"]))
    if style["grid"]:
        lines.append(f"- **Grid:** {style['grid']} master pixels to one art pixel")
    if style["texel_density"]:
        lines.append(f"- **Texel density:** {style['texel_density']:g} per metre")
    lines += ["", "## Targets", ""]
    lines += [f"- **{targets.TARGETS[t]['label']}** (`{t}`): {targets.TARGETS[t]['help']}"
              for t in project["targets"]]
    lines += ["", "## Assets", ""]
    if not project["assets"]:
        lines.append("None yet. Write a plan and apply it: `forge.py plan "
                     f"{project['name']} plan.json`.")
        return "\n".join(lines) + "\n"

    rows = [projects.state(base, project, recipe) for recipe in project["assets"]]
    counts = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    lines.append(", ".join(f"{n} {s}" for s, n in sorted(counts.items())) + ".")
    lines += ["", "| Kind | Name | Files | Size | Alpha | Layer | Pivot | Seed | Family | Status | Prompt |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
    for recipe, row in zip(project["assets"], rows):
        where = f"assets/{recipe['kind']}/{recipe['name']}/masters/"
        files = ", ".join(f"`{where}{f}`" for f in row["masters"]) or "—"
        lines.append("| " + " | ".join(_cell(v) for v in (
            recipe["kind"], f"**{recipe['name']}**", files, _size(recipe),
            "yes" if recipe["alpha"] else "no", recipe["layer"], _pivot(recipe),
            row["seed"], row["family"], row["status"], styles.prompt(recipe, style))) + " |")
    notes = [(r["name"], r["notes"]) for r in project["assets"] if r.get("notes")]
    if notes:
        lines += ["", "## Notes", ""]
        lines += [f"- **{name}:** {_cell(text)}" for name, text in notes]
    return "\n".join(lines) + "\n"
