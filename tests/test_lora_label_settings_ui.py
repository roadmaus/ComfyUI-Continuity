"""The LoRA label opt-out is an Interface preference, saved through the real UI."""

import domshim
import layout
from harness import check


layout.skip_without_node()

SCRIPT = domshim.DOM + """
import { openSettings } from "./web/creator/settings.js";
import { api } from "../scripts/api.js";
import { uiSetting } from "./web/creator/api.js";
import { ko } from "./web/creator/locales/ko.js";
import { ja } from "./web/creator/locales/ja.js";
import { zh } from "./web/creator/locales/zh.js";

const posted = [];
const fetchApi = api.fetchApi.bind(api);
let refuse = false;
api.fetchApi = async (url, options = {}) => {
  if (url === "/continuity/settings" && options.method === "POST") {
    posted.push(JSON.parse(options.body));
    if (refuse) return { ok: false, status: 400, json: async () => ({ error: "rejected" }) };
  }
  return fetchApi(url, options);
};
globalThis.__settings.video_crf = 18;
globalThis.app = { extensionManager: { setting: { get: () => "en" } } };
const settle = async () => {
  for (let i = 0; i < 4; i++) await new Promise((done) => setTimeout(done, 0));
};
const row = () => document.body.querySelector('[data-key="lora_skip_metadata"]');
const buttons = () => row().querySelectorAll(".mmc-set-seg-opt");
const selected = () => buttons().map((button) => button.getAttribute("aria-pressed"));
const press = async (index) => { buttons()[index].listeners.click[0](); await settle(); };
const close = () => document.body.querySelector(".mmc-close").listeners.click[0]();

openSettings();
await settle();
const interfaceGroup = document.body.querySelector('[data-group="interface"]');
const out = {
  interface: interfaceGroup.contains(row()),
  defaults: selected(),
  name: row().querySelector(".mmc-set-name").textContent,
  help: row().querySelector(".mmc-set-what").attrs.title,
  choices: buttons().map((button) => button.attrs.title),
};
await press(1);
out.enabled = { pressed: selected(), stored: globalThis.__settings.lora_skip_metadata,
                cached: uiSetting("lora_skip_metadata", false), crf: globalThis.__settings.video_crf };
close();
openSettings();
await settle();
out.reopened = selected();
await press(0);
out.disabled = { pressed: selected(), stored: globalThis.__settings.lora_skip_metadata,
                 cached: uiSetting("lora_skip_metadata", true) };
refuse = true;
await press(1);
out.refused = { pressed: selected(), stored: globalThis.__settings.lora_skip_metadata,
                cached: uiSetting("lora_skip_metadata", true) };
out.posted = posted;
out.translated = [ko, ja, zh].map((dictionary) =>
  [out.name, out.help, ...out.choices].every((key) => Boolean(dictionary[key])));
close();
console.log(JSON.stringify(out));
"""

with layout.pack(skip=("atlas",)) as target:
    got = layout.in_pack(SCRIPT, target)

check("LoRA labels setting is under Interface", got["interface"], True)
check("missing preference leaves metadata enabled", got["defaults"], ["true", "false"])
check("setting label describes card metadata", got["name"], "Skip model metadata in LoRA cards")
check("help explains display-only scope and reopening", got["help"],
      "Card labels only. LoRA loading, trigger words, detail metadata and local thumbnails "
      "stay unchanged. Reopen the LoRA manager to apply changes.")
check("enable saves and updates the settings cache without changing render settings", got["enabled"],
      {"pressed": ["false", "true"], "stored": True, "cached": True, "crf": 18})
check("reopened settings display the saved value", got["reopened"], ["false", "true"])
check("disable saves and updates the settings cache", got["disabled"],
      {"pressed": ["true", "false"], "stored": False, "cached": False})
check("a refused save restores the displayed and cached preference", got["refused"],
      {"pressed": ["true", "false"], "stored": False, "cached": False})
for state, pressed in (
    ("default", got["defaults"]), ("enabled", got["enabled"]["pressed"]),
    ("disabled", got["disabled"]["pressed"]), ("reopened", got["reopened"]),
):
    check(f"{state} offers exactly two choices", len(pressed), 2)
    check(f"{state} selects exactly one choice", pressed.count("true"), 1)
check("each choice posts only the intended setting", got["posted"],
      [{"lora_skip_metadata": True}, {"lora_skip_metadata": False}, {"lora_skip_metadata": True}])
check("Korean Japanese and Chinese translate the label and all help", got["translated"], [True] * 3)
