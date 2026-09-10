"""Stored data counts every preference its picker/layout row can remove.

    python3 tests/test_picker_inventory.py

Only the existing in-memory userdata and DOM fixtures are used. No actual
browser settings, workflow, media, or server files are read or removed.
"""

import layout
from domshim import DOM
from harness import check

layout.skip_without_node()

SCRIPT = r'''
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
import path from "node:path";
globalThis.app = { extensionManager: { setting: { get: () => "en" } } };
const prefs = await import("./web/creator/api.js");
const settingsURL = pathToFileURL(path.join(process.cwd(), "web/creator/settings.js"));
// Export the private page/row for this test; all method bodies stay intact.
const source = readFileSync(settingsURL, "utf8")
  .replace("class SettingsPage {", "export class SettingsPage {")
  .replace("const STORED = [", "export const STORED = [")
  .replace(/from "(\.[^"]+)"/g, (_, spec) => `from "${new URL(spec, settingsURL).href}"`);
const { SettingsPage, STORED } = await import("data:text/javascript;base64," + Buffer.from(source).toString("base64"));
const row = STORED.find((entry) => entry.id === "picker");
const page = new SettingsPage(() => {});
let cases = 0;
for (const fixture of [
  { favorites: [], input: "references", renders: "all", plate: null, view: null, count: 1 },
  { favorites: [], input: "all", renders: "renders", plate: null, view: null, count: 1 },
  { favorites: [], input: "all", renders: "all", plate: "0.5", view: null, count: 1 },
  { favorites: [], input: "all", renders: "all", plate: null, view: "simple", count: 1 },
  { favorites: ["a.png [input]"], input: "references", renders: "renders", plate: "1", view: "full", count: 5 },
  { favorites: [], input: "all", renders: "all", plate: null, view: null, count: 0 },
]) {
  await row.remove();
  prefs.savePickerPrefs({ favorites: fixture.favorites,
    lastShelf: { input: fixture.input, renders: fixture.renders } });
  if (fixture.plate !== null) localStorage.setItem("mmc.fullscreen.plate", fixture.plate);
  if (fixture.view !== null) localStorage.setItem("mmc.fullscreen.view", fixture.view);
  localStorage.setItem("unrelated-preference", "preserve me");
  await page.takeStock();
  assert.equal(page.kept.picker, fixture.count);
  const node = page.storedRow(row);
  assert.equal("disabled" in node.querySelector("button").attrs, fixture.count === 0);
  assert.equal(STORED.filter((entry) => entry.held(page.kept) !== 0).includes(row), fixture.count > 0);
  await row.remove();
  await page.takeStock();
  assert.equal(page.kept.picker, 0);
  assert.equal(localStorage.getItem("unrelated-preference"), "preserve me");
  cases++;
}
console.log(JSON.stringify({ cases }));
'''

with layout.pack(skip=["atlas"]) as target:
    result = layout.in_pack(DOM + SCRIPT, target)
check("preferences can be counted and cleared independently", result["cases"], 6)
