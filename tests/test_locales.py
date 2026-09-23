"""Locale data and the real lookup/interpolation contract, without ComfyUI.

    python tests/test_locales.py

Translations are data, but duplicate English keys silently discard an earlier
translation and a dropped {slot} silently hides a value. Check the source pairs
before importing the dictionaries: an ordinary JS import alone loses duplicates.
This does not judge prose quality or claim that every runtime-built key exists.
"""

from collections import Counter
import json
from pathlib import Path
import re

import layout
from harness import check, passed

layout.skip_without_node()
LANGUAGES = ("ko", "ja", "zh")
SLOTS = re.compile(r"\{(\w+)\}", re.ASCII)


def source_pairs(source, language):
    """Read the catalog's quoted string pairs, including two on the same line.

    Keep the tiny data format explicit rather than parsing arbitrary JavaScript.
    Whitespace, comments and a trailing comma are accepted; computed properties
    or executable values are not part of these translation catalogs.
    """
    header = re.match(r"\s*(?://[^\n]*\n\s*)*export const "
                      + language + r"\s*=\s*\{", source)
    if not header:
        raise ValueError(f"{language}: expected an exported dictionary")
    decoder = json.JSONDecoder()
    pos, pairs = header.end(), []

    def space(index):
        while True:
            match = re.match(r"(?:\s+|//[^\n]*(?:\n|$)|/\*[\s\S]*?\*/)", source[index:])
            if not match:
                return index
            index += match.end()

    while True:
        pos = space(pos)
        if source[pos:pos + 1] == "}":
            pos = space(pos + 1)
            if source[pos:pos + 1] == ";":
                pos = space(pos + 1)
            if pos != len(source):
                raise ValueError(f"{language}: unexpected code after dictionary")
            return pairs
        key, pos = decoder.raw_decode(source, pos)
        pos = space(pos)
        if source[pos:pos + 1] != ":":
            raise ValueError(f"{language}: expected ':' after {key!r}")
        value, pos = decoder.raw_decode(source, space(pos + 1))
        if not isinstance(key, str) or not isinstance(value, str):
            raise ValueError(f"{language}: catalog entries must be string pairs")
        pairs.append((key, value))
        pos = space(pos)
        if source[pos:pos + 1] == ",":
            pos += 1
        elif source[pos:pos + 1] != "}":
            raise ValueError(f"{language}: expected ',' after {key!r}")


# Guard the checker itself against the shadowing and same-line cases it covers.
fixture = 'export const ko = {"a": "1", "b": "2", /* note */ "a": "3",};'
check("source reader retains repeated and same-line pairs", source_pairs(fixture, "ko"),
      [("a", "1"), ("b", "2"), ("a", "3")])

catalogs = {}
for language in LANGUAGES:
    source = Path(layout.js("locales", f"{language}.js")).read_text(encoding="utf-8")
    pairs = source_pairs(source, language)
    duplicates = [key for key, count in Counter(key for key, _ in pairs).items() if count > 1]
    check(f"{language}: no shadowed English keys", duplicates, [])
    catalogs[language] = dict(pairs)
    for key, value in pairs:
        check(f"{language}: nonempty translation of {key!r}", bool(value.strip()), True)
        check(f"{language}: interpolation slots in {key!r}",
              Counter(SLOTS.findall(value)), Counter(SLOTS.findall(key)))
    check(f"{language}: same UI key set", set(catalogs[language]), set(catalogs["ko"]))

# Node-search names and descriptions are a second, independent locale surface.
definitions = {}
for language in LANGUAGES:
    path = Path(layout.ROOT) / "locales" / language / "nodeDefs.json"
    def no_duplicates(pairs):
        keys = [key for key, _ in pairs]
        check(f"{language}: nodeDefs has no duplicate JSON keys", len(set(keys)), len(keys))
        return dict(pairs)
    definitions[language] = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=no_duplicates)
    check(f"{language}: same node IDs", set(definitions[language]), set(definitions["ko"]))
    for node_id, fields in definitions[language].items():
        check(f"{language}: node fields for {node_id}", set(fields), {"display_name", "description"})
        for field, value in fields.items():
            check(f"{language}: nonempty {node_id}.{field}", isinstance(value, str) and bool(value.strip()), True)

SCRIPT = r"""
import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';
const root = pathToFileURL(process.argv[1] + '/');
const {t} = await import(new URL('i18n.js', root));
const catalogs = {};
for (const lang of ['ko', 'ja', 'zh']) {
  catalogs[lang] = (await import(new URL(`locales/${lang}.js`, root)))[lang];
}
let selected;
globalThis.app = {extensionManager: {setting: {get(key) {
  assert.equal(key, 'Comfy.Locale');
  return selected;
}}}};
const key = 'Add image';
for (const [locale, lang] of [['ko', 'ko'], ['ko-KR', 'ko'], ['ja', 'ja'],
                            ['ja-JP', 'ja'], ['zh', 'zh'], ['zh-CN', 'zh'], ['zh-TW', 'zh']]) {
  selected = locale;
  assert.equal(t(key), catalogs[lang][key]);
  // Exercise every actual translation through the runtime, not a mock lookup.
  for (const [english, value] of Object.entries(catalogs[lang])) {
    const params = Object.fromEntries([...english.matchAll(/\{(\w+)\}/g)]
      .map(([, name]) => [name, `<${name}>`]));
    assert.equal(t(english), value);
    assert.equal(t(english, params), value.replace(/\{(\w+)\}/g, (_, name) => params[name]));
  }
}
selected = 'en';
assert.equal(t(key), key);
selected = 'fr-FR';
assert.equal(t(key), key);
selected = 'ko';
const missing = '__locale_test__ {zero} {flag} {unset}';
assert.equal(t(missing, {zero: 0, flag: false}), '__locale_test__ 0 false {unset}');
assert.equal(t(missing), missing);
// Changing the frontend setting takes effect on the next call.
assert.equal(t(key), catalogs.ko[key]);
selected = 'ja';
assert.equal(t(key), catalogs.ja[key]);
Object.defineProperty(globalThis, 'navigator', {configurable: true, value: {language: 'zh-CN'}});
selected = undefined;
assert.equal(t(key), catalogs.zh[key]);
globalThis.app.extensionManager.setting.get = () => {throw new Error('not ready');};
assert.equal(t(key), catalogs.zh[key]);
delete globalThis.app;
delete globalThis.navigator;
assert.equal(t(key), key);
console.log(JSON.stringify(catalogs));
"""

reflected = layout.run(SCRIPT, layout.WEB_ROOT)
for language in LANGUAGES:
    check(f"{language}: source reader agrees with native JS import", reflected[language], catalogs[language])
passed("locale catalogs, node definitions, fallback and interpolation passed")
