# FAQ and troubleshooting

## Settings

The gear on the node's rail opens the pack's settings.

- **Where files go** is a per-machine setting (the Folders tab), not part of
  the workflow, with `%year%`-style tokens. Every family files into a folder
  of its own, and each has a row to override.
- **MP4 quality** is a setting too, on the same page. Two people opening the
  same workflow get the same shot without having to agree on how many
  megabytes it takes.
- **Language** follows ComfyUI's own locale: English, Japanese, Korean,
  Simplified Chinese. Corrections are one-line edits in
  `web/creator/locales/`.
- **Appearance** has a text size, and the pack takes its colours from
  ComfyUI's palette.

## Common errors

### "Render refused, naming a field and a folder"

Not a bug: a weight file is missing. Put the file it names in the folder it
names. [models.md](models.md) has every file.

### CUDA OOM with `HostBuffer.read_file_slice` on a long render

Recent ComfyUI streams weights with Dynamic VRAM by default. Start ComfyUI
with `--disable-dynamic-vram`
([ComfyUI#15255](https://github.com/Comfy-Org/ComfyUI/issues/15255)).

### fp8 isn't any faster

fp8 only speeds up sampling on cards with hardware fp8 matmul (RTX 40-series
and later). On older cards it still halves the checkpoint's memory.

### References refused on Ideogram 4.0

Ideogram reads no reference conditioning, and a render that silently ignored
your images would be worse than one that says so. Switch the model pill to
another stills family, or clear the references.

### References do nothing on LTX 2.5

Citing a reference on LTX 2.5 needs the Ingredients IC-LoRA in `models/loras`.
Lightricks hasn't released a 2.5 version, so use
[the 2.3 one](https://huggingface.co/Lightricks/LTX-2.3-22b-IC-LoRA-Ingredients),
which is what this pack is tested against.

### The refiner refuses H3's text encoder

By design. H3's 32B encoder is truncated to its hidden states and has no head
to decode text with. Use a Qwen3-VL 4B or 8B (the Krea 2 and Ideogram
encoders are exactly that), or point the refiner at a server.

### My 6-second H3 video is 5.9 or 6.1 seconds

H3's frame count has to satisfy `n % 17 == 5` at 24 fps, so not every whole
second exists. The pill shows whole seconds and the compiler lands on the
nearest legal count.

### GGUF files don't show up

They appear once [ComfyUI-GGUF](https://github.com/city96/ComfyUI-GGUF) is
installed. Same folder as the safetensors, picked the same way.

### An accelerator pill is missing

The cache pills, sage attention and the device chips belong to optional packs
(see the Thanks list in the README). They light up when the pack is
installed. `easy` (core's EasyCache) and `kitchen` (core's int8 attention)
need nothing installed, though `kitchen` only appears on builds that ship the
kernel.

## Other questions

### Was this pack called something else?

Yes, MiniMax Creator, back when MiniMax H3 was the only family it drove.
GitHub redirects the old address, so an existing clone still pulls, but it is
worth repointing:

```
git remote set-url origin https://github.com/roadmaus/ComfyUI-Continuity.git
```

Saved workflows, node ids, widget names and output folders are all unchanged.
Old graphs load and old files stay where they are.

### Does anything leave my machine?

No. Local open weights through ComfyUI core, no API key, nothing uploaded.
The one exception is opt-in: if you point the Refine button at a hosted API,
that request goes to the server you configured.

### Where do renders go?

`output/continuity/`, filed per family (`renders/ltx25/`, `stills/krea2/`),
with takes under `takes/` and upscales under `upscaled/`. All of it
overridable in settings.

### Can I add a model family?

A family is a package under `creator/families/` with a `declare.py` the
registry picks up; adding one doesn't mean touching the node. If there is a
model you want in here, open an issue.
