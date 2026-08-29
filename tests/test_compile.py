"""Phase-1 contract tests: canvas math, duration snapping, and label ordering.

Runs standalone — `python tests/test_compile.py` — with no torch and no ComfyUI,
because `canvas.py` and `compile.py` are deliberately free of both. The label
ordering assertions are the important ones: if they drift out of step with
`encode.py`'s reference loop, prompts bind to the wrong tensors and nothing
raises.
"""

import os

import layout

_pkg = layout.load("canvas", "h3_declare", "contextir", "subjects", "compile",
                   "still", package="mmc")

# The family whose arithmetic these cases are written in. Its own declaration,
# not a default: every call below says which family it means.
H3 = _pkg.h3_declare.RULES
canvas, compiler, still = _pkg.canvas, _pkg.compile, _pkg.still

from harness import FAILURES, check, passed


def expect_error(label, fn, fragment):
    try:
        fn()
    except compiler.CompileError as exc:
        if fragment.lower() not in str(exc).lower():
            FAILURES.append(f"{label}: error {str(exc)!r} does not mention {fragment!r}")
    except Exception as exc:  # noqa: BLE001
        FAILURES.append(f"{label}: raised {type(exc).__name__} instead of CompileError: {exc}")
    else:
        FAILURES.append(f"{label}: expected a CompileError, got none")


# --- canvas ------------------------------------------------------------------

# The native stop must reproduce core's own numbers exactly.
check("16:9 @768", canvas.resolve_canvas(16 / 9, 768, H3), (1344, 768))
check("4:3 @768", canvas.resolve_canvas(4 / 3, 768, H3), (1024, 768))
check("1:1 @768", canvas.resolve_canvas(1.0, 768, H3), (768, 768))
check("9:16 @768", canvas.resolve_canvas(9 / 16, 768, H3), (768, 1344))

for label, ratio in H3.aspects.items():
    for edge in (384, 512, 640, 768, 896, 1024, 1536, 2048):
        width, height = canvas.resolve_canvas(ratio, edge, H3)
        cap = H3.native_max_pixels * (edge / H3.native_short_edge) ** 2
        if width % 32 or height % 32:
            FAILURES.append(f"{label} @{edge}: {width}x{height} is not a multiple of 32")
        if width * height > cap:
            FAILURES.append(f"{label} @{edge}: {width}x{height} exceeds the area cap")

# Ratios outside 21:9..9:16 clamp rather than stretch.
check("3:1 clamps", canvas.canvas_from_image(3000, 1000, 768, H3)[3], True)
check("1:3 clamps", canvas.canvas_from_image(1000, 3000, 768, H3)[3], True)
check("3:2 adaptive", canvas.canvas_from_image(1500, 1000, 768, H3)[:2], (1152, 768))

# --- duration ----------------------------------------------------------------

for seconds in range(H3.min_seconds, H3.max_seconds + 1):
    frames = canvas.frames_for_seconds(seconds, H3)
    if frames % 17 != 5:
        FAILURES.append(f"{seconds}s -> {frames} frames is not on the 17n+5 grid")
    if abs(canvas.seconds_for_frames(frames, H3) - seconds) > 0.36:
        FAILURES.append(f"{seconds}s -> {frames} frames drifts too far")

check("8s is exact", canvas.frames_for_seconds(8, H3), 192)
check("6s", canvas.frames_for_seconds(6, H3), 141)

# The offered range is wider than the trained one on purpose: 17n+5 is the only
# hard rule, and clips well past 15 s do generate. The pill says so; it does not
# refuse. So the ends have to be reachable and still legal.
check("a one-second shot is offered", canvas.frames_for_seconds(1, H3) % 17, 5)
check("...and is about a second", round(canvas.seconds_for_frames(canvas.frames_for_seconds(1, H3), H3), 2), 0.92)
check("a minute is reachable",
      round(canvas.seconds_for_frames(canvas.frames_for_seconds(60, H3), H3)), 60)
# Out of range clamps rather than raising — this is where a hand-edited blob and
# a workflow saved against an older ceiling both land somewhere legal.
check("past the ceiling clamps to the top",
      canvas.frames_for_seconds(999, H3), max(canvas.legal_frame_counts(H3)))
check("under the floor clamps to the bottom", canvas.frames_for_seconds(0, H3), 5)

check("the trained range is a subset, not the limit",
      (canvas.is_trained_length(124, H3), canvas.is_trained_length(362, H3),
       canvas.is_trained_length(107, H3), canvas.is_trained_length(379, H3)),
      (True, True, False, False))

# --- mode routing ------------------------------------------------------------

def build(prompt="", assets=(), **rest):
    data = {"prompt": prompt, "assets": list(assets), "duration_s": 6,
            "aspect": "16:9", "short_edge": 768}
    data.update(rest)
    return compiler.compile_request(data, image_size_lookup=lambda _f: (1500, 1000))


def image(handle, role="reference", **rest):
    return {"handle": handle, "kind": "image", "role": role, "filename": f"{handle}.png", **rest}


def video(handle, **rest):
    return {"handle": handle, "kind": "video", "role": "reference", "filename": f"{handle}.mp4", **rest}


def audio(handle, **rest):
    return {"handle": handle, "kind": "audio", "role": "reference", "filename": f"{handle}.wav", **rest}


check("text only", build().mode, "T2VA")
check("start only", build(assets=[image("img-1", "first_frame")]).mode, "I2VA")
check("end only", build(assets=[image("img-1", "last_frame")]).mode, "L2VA")
check("both frames", build(assets=[image("img-1", "first_frame"), image("img-2", "last_frame")]).mode, "FL2VA")
check("a reference", build(assets=[image("img-1")]).mode, "REF2VA")

# Muted, the way a LoRA is: attached, kept exactly as it was set up, and out of
# this run. Read here rather than filtered downstream, so the mode, the limits,
# the plan and the checkpoint pin are all derived from what is actually sent —
# a shot whose only reference is muted is a text generation, not a reference one
# that happens to encode nothing.
check("a muted reference is not a reference of this render",
      build(assets=[image("img-1", enabled=False)]).mode, "T2VA")
check("...nor of the checkpoint it would have pinned",
      build(assets=[image("img-1", enabled=False)]).checkpoint, "fl2va")
check("...and the live ones beside it still are",
      build(assets=[image("img-1", enabled=False), image("img-2")]).mode, "REF2VA")
check("...leaving only themselves out",
      [a.handle for a in build(assets=[image("img-1", enabled=False),
                                       image("img-2")]).ref_images], ["img-2"])
# A muted entry still owns its handle: unmuting it must not collide with a
# second @img-1 somebody attached while it was off.
expect_error("a muted handle is still taken",
             lambda: build(assets=[image("img-1", enabled=False), image("img-1")]),
             "duplicate asset handle @img-1")
# A keyframe is where the shot opens or closes rather than something the prompt
# reaches for, so there is nothing for it to be out of — and a blob that queued
# quietly without a frame the node still draws would be the worse answer.
# A muted reference is still on the node and still on screen, so the refusal for
# a sentence that cites one has to say which of the two things is wrong.
expect_error("a cited reference that is muted says so",
             lambda: build("a room with @img-2 on the table",
                           assets=[image("img-1"), image("img-2", enabled=False)]),
             "but it is muted")
expect_error("...and a citation of nothing still reads as nothing",
             lambda: build("a room with @img-2 on the table", assets=[image("img-1")]),
             "no such asset is attached")

expect_error("a keyframe cannot be muted",
             lambda: build(assets=[image("img-1", "first_frame", enabled=False)]),
             "only a reference can be muted")

check("t2va uses the fl2va model", build().checkpoint, "fl2va")
check("ref2va uses the ref model", build(assets=[image("img-1")]).checkpoint, "ref2va")

# --- checkpoint pinning ------------------------------------------------------
# The mode says how the request is encoded; the pin says which weights it runs
# on. Keyframes are a payload Ref2VA can also take, so that pin is honoured.

check("auto is the default", build().checkpoint_pinned, False)
check("auto is spelled out too", build(checkpoint="auto").checkpoint, "fl2va")
check("frames can be pinned to ref2va",
      build(assets=[image("img-1", "first_frame")], checkpoint="ref2va").checkpoint, "ref2va")
check("a pin is flagged as one",
      build(checkpoint="ref2va").checkpoint_pinned, True)
check("pinning what was already derived is not a pin",
      build(checkpoint="fl2va").checkpoint_pinned, False)
check("a pin does not change the encoding",
      build(assets=[image("img-1", "first_frame")], checkpoint="ref2va").mode, "I2VA")

# The reverse pin is honoured too: the slot names an input, not a training,
# and merges of the two checkpoints exist — the pin says what is loaded there.
check("references pinned to fl2va are honoured",
      build(assets=[image("img-1")], checkpoint="fl2va").checkpoint, "fl2va")
check("...and flagged as the divergent pin they are",
      build(assets=[image("img-1")], checkpoint="fl2va").checkpoint_pinned, True)
expect_error("an unknown checkpoint is refused",
             lambda: build(checkpoint="sdxl"), "unknown checkpoint")

# A pin moves the LoRAs and their trigger words with it: the words in the prompt
# have to name the weights that are actually patched.
check("a pin moves the trigger words",
      build("x", assets=[image("img-1", "first_frame")], checkpoint="ref2va",
            loras=[{"name": "a.safetensors", "modes": ["ref2va"], "triggers": ["ohwx"]}]).triggers,
      ["ohwx"])

# The image modes take their aspect from the keyframe, not the ratio pill.
adaptive = build(assets=[image("img-1", "first_frame")])
check("adaptive canvas", (adaptive.width, adaptive.height), (1152, 768))
check("adaptive flag", adaptive.ratio_from_image, True)
check("pill still rules ref2va", build(assets=[image("img-1")]).width, 1344)

# --- aspect source -----------------------------------------------------------
# Where the ratio comes from is a choice now, not only the rule: "pill" forces
# the preset even against a keyframe, and a handle adapts the canvas to any
# attached picture — a reference as much as a frame.

def build_sized(sizes, assets, **rest):
    data = {"prompt": "", "assets": list(assets), "duration_s": 6,
            "aspect": "16:9", "short_edge": 768, **rest}
    return compiler.compile_request(
        data, image_size_lookup=lambda f: sizes[f])

TALL, WIDE = (768, 1344), (1500, 1000)
sized = {"img-1.png": WIDE, "img-2.png": TALL, "vid-1.mp4": (1920, 1080)}

from_ref = build_sized(sized, [image("img-1", "first_frame"), image("img-2")],
                       aspect_source="img-2")
check("a reference image can set the canvas",
      (from_ref.width < from_ref.height, from_ref.ratio_from_image),
      (True, False))
check("a reference video can set the canvas",
      build_sized(sized, [image("img-2"), video("vid-1")],
                  aspect_source="vid-1").ratio, 1920 / 1080)
pilled = build_sized(sized, [image("img-1", "first_frame")], aspect_source="pill")
check("the pill can outrank a keyframe on purpose",
      ((pilled.width, pilled.height), pilled.ratio_from_image),
      ((1344, 768), False))
check("choosing the anchor itself is the auto rule",
      build_sized(sized, [image("img-1", "first_frame")],
                  aspect_source="img-1").ratio_from_image, True)
expect_error("a source that is not attached is refused",
             lambda: build_sized(sized, [image("img-1")], aspect_source="img-9"),
             "names nothing attached")
expect_error("a soundtrack has no aspect to give",
             lambda: build_sized(sized, [image("img-1"), audio("aud-1")],
                                 aspect_source="aud-1"),
             "no picture to take an aspect ratio from")

# Frames and references share a generation now: the frames ride as pinned
# guides on Ref2VA, exactly as a seam's inherited frame always has. The
# references keep their <Picture N>s (cached reference prompts stay
# byte-identical); the frames take the next ordinals and an alignment line.
both = build(assets=[image("img-1", "first_frame"), image("img-2")])
check("frames + refs are one REF2VA generation", both.mode, "REF2VA")
check("...on the ref2va weights", both.checkpoint, "ref2va")
check("the reference keeps its picture", both.labels["img-2"], "<Picture 1>")
check("the frame takes the next ordinal", both.labels["img-1"], "<Picture 2>")
check("the frame still anchors the canvas", both.ratio_from_image, True)
check("the prompt aligns the frame at its ordinal",
      "<Picture 2> (from [Shot 1]) aligns with the 0.00-second mark" in both.prompt, True)
ends = build(assets=[image("img-1", "first_frame"), image("img-3", "last_frame"),
                     image("img-2")])
check("an end frame rides along too", ends.labels["img-3"], "<Picture 3>")
check("...aligned at the far mark",
      "<Picture 3> (from [Shot 1]) aligns with the 5.88-second mark" in ends.prompt, True)

# --- label ordering (the contract encode.py walks) ---------------------------

full = build(assets=[
    image("img-1"), image("img-2"),
    video("vid-1", with_audio=True), video("vid-2"),
    audio("aud-1"),
])
check("picture 1", full.labels["img-1"], "<Picture 1>")
check("picture 2", full.labels["img-2"], "<Picture 2>")
check("video 1", full.labels["vid-1"], "<Video 1>")
check("video 2", full.labels["vid-2"], "<Video 2>")
# vid-1's soundtrack is presented before vid-1 itself, so it takes <Audio 1>
# and the standalone clip is pushed to <Audio 2>.
check("soundtrack audio", full.labels["vid-1:audio"], "<Audio 1>")
check("standalone audio", full.labels["aud-1"], "<Audio 2>")

# encode.py executes this plan verbatim, so its order *is* the payload order.
check("plan order",
      [(s["op"], s["asset"].handle, s["label"]) for s in full.plan],
      [("image", "img-1", "<Picture 1>"),
       ("image", "img-2", "<Picture 2>"),
       ("soundtrack", "vid-1", "<Audio 1>"),
       ("video", "vid-1", "<Video 1>"),
       ("video", "vid-2", "<Video 2>"),
       ("audio", "aud-1", "<Audio 2>")])
check("keyframe modes have no plan", build(assets=[image("img-1", "first_frame")]).plan, [])

frames_only = build(assets=[image("img-9", "first_frame"), image("img-4", "last_frame")])
check("first frame label", frames_only.labels["img-9"], "<Picture 1>")
check("last frame label", frames_only.labels["img-4"], "<Picture 2>")
check("lone last frame", build(assets=[image("img-4", "last_frame")]).labels["img-4"], "<Picture 1>")

# --- prompt substitution -----------------------------------------------------

check("substitution",
      build("keep @img-1 and the walk from @vid-1", [image("img-1"), video("vid-1")]).body,
      "keep <Picture 1> and the walk from <Video 1>")
check("prose survives", build("meet me @ 5 sharp").body, "meet me @ 5 sharp")
expect_error("dangling handle", lambda: build("use @img-7", [image("img-1")]), "no such asset")

# --- the Context-IR skeleton -------------------------------------------------
#
# `body` is what the user wrote; `prompt` is what the DiT reads. The gap between
# them is contextir.compose, and what matters is that it only ever *adds* — a
# prompt that already carries its own sections has to come through untouched, or
# a refiner's output would be silently rewritten.

def lora_entry(name, **rest):
    return {"name": name, "strength": 1.0, **rest}


t2va = build("a walk")
check("T2VA has no instruction line",
      t2va.prompt, "integrated_multimodal_description: [Shot 1] a walk")
check("...and an empty prompt composes to nothing", build("").prompt, "")

i2va = build("a walk", assets=[image("img-1", "first_frame")])
check("I2VA opens with the alignment instruction",
      i2va.prompt.splitlines()[0],
      "For the target video, at 0.00 seconds into the target video, "
      "<Picture 1> (from [Shot 1]) is fully referenced.")
check("...and the body follows as a field",
      i2va.prompt.endswith("integrated_multimodal_description: [Shot 1] a walk"), True)

# 6 s on the pill is 149 frames, which is 6.208333... s of video. The instruction
# states the *real* duration, because that is what the model aligns against.
l2va = build("a walk", assets=[image("img-1", "last_frame")])
check("L2VA states the true duration to two decimals",
      "aligns with the 5.88-second mark" in l2va.prompt, True)
check("...and the pill's whole number never appears",
      "6.00-second mark" in l2va.prompt, False)

fl2va = build("a walk", assets=[image("img-1", "first_frame"), image("img-2", "last_frame")])
check("FL2VA names both pictures",
      "Picture 1 (from Shot 1)" in fl2va.prompt and "Picture 2 (from Shot 1)" in fl2va.prompt,
      True)

# The end frame is reached by the *last* shot, and a lone generation now has more
# than one of them: the refiner divides a Creator clip into shots itself and
# stores the markers in the body. Counted off that body rather than assumed to be
# one, or a refined L2VA prompt would align its end frame against Shot 1 and
# claim the video arrives there before its first cut.
cut = build("", assets=[image("img-1", "last_frame")],
            refined={"body": "[Shot 1] a walk [Shot 2] At 00:03.000, the camera cuts to the door"})
check("a refined body's own shots are counted",
      "<Picture 1> (from [Shot 2])" in cut.prompt, True)
check("...and one that has none is still Shot 1",
      "<Picture 1> (from [Shot 1])" in
      build("", assets=[image("img-1", "last_frame")], refined={"body": "a walk"}).prompt, True)

# The instruction has to be the first line, so triggers go inside the body.
check("triggers land under the instruction, not above it",
      build("a walk", assets=[image("img-1", "first_frame")],
            loras=[lora_entry("a.safetensors", triggers=["ohwx"])]).prompt.splitlines()[0]
      .startswith("For the target video,"),
      True)
check("...and still lead the description",
      "integrated_multimodal_description: [Shot 1] ohwx, a walk"
      in build("a walk", assets=[image("img-1", "first_frame")],
               loras=[lora_entry("a.safetensors", triggers=["ohwx"])]).prompt,
      True)

sound = build("a walk", soundscape="rain on glass", music="slow piano")
check("the soundscape becomes its own field",
      "overall_soundscape: rain on glass" in sound.prompt, True)
check("the score becomes its own field",
      "non_diegetic_music: slow piano" in sound.prompt, True)
check("an empty audio field emits nothing at all",
      "overall_soundscape" in build("a walk", music="slow piano").prompt, False)
check("N/A is something you type, not something inferred",
      "non_diegetic_music: N/A" in build("a walk", music="N/A").prompt, True)
check("the fields come through onto Compiled", (sound.soundscape, sound.music),
      ("rain on glass", "slow piano"))

# A prompt that is already Context-IR — hand-written, or from a refiner — is its
# own rewrite and is left exactly as it is.
already = build("integrated_multimodal_description: [Shot 1] a walk\n\n"
                "overall_soundscape: wind only", soundscape="rain on glass")
check("an existing body field is not wrapped again",
      already.prompt.count("integrated_multimodal_description:"), 1)
check("...and an existing audio field is not duplicated",
      already.prompt.count("overall_soundscape:"), 1)
check("...so the user's own soundscape wins over the global one",
      "rain on glass" in already.prompt, False)

pre_aligned = build("For the target video, at 0.00 seconds into the target video, "
                    "<Picture 1> (from [Shot 1]) is fully referenced.\n\n"
                    "integrated_multimodal_description: [Shot 1] a walk",
                    assets=[image("img-1", "first_frame")])
check("an instruction the user wrote is not repeated",
      pre_aligned.prompt.count("For the target video,"), 1)

# A reference generation is written in the reference form whether or not anyone
# ran a refiner: the three sections are derived from the chips, and the body is
# wrapped in `detailed_description:` rather than in the base form's field.
ref = build("keep @img-1", [image("img-1")], soundscape="street noise")
check("a reference body is not in the base form's field",
      "integrated_multimodal_description" in ref.prompt, False)
check("...it is in the reference form's",
      "detailed_description: [Shot 1] keep <Picture 1>" in ref.prompt, True)
check("...but still gets its soundscape", "overall_soundscape: street noise" in ref.prompt, True)
check("...and no keyframe instruction", "For the target video," in ref.prompt, False)
check("...and the picture it was handed is defined",
      ref.prompt.startswith("subject_definitions: <Picture 1> is a reference picture."), True)

# The refiner writes `@handles` into the reference sections and the two audio
# fields exactly as it does into the body — that is how a rewrite survives an
# asset being added — so every one of those fields is substituted at queue time.
# Before this, a section reached the DiT saying `@img-1`, a token it has never
# seen, and the reference it named conditioned nothing.
sectioned = build("", [image("img-1"), audio("aud-1")],
                  soundscape="the song from @aud-1 fills the room",
                  music="",
                  refined={"body": "she sings, matching @img-1",
                           "sections": {"subject_definitions":
                                            "<Subject 1> is the woman in @img-1",
                                        "summary": "<Subject 1> sings @aud-1",
                                        "retention_analysis": "@img-1: fully_preserved"}})
check("a refined section's handles become labels",
      "<Subject 1> is the woman in <Picture 1>" in sectioned.prompt, True)
check("...in every section",
      "<Picture 1>: fully_preserved" in sectioned.prompt, True)
check("...and the summary's audio too", "<Subject 1> sings <Audio 1>" in sectioned.prompt, True)
check("the soundscape's handles become labels",
      "overall_soundscape: the song from <Audio 1> fills the room" in sectioned.prompt, True)
check("no handle survives into the DiT's prompt", "@img-1" in sectioned.prompt
      or "@aud-1" in sectioned.prompt, False)
expect_error("a dangling handle in the soundscape names the field",
             lambda: build("a walk", soundscape="the song from @aud-9"),
             "overall_soundscape references @aud-9")
expect_error("a dangling handle in a section names the section",
             lambda: build("", [image("img-1")],
                           refined={"body": "keep @img-1",
                                    "sections": {"subject_definitions": "from @vid-3",
                                                 "summary": "", "retention_analysis": ""}}),
             "subject_definitions references @vid-3")


# --- reference limits --------------------------------------------------------

expect_error("10 images", lambda: build(assets=[image(f"img-{i}") for i in range(10)]), "9 reference images")
expect_error("4 videos", lambda: build(assets=[video(f"vid-{i}") for i in range(4)]), "3 reference videos")
expect_error("audio alone", lambda: build(assets=[audio("aud-1")]), "at least one reference image or video")
expect_error("soundtracks count as audio",
             lambda: build(assets=[video(f"vid-{i}", with_audio=True) for i in range(3)] + [audio("aud-1")]),
             "3 reference audio")
expect_error("duplicate handles", lambda: build(assets=[image("img-1"), image("img-1")]), "duplicate")
# --- segments ----------------------------------------------------------------

check("no trim by default", build(assets=[video("vid-1")]).ref_videos[0].trim, None)
check("trim parsed",
      build(assets=[video("vid-1", trim={"start": 1, "end": 3.5})]).ref_videos[0].trim,
      (1.0, 3.5))
check("audio trims too",
      build(assets=[video("vid-1"), audio("aud-1", trim={"start": 0.5, "end": 2})]).ref_audios[0].trim,
      (0.5, 2.0))
expect_error("a still has no timeline",
             lambda: build(assets=[image("img-1", trim={"start": 0, "end": 1})]),
             "only video and audio")
expect_error("inverted trim",
             lambda: build(assets=[video("vid-1", trim={"start": 3, "end": 1})]),
             "start < end")
expect_error("negative trim",
             lambda: build(assets=[video("vid-1", trim={"start": -1, "end": 1})]),
             "start < end")
expect_error("non-numeric trim",
             lambda: build(assets=[video("vid-1", trim={"start": "soon", "end": 1})]),
             "numeric")
expect_error("half a trim",
             lambda: build(assets=[video("vid-1", trim={"start": 1})]),
             "numeric")

# --- video tracks ------------------------------------------------------------

check("default track", build(assets=[video("vid-1")]).ref_videos[0].track, "picture")
check("with_audio still reads as a track",
      build(assets=[video("vid-1", with_audio=True)]).ref_videos[0].track, "picture+sound")
check("an explicit track wins over with_audio",
      build(assets=[image("img-1"), video("vid-1", with_audio=True, track="sound")]).ref_audios[0].track,
      "sound")
expect_error("unknown track", lambda: build(assets=[video("vid-1", track="both")]), "unknown track")
expect_error("only video has a track",
             lambda: build(assets=[image("img-1"), audio("aud-1", track="sound")]),
             "only video has a track")

# A clip taken for its sound alone is an audio reference and nothing else: no
# <Video> label, no video slot, and the picture is never loaded.
sound_only = build(assets=[image("img-1"), video("vid-1", track="sound")])
check("sound-only takes no video slot", [a.handle for a in sound_only.ref_videos], [])
check("sound-only is an audio reference", [a.handle for a in sound_only.ref_audios], ["vid-1"])
check("sound-only label", sound_only.labels["vid-1"], "<Audio 1>")
check("sound-only plan",
      [(s["op"], s["asset"].handle) for s in sound_only.plan],
      [("image", "img-1"), ("audio", "vid-1")])
check("sound-only substitutes as audio",
      "detailed_description: [Shot 1] hum like <Audio 1>"
      in build("hum like @vid-1", [image("img-1"), video("vid-1", track="sound")]).prompt,
      True)

# It still cannot stand on its own: a soundtrack with no picture beside it is
# the same "audio is never a standalone reference" case as a bare .wav.
expect_error("sound-only is not a picture",
             lambda: build(assets=[video("vid-1", track="sound")]),
             "at least one reference image or video")
expect_error("sound-only counts against the audio slots",
             lambda: build(assets=[image("img-1")]
                           + [video(f"vid-{i}", track="sound") for i in range(3)]
                           + [audio("aud-1")]),
             "3 reference audio")
# Three of them is fine on its own, which is what makes the fourth the failure.
check("three sound-only clips fit",
      len(build(assets=[image("img-1")]
                + [video(f"vid-{i}", track="sound") for i in range(3)]).ref_audios), 3)
# The picture bucket is what they left: four would have broken the 3-video limit.
check("sound-only clips do not crowd the video slots",
      len(build(assets=[image("img-1"), video("vid-a"), video("vid-b"), video("vid-c"),
                        video("vid-d", track="sound")]).ref_videos), 3)

check("a sound-only clip can be trimmed",
      build(assets=[image("img-1"), video("vid-1", track="sound",
                                          trim={"start": 1, "end": 2})]).ref_audios[0].trim,
      (1.0, 2.0))

# --- reference size ----------------------------------------------------------
#
# The default is per kind, and both halves of it are the behaviour that shipped
# before video had the setting at all: an image with nothing said is encoded to
# the generation's pixel area, a video to core's 768 reference canvas. Getting
# this backwards would silently re-encode every existing video reference at a
# different size, so it is worth pinning.

check("an image defaults to match", build(assets=[image("img-1")]).ref_images[0].ref_size, "match")
check("a video defaults to max", build(assets=[video("vid-1")]).ref_videos[0].ref_size, "max")
check("an image can ask for max",
      build(assets=[image("img-1", ref_size="max")]).ref_images[0].ref_size, "max")
check("a video can ask for match",
      build(assets=[video("vid-1", ref_size="match")]).ref_videos[0].ref_size, "match")
# A clip taken for its sound has no picture to size, and lands in the audio
# bucket where nothing reads the field — but it must still parse.
check("a sound-only clip carries the video default",
      build(assets=[image("img-1"), video("vid-1", track="sound")]).ref_audios[0].ref_size, "max")
expect_error("unknown ref_size",
             lambda: build(assets=[image("img-1", ref_size="huge")]), "must be 'match' or 'max'")

# --- what a reference image takes --------------------------------------------
#
# "full" is the only behaviour that existed before the setting, so an old blob
# reads unchanged. The narrowing itself lives in the refiner's prose — the DiT
# is handed the same tensor either way — so all compile owes it is storage,
# validation, and refusal anywhere the field would quietly mean nothing.

check("a reference image defaults to the whole picture",
      build(assets=[image("img-1")]).ref_images[0].takes, "full")
check("a person reference is kept",
      build(assets=[image("img-1", takes="person")]).ref_images[0].takes, "person")
expect_error("unknown takes",
             lambda: build(assets=[image("img-1", takes="face")]), "takes must be one of")
expect_error("a keyframe cannot be narrowed",
             lambda: build(prompt="x", assets=[image("img-1", role="first_frame", takes="person")]),
             "used whole")

# --- and what a reference video takes -----------------------------------------
#
# The same field, four more values. They are roles H3's reference guide gives a
# clip rather than crops of it, so compile still only stores and validates —
# but the values a picture never had are refused on a picture, and a clip with
# no picture left to scope is refused all of them.

check("a reference video defaults to the whole clip",
      build(assets=[video("vid-1")]).ref_videos[0].takes, "full")
check("a camera reference is kept",
      build(assets=[video("vid-1", takes="camera")]).ref_videos[0].takes, "camera")
check("a motion reference is kept",
      build(assets=[video("vid-1", takes="motion")]).ref_videos[0].takes, "motion")
check("a clip can be narrowed the way a picture can",
      build(assets=[video("vid-1", takes="person")]).ref_videos[0].takes, "person")
expect_error("a video's takes must be one of its own",
             lambda: build(assets=[video("vid-1", takes="storyboard")]),
             "takes must be one of")
expect_error("a picture has no camera to take",
             lambda: build(assets=[image("img-1", takes="camera")]), "takes must be one of")

# --- and what a reference audio takes -----------------------------------------
#
# The guide's own audio roles, and the split that decides both the task-type
# prefix and the retention marker: a signal copied outright against one only
# referenced. A clip taken for its soundtrack alone scopes here rather than with
# the pictures — it arrives in `ref_audios` and its picture is never encoded, so
# the picture vocabulary would narrow a file that is not there.

check("a reference audio clip defaults to the whole signal",
      build(assets=[image("img-1"), audio("aud-1")]).ref_audios[0].takes, "full")
check("a voice reference is kept",
      build(assets=[image("img-1"), audio("aud-1", takes="voice")]).ref_audios[0].takes, "voice")
check("a copied signal is kept",
      build(assets=[image("img-1"), audio("aud-1", takes="copy")]).ref_audios[0].takes, "copy")
check("a sound-only clip scopes as the audio it has become",
      build(assets=[image("img-1"),
                    video("vid-1", track="sound", takes="music")]).ref_audios[0].takes,
      "music")
expect_error("a sound-only clip has no picture left to narrow",
             lambda: build(assets=[image("img-1"), video("vid-1", track="sound", takes="motion")]),
             "takes must be one of")
expect_error("audio has no person in it to take",
             lambda: build(assets=[image("img-1"), audio("aud-1", takes="person")]),
             "takes must be one of")
expect_error("a keyframe is still refused outright",
             lambda: build(prompt="x", assets=[image("img-1", role="last_frame", takes="style")]),
             "used whole")

# --- saying what each reference is, for the model -----------------------------
#
# `takes` used to be read by the refiner's glossary and by nothing else, so a
# piece queued without a rewrite had the dial quietly do nothing. It is written
# into the prompt as prose now — the only place H3 can carry it, since the DiT
# is handed the same tensor either way — and unconditionally, because a label
# the prompt never defines is a label pointing at nothing.
#
# A floor, like the rest of `contextir`: dropped the moment a refiner has
# written the real sections.

def defined(prompt="", assets=(), **rest):
    data = {"prompt": prompt, "assets": list(assets), "duration_s": 6,
            "aspect": "16:9", "short_edge": 768}
    data.update(rest)
    return compiler.compile_request(
        data, image_size_lookup=lambda _f: (1500, 1000))


check("a reference's scope is stated without anyone asking for it",
      "is a person reference" in build("a walk", [image("img-1", takes="person")]).prompt,
      True)

person = defined("a walk", [image("img-1", takes="person")])
check("on, the picture's scope is stated in the prompt",
      "<Picture 1> is a person reference:" in person.prompt, True)
check("...saying what is retained",
      "face, hair, skin, build and clothing in it are retained" in person.prompt, True)
check("...and what is not",
      "background, palette, lighting, pose and action are not" in person.prompt, True)
check("...ahead of the description, where subject_definitions goes",
      person.prompt.index("is a person reference")
      < person.prompt.index("detailed_description:")
      if "detailed_description:" in person.prompt
      else person.prompt.index("is a person reference") < person.prompt.index("a walk"),
      True)

check("an un-narrowed picture is still named, so its label points at something",
      "<Picture 1> is a reference picture." in defined("a walk", [image("img-1")]).prompt,
      True)

check("a camera reference says nobody in the clip appears",
      "nobody and nothing visible in the clip appears in the target video"
      in defined("a walk", [video("vid-1", takes="camera")]).prompt, True)
# Section 2.3's definition form, not the summary's opening sentence. Those are
# different sections saying different things — what the label *is*, against what
# the target video is — and borrowing the second for the first said "the target
# video is an edited version of" once per source clip.
check("an edit is defined as a source video",
      "<Video 1> is a source video for the target video edit."
      in defined("a walk", [video("vid-1", takes="edit")]).prompt, True)
check("...and the summary is where the target video is called an edit of it",
      "summary: [video editing] The target video is an edited version of <Video 1>."
      in defined("a walk", [video("vid-1", takes="edit")]).prompt, True)
check("a continuation names the clip it picks up from",
      "<Video 1> is the source video the target video continues from."
      in defined("a walk", [video("vid-1", takes="continue")]).prompt, True)
check("a voice reference binds timbre and refuses the words",
      "its words and its background sound are not copied"
      in defined("a walk", [image("img-1"), audio("aud-1", takes="voice")]).prompt, True)
check("a copied signal says it is the target's own audio",
      "<Audio 1> is reused directly" in
      defined("a walk", [image("img-1"), audio("aud-1", takes="copy")]).prompt, True)

# --- the task-type prefix and the summary -------------------------------------
#
# Section 3's table, read backwards: the prefix is a restatement of what the
# chips already say, not a judgement about the piece. It used to be the
# refiner's alone, so a piece queued without a rewrite shipped five of the six
# sections and left the model to work out what kind of job it was.

prefix = lambda compiled: compiled.prompt.split("summary: ")[1].split("]")[0] + "]"

check("references alone are a reference generation",
      prefix(defined("a walk", [image("img-1", takes="person")])), "[reference generation]")
# The guide says this one outright: a clip lending only its camera is reference
# generation, not video editing.
check("a camera reference is still only a reference generation",
      prefix(defined("a walk", [video("vid-1", takes="camera")])), "[reference generation]")
check("an edited clip makes it a video edit",
      prefix(defined("a walk", [video("vid-1", takes="edit")])), "[video editing]")
check("a continued clip makes it a continuation",
      prefix(defined("a walk", [video("vid-1", takes="continue")])), "[video continuation]")
check("a copied signal adds audio reuse",
      prefix(defined("a walk", [image("img-1"), audio("aud-1", takes="copy")])),
      "[reference generation + audio reuse]")
check("...and a referenced one adds audio reference instead",
      prefix(defined("a walk", [image("img-1"), audio("aud-1", takes="voice")])),
      "[reference generation + audio reference]")
# Whole-video relationships lead, then generation, then the frames — the order
# of the guide's own two worked examples.
check("several relationships combine in the guide's order, with no repeats",
      prefix(defined("a walk", [image("img-1", takes="person"),
                                video("vid-1", takes="edit"),
                                video("vid-2", takes="camera")])),
      "[video editing + reference generation]")
# A frame riding along in a reference generation is keyframe completion too.
check("a start frame adds keyframe completion",
      prefix(defined("a walk", [image("img-1", takes="person"),
                                image("key-1", role="first_frame")])),
      "[reference generation + keyframe completion]")

check("the summary counts the shots it is summarising",
      "The target video runs one shot."
      in defined("a walk", [image("img-1", takes="person")]).prompt, True)

# The ordinals come off `plan_references`, so the prose and the payload cannot
# disagree about which file is which.
two = defined("a walk", [image("img-1", takes="style"), image("img-2", takes="person"),
                         video("vid-1", takes="motion")])
check("every label is defined, in the order the tokenizer is shown them",
      [line for line in ("<Picture 1> is a style reference",
                         "<Picture 2> is a person reference",
                         "<Video 1> is a motion reference")
       if line in two.prompt],
      ["<Picture 1> is a style reference", "<Picture 2> is a person reference",
       "<Video 1> is a motion reference"])

# A clip with its soundtrack is two labels for one file, and the audio one is not
# addressable by handle — so its line names the clip it came off.
sound = defined("a walk", [video("vid-1", track="picture+sound", takes="camera")])
check("a soundtrack's label is defined against its clip",
      "<Audio 1> is the synchronized audio track of <Video 1>." in sound.prompt, True)

# The one thing that must not happen: two descriptions of the same reference.
refined = defined("a walk", [image("img-1", takes="person")], refined={
    "enabled": True, "body": "a woman walks", "sections": {
        "subject_definitions": "<Subject 1> is the woman in @img-1.",
        "summary": "[reference generation] She walks.",
        "retention_analysis": "<Subject 1>: fully_preserved - her likeness is retained."}})
check("a refined reference form defines its own labels, so nothing is added",
      "is a person reference" in refined.prompt, False)
check("...and the refiner's own definition is what is queued",
      "subject_definitions: <Subject 1> is the woman in <Picture 1>." in refined.prompt, True)

check("a keyframe is left to the alignment instruction",
      "is a reference picture" in defined("a walk", [image("img-1", role="first_frame")]).prompt,
      False)


# --- loras and trigger words -------------------------------------------------

def lora(name, **rest):
    return {"name": name, "strength": 1.0, **rest}


check("no loras, no prefix", build("a walk").body, "a walk")
check("triggers prefix the prompt",
      build("a walk", loras=[lora("a.safetensors", triggers=["ohwx", "cinematic"])]).body,
      "ohwx, cinematic, a walk")
check("triggers survive an empty prompt",
      build("", loras=[lora("a.safetensors", triggers=["ohwx"])]).body,
      "ohwx")
check("triggers are exposed, not only inlined",
      build("x", loras=[lora("a.safetensors", triggers=["ohwx"])]).triggers,
      ["ohwx"])

# Order is list order; a word two LoRAs share is weighted once, not twice.
check("triggers dedupe case-insensitively",
      build("x", loras=[lora("a.safetensors", triggers=["ohwx", "Film"]),
                        lora("b.safetensors", triggers=["FILM", "grain"])]).triggers,
      ["ohwx", "Film", "grain"])

# A LoRA that is not in the run contributes neither weights nor words. Both
# sides read `active_loras`, so these cannot drift apart.
check("the other checkpoint's triggers stay out",
      build("x", loras=[lora("a.safetensors", modes=["ref2va"], triggers=["ohwx"])]).triggers,
      [])
check("...and come back in ref2va",
      build("x", assets=[image("img-1")],
            loras=[lora("a.safetensors", modes=["ref2va"], triggers=["ohwx"])]).triggers,
      ["ohwx"])
check("disabled contributes nothing",
      build("x", loras=[lora("a.safetensors", enabled=False, triggers=["ohwx"])]).triggers, [])
check("zero strength contributes nothing",
      build("x", loras=[lora("a.safetensors", strength=0, triggers=["ohwx"])]).triggers, [])
check("blank words are dropped",
      build("x", loras=[lora("a.safetensors", triggers=["  ", "ohwx "])]).triggers, ["ohwx"])

check("no modes means both",
      compiler.lora_modes({"name": "a"}), ("fl2va", "ref2va"))
check("a nonsense mode falls back to both",
      compiler.lora_modes({"name": "a", "modes": ["sdxl"]}), ("fl2va", "ref2va"))
check("active order is list order",
      [e["name"] for e in compiler.active_loras(
          [lora("b.safetensors"), lora("a.safetensors")], "fl2va")],
      ["b.safetensors", "a.safetensors"])

# Substitution runs first, so a label can never end up inside the prefix.
check("triggers do not disturb labels",
      build("keep @img-1", [image("img-1")],
            loras=[lora("a.safetensors", modes=["ref2va"], triggers=["ohwx"])]).body,
      "ohwx, keep <Picture 1>")

expect_error("non-numeric strength",
             lambda: build("x", loras=[lora("a.safetensors", strength="hard")]),
             "strength must be a number")

expect_error("video as a keyframe",
             lambda: build(assets=[{"handle": "vid-1", "kind": "video", "role": "first_frame", "filename": "v.mp4"}]),
             "only images")

# --- timeline ----------------------------------------------------------------
#
# A segment is a whole generation, so most of the surface above already covers
# it. What is new is only the three things the timeline owns: the inherited
# prompt, the shared canvas, and continuation.


def timeline(segments, prompt="", **rest):
    return compiler.compile_timeline({"segments": segments, "prompt": prompt, **rest})


def segment(prompt="", **rest):
    return {"prompt": prompt, "assets": [], "loras": [], "duration_s": 6, **rest}


chain = timeline([segment("wide shot"), segment("closer", **{"continue": True})], prompt="a red room")

check("the global prompt leads each segment", chain[0].body, "a red room\nwide shot")
check("...and the continuing one too", chain[1].body, "a red room\ncloser")
check("an empty global prompt adds no blank line",
      timeline([segment("only mine")])[0].body, "only mine")
check("an empty segment prompt adds no blank line",
      timeline([segment()], prompt="only global")[0].body, "only global")

check("segment 1 cannot continue", chain[0].continues, False)
check("segment 1 is text-only", chain[0].mode, "T2VA")
check("continuing is a keyframe generation", chain[1].mode, "I2VA")
check("...on the fl2va checkpoint", chain[1].checkpoint, "fl2va")
check("the flag survives compilation", chain[1].continues, True)
check("a continuation flag on segment 1 is ignored, not refused",
      timeline([segment(**{"continue": True})])[0].mode, "T2VA")

# The seam's named source — 1-based on the segment because that is the number
# on the card, 0-based on the payload because that is what the emitter joins
# on. Only a source before the previous segment is worth writing down.
def payload_sources(segments):
    return [p.get("continue_from")
            for p in compiler.timeline_payloads({"segments": segments})]

check("a named source lands on the payload, 0-based",
      payload_sources([segment(), segment(),
                       segment(**{"continue": True, "continue_from": 1})]),
      [None, None, 0])
check("naming the previous segment is the default, said out loud",
      payload_sources([segment(), segment(),
                       segment(**{"continue": True, "continue_from": 2})]),
      [None, None, None])
check("an out-of-range source falls back to the previous segment",
      payload_sources([segment(), segment(**{"continue": True, "continue_from": 7})]),
      [None, None])
check("a source without a live seam writes nothing",
      payload_sources([segment(), segment(), segment(**{"continue_from": 1})]),
      [None, None, None])
check("the sound seam names a source the same way",
      payload_sources([segment(), segment(),
                       segment(**{"continue_audio": True, "continue_from": 1})]),
      [None, None, 0])
check("the source never reaches the request",
      "continue_from" in compiler.timeline_payloads(
          {"segments": [segment(), segment(),
                        segment(**{"continue": True, "continue_from": 1})]})[2]["request"],
      False)

check("an end frame makes a continuing segment FL2VA",
      timeline([segment(), segment(**{
          "continue": True,
          "assets": [{"handle": "img-1", "kind": "image", "role": "last_frame", "filename": "b.png"}],
      })])[1].mode,
      "FL2VA")
# The inherited frame has no handle but still takes <Picture 1>, so the end frame
# has to be <Picture 2> or the prompt binds to the wrong tensor.
check("the inherited frame consumes <Picture 1>",
      timeline([segment(), segment("end on @img-1", **{
          "continue": True,
          "assets": [{"handle": "img-1", "kind": "image", "role": "last_frame", "filename": "b.png"}],
      })])[1].body,
      "end on <Picture 2>")

# Every segment is concatenated with the others at the end, which is only
# defined if they all came out the same size.
wide = timeline([segment(), segment(), segment()], aspect="9:16", short_edge=512)
check("one canvas across the timeline",
      {(c.width, c.height) for c in wide}, {canvas.resolve_canvas(9 / 16, 512, H3)})

# A continuing segment with references: the seam rides as pinned guides that
# payload.py places on the segment's own timeline, so the checkpoint choice no
# longer forbids the combination — REF2VA carries the seam.
referenced_seam = timeline([segment(), segment("with @img-1", **{
    "continue": True, "continue_audio": True,
    "assets": [{"handle": "img-1", "kind": "image", "role": "reference", "filename": "a.png"}],
})])
check("a continuing segment with references compiles as REF2VA",
      referenced_seam[1].mode, "REF2VA")
check("...and keeps both seam flags",
      (referenced_seam[1].continues, referenced_seam[1].continues_audio), (True, True))
check("...on the ref2va checkpoint", referenced_seam[1].checkpoint, "ref2va")
expect_error("a start frame in a continuing segment",
             lambda: timeline([segment(), segment(**{
                 "continue": True,
                 "assets": [{"handle": "img-1", "kind": "image", "role": "first_frame", "filename": "a.png"}],
             })]),
             "already the source segment")

# --- the feather -------------------------------------------------------------
#
# How many of the source's last frames the seam inherits. Values off the video
# VAE's temporal grid cannot be encoded standalone and are refused; a feather
# on a hard cut is a leftover and is dropped, like the other seam keys.

feathered = timeline([segment(), segment("closer", **{"continue": True, "feather": 22})])
check("a feathered seam survives compilation", feathered[1].feather, 22)
check("an unfeathered seam is the classic single frame",
      timeline([segment(), segment(**{"continue": True})])[1].feather, 1)
check("a feather on a hard cut is dropped, not refused",
      timeline([segment(), segment(**{"feather": 22})])[1].feather, 1)
check("a feathered tail is clamped to the overlap",
      timeline([segment(), segment(**{"continue": True, "continue_audio": True,
                                      "feather": 22})], audio_tail_s=4.0)[1].audio_tail_s,
      22 / 24)
check("a classic seam's tail is not",
      timeline([segment(), segment(**{"continue": True, "continue_audio": True})],
               audio_tail_s=4.0)[1].audio_tail_s,
      4.0)
check("the seam line rides a classic sound seam's prompt",
      "<Audio 1> is the end of the preceding shot's soundtrack"
      in timeline([segment(), segment(**{"continue": True, "continue_audio": True})])[1].prompt,
      True)
# A blended sound seam pins its tail on this segment's own timeline instead of
# sending it as a reference, so it takes no <Audio N> and the prompt carries no
# line naming one. Asserted about the line itself: this used to compare the
# whole prompt against an unblended seam's, which stopped being one difference
# the moment a blended seam also stopped presenting its boundary picture.
check("a feathered seam's tail rides unlabelled — no seam line",
      "<Audio 1> is the end of the preceding shot's soundtrack"
      in timeline([segment(), segment(**{"continue": True, "continue_audio": True,
                                         "feather": 22})])[1].prompt,
      False)

# And the picture half of the same rule. An unblended seam's boundary frame *is*
# the seam, so it is presented and the alignment line names it; a blended one
# hands the run to the DiT and tells the text encoder nothing, unless asked.
# Presenting it said "arrive at exactly this still" over a run of motion that
# merely ends on it — and `_encode_references` never did, so the two encode
# roads conditioned the same seam differently.
blended = timeline([segment(), segment(**{"continue": True, "feather": 22})])[1]
classic = timeline([segment(), segment(**{"continue": True})])[1]
pinned = timeline([segment(), segment(**{"continue": True, "feather": 22,
                                         "feather_pin": True})])[1]
check("an unblended seam names its frame", classic.presents_head_frame, True)
check("...and the prompt says where it aligns",
      "<Picture 1>" in classic.prompt, True)
check("a blended seam names nothing by default", blended.presents_head_frame, False)
check("...so the prompt claims no picture", "Picture 1" in blended.prompt, False)
check("...and pinning it puts both back",
      (pinned.presents_head_frame, "<Picture 1>" in pinned.prompt), (True, True))
check("the pin is inert without a blend to modify",
      timeline([segment(), segment(**{"continue": True, "feather_pin": True})])[1].feather_pin,
      False)

# And the rule that holds over both of them: on a reference generation the
# ordinals are the references', so the base modes' alignment line must not be
# written at all. It names <Picture 1> as the frame the target opens on, and
# <Picture 1> there is the first *reference* — the seam is never presented on
# that road (`encode._encode_references`) and an attached start frame is
# presented after the references, already named by the alignment preamble at
# the ordinal it really took. Composed as a keyframe mode, a chained cast shot
# told the model to open on the character sheet while the DiT held the previous
# pass's own frames as pinned guides.
OPENS_ON = "For the target video, at 0.00 seconds into the target video"
cast_seam = timeline([segment(), segment("keep @img-1", **{"continue": True,
                                                           "assets": [image("img-1")]})])[1]
check("a chained reference segment is REF2VA", cast_seam.mode, "REF2VA")
check("...and claims to open on no reference", OPENS_ON in cast_seam.prompt, False)
cast_start = build("keep @img-1", [image("img-1"), image("st-1", "first_frame")])
check("a reference generation with a start frame is REF2VA too", cast_start.mode, "REF2VA")
check("...and states its alignment once, at the ordinal the frame took",
      (OPENS_ON in cast_start.prompt,
       "<Picture 2> (from [Shot 1]) aligns with the 0.00-second mark" in cast_start.prompt),
      (False, True))
expect_error("a feather off the VAE grid",
             lambda: timeline([segment(), segment(**{"continue": True, "feather": 10})]),
             "not 10")
expect_error("a feather wider than the clip affords",
             lambda: timeline([segment(**{"duration_s": 6}),
                               segment(**{"duration_s": 1, "continue": True, "feather": 39})]),
             "at least 78 frames")
expect_error("errors name the segment",
             lambda: timeline([segment(), segment(**{"duration_s": 6, "checkpoint": "nope"})]),
             "segment 2")
expect_error("an empty timeline", lambda: timeline([]), "nothing on it")
expect_error("too many segments",
             lambda: timeline([segment()] * (compiler.MAX_SEGMENTS + 1)),
             "at most")

# --- what bounds a timeline --------------------------------------------------
#
# Cards do not measure work and neither do passes; frames do. These are the
# assertions that keep `MAX_SEGMENTS` from drifting back into being read as a
# work bound — mutate `timeline_frames` to sum cards instead of passes and the
# first one fails, which is the whole point of it.

# Three five-second cards merged into one pass are one 362-frame generation, not
# three 124-frame ones. Summing the cards would be wrong by the rounding on each.
merged_run = {"segments": [segment(**{"duration_s": 5}),
                           segment(**{"duration_s": 5, "merge": True}),
                           segment(**{"duration_s": 5, "merge": True})]}
check("a merged pass is snapped once, not per card",
      compiler.timeline_frames(merged_run), canvas.frames_for_seconds(15, H3))
check("...which is not what the cards sum to",
      compiler.timeline_frames(merged_run) == 3 * canvas.frames_for_seconds(5, H3), False)

check("an unmerged strip snaps every card",
      compiler.timeline_frames({"segments": [segment(**{"duration_s": 5})] * 3}),
      3 * canvas.frames_for_seconds(5, H3))

# A feathered seam re-generates its inherited run and the reel node drops it, so those
# frames are sampled but never delivered — and the finished length has to say so.
feathered = {"segments": [segment(),
                          segment(**{"continue": True, "feather": 22})]}
check("a feathered seam costs the finished clip its overlap",
      compiler.timeline_frames(feathered), 2 * canvas.frames_for_seconds(6, H3) - 22)
check("...and an unfeathered one costs nothing",
      compiler.timeline_frames({"segments": [segment(), segment(**{"continue": True})]}),
      2 * canvas.frames_for_seconds(6, H3))

# The work bound itself. Long cards rather than many, precisely because the old
# cap could not see this case: well inside MAX_SEGMENTS, hours of video.
expect_error("a timeline past the frame budget",
             lambda: timeline([segment(**{"duration_s": 60})] * 40),
             "will not queue more than")
check("...and one inside it compiles",
      len(timeline([segment(**{"duration_s": 60})] * 25)), 25)

# --- timeline globals --------------------------------------------------------
#
# Three things the timeline owns on top of the prompt and the canvas: the LoRAs
# every segment is patched with, and the two audio fields. All three exist for
# the same reason — a turbo LoRA, a room tone and a score are properties of the
# piece, and setting them shot by shot is how they drift apart.

turbo = lora_entry("turbo.safetensors", triggers=["fast"])

globals_chain = timeline([segment("wide"), segment("close")], loras=[turbo])
check("a global LoRA reaches segment 1", globals_chain[0].triggers, ["fast"])
check("...and segment 2", globals_chain[1].triggers, ["fast"])

mixed = timeline([segment("wide", loras=[lora_entry("shot.safetensors", triggers=["grain"])])],
                 loras=[turbo])
check("global words lead the segment's own", mixed[0].triggers, ["fast", "grain"])

# A segment naming the same file replaces the global entry rather than stacking
# the same weights twice at two strengths.
override = compiler.merge_loras(
    [lora_entry("turbo.safetensors", strength=1.0)],
    [lora_entry("turbo.safetensors", strength=0.4)])
check("a segment's entry replaces the global one",
      [(e["name"], e["strength"]) for e in override], [("turbo.safetensors", 0.4)])
check("an unrelated global entry survives beside it",
      [e["name"] for e in compiler.merge_loras([turbo], [lora_entry("b.safetensors")])],
      ["turbo.safetensors", "b.safetensors"])
check("no globals is just the segment's list",
      [e["name"] for e in compiler.merge_loras(None, [lora_entry("b.safetensors")])],
      ["b.safetensors"])

sound_chain = timeline([segment("wide"), segment("close")],
                       soundscape="rain on glass", music="slow piano")
check("the soundscape reaches every segment",
      ["overall_soundscape: rain on glass" in c.prompt for c in sound_chain], [True, True])
check("...and so does the score",
      ["non_diegetic_music: slow piano" in c.prompt for c in sound_chain], [True, True])

# A shot that genuinely sounds different can still say so; an empty field is
# inheritance, not a clearing.
per_shot = timeline([segment("wide"), segment("close", soundscape="underwater")],
                    soundscape="rain on glass")
check("a segment can override the soundscape", per_shot[1].soundscape, "underwater")
check("...without disturbing the others", per_shot[0].soundscape, "rain on glass")
check("an empty segment field inherits", per_shot[1].music, "")

# --- the sound seam ----------------------------------------------------------
#
# The previous segment's audio tail rides in as a `ref_audio` block, which the
# FL2VA weights read even though their documented inputs are text and frames.
# Independent of the picture seam in both directions.

sound_seam = timeline([segment("wide"), segment("close", **{"continue_audio": True})])
check("the sound seam is off by default", sound_seam[0].continues_audio, False)
check("...and on where it was set", sound_seam[1].continues_audio, True)
check("the picture is not dragged along with it", sound_seam[1].continues, False)
check("a sound-only seam is still T2VA", sound_seam[1].mode, "T2VA")
check("the inherited tail gets a label the prompt defines",
      "<Audio 1> is the end of the preceding shot's soundtrack" in sound_seam[1].prompt, True)
check("...and nothing says so where the seam is silent",
      "<Audio 1>" in sound_seam[0].prompt, False)

both = timeline([segment(), segment(**{"continue": True, "continue_audio": True})])
check("picture and sound can cross the same seam",
      (both[1].continues, both[1].continues_audio), (True, True))
check("...which is still an I2VA generation", both[1].mode, "I2VA")

check("segment 1 has no seam to carry sound over",
      timeline([segment(**{"continue_audio": True})])[0].continues_audio, False)

check("the tail defaults to the documented length",
      sound_seam[1].audio_tail_s, compiler.DEFAULT_AUDIO_TAIL_S)
check("...is the timeline's to set",
      timeline([segment(), segment(**{"continue_audio": True})], audio_tail_s=2.5)[1].audio_tail_s,
      2.5)
check("...clamps rather than sending an unpayable one",
      timeline([segment(), segment(**{"continue_audio": True})], audio_tail_s=99)[1].audio_tail_s,
      compiler.MAX_AUDIO_TAIL_S)
check("a silent seam carries no tail at all", sound_seam[0].audio_tail_s, 0.0)

expect_error("a negative tail",
             lambda: timeline([segment(), segment(**{"continue_audio": True})], audio_tail_s=-1),
             "greater than 0")
expect_error("a non-numeric tail",
             lambda: timeline([segment(), segment(**{"continue_audio": True})], audio_tail_s="long"),
             "must be a number")

# The inherited sound rides after the reference plan's own blocks, unlabelled,
# so a reference segment's sound seam is an ordinary thing now.
check("the sound seam on a reference segment compiles",
      timeline([segment(), segment(**{
          "continue_audio": True,
          "assets": [{"handle": "img-1", "kind": "image", "role": "reference",
                      "filename": "a.png"}],
      })])[1].continues_audio,
      True)

# A lone request is unchanged by any of this.
check("compile_request still defaults to not continuing", build("x").continues, False)


# --- the reference pool --------------------------------------------------------
#
# Assets attached to the timeline itself, injected into exactly the segments
# whose own text cites their handle. The cite-gating is the load-bearing part:
# an uncited pool must leave every payload byte-identical to a pool-less one,
# or the cache re-renders segments nobody touched.

sheet = {"handle": "ref-1", "kind": "image", "role": "reference", "filename": "sheet.png"}

pooled = timeline([segment("wide shot"), segment("she turns, @ref-1")], assets=[sheet])
check("a cited pool reference rides into the citing segment",
      [a.filename for a in pooled[1].ref_images], ["sheet.png"])
check("...as an ordinary reference generation", pooled[1].mode, "REF2VA")
check("...with its label substituted", pooled[1].body, "she turns, <Picture 1>")
check("a segment that cites nothing carries nothing",
      (pooled[0].mode, pooled[0].ref_images), ("T2VA", []))

# The injected asset leads the segment's own, so a shared reference keeps the
# low ordinal wherever the citing sets agree.
led = timeline([segment("@ref-1 beside @img-1", assets=[
    {"handle": "img-1", "kind": "image", "role": "reference", "filename": "own.png"},
])], assets=[sheet])
check("the pool leads the segment's own references",
      led[0].body, "<Picture 1> beside <Picture 2>")

check("a segment's own handle shadows the pool's",
      timeline([segment("keep @ref-1", assets=[
          {"handle": "ref-1", "kind": "image", "role": "reference", "filename": "mine.png"},
      ])], assets=[sheet])[0].ref_images[0].filename,
      "mine.png")

check("a citation in the refined body counts",
      timeline([segment("plain", refined={"body": "her from @ref-1", "scope": "shot"})],
               assets=[sheet])[0].mode,
      "REF2VA")
check("a citation in the segment's own soundscape counts",
      timeline([segment("plain", soundscape="the room from @ref-1... hums",
                        assets=[{"handle": "img-1", "kind": "image",
                                 "role": "reference", "filename": "a.png"}])],
               assets=[sheet])[0].ref_images[0].filename,
      "sheet.png")

# Cache stability: an uncited pool changes nothing about the payloads at all.
plain_segments = [segment("wide"), segment("close")]
check("an uncited pool leaves every payload byte-identical",
      compiler.timeline_payloads({"segments": plain_segments}),
      compiler.timeline_payloads({"segments": plain_segments, "assets": [sheet]}))

# A citation in the global prompt is a citation in every segment — the join
# carries it in front of each one, so a sheet cited there rides everywhere
# without a per-segment mention. The attach-once gesture.
everywhere = timeline([segment("wide"), segment("close")],
                      prompt="the piece follows @ref-1", assets=[sheet])
check("a global citation reaches every segment",
      [c.mode for c in everywhere], ["REF2VA", "REF2VA"])
check("...carrying the file into each",
      [[a.filename for a in c.ref_images] for c in everywhere],
      [["sheet.png"], ["sheet.png"]])
check("...with the label substituted in the join",
      everywhere[0].body, "the piece follows <Picture 1>\nwide")

check("the global soundscape's citation inherits the same way",
      timeline([segment("x")], soundscape="hums like @ref-1",
               assets=[sheet])[0].ref_images[0].filename,
      "sheet.png")
check("...but not into a segment that writes its own soundscape",
      timeline([segment("x", soundscape="underwater")],
               soundscape="hums like @ref-1", assets=[sheet])[0].ref_images,
      [])

# A global citation rides into a keyframe segment too, now that frames and
# references share a generation: the segment becomes REF2VA and its frame
# rides as a pinned guide.
global_keyframe = timeline([segment("open", assets=[
    {"handle": "img-1", "kind": "image", "role": "first_frame",
     "filename": "a.png"}])],
    prompt="the piece follows @ref-1", assets=[sheet])
check("a global citation rides into a keyframe segment",
      global_keyframe[0].mode, "REF2VA")
check("...keeping the frame", global_keyframe[0].first_frame.handle, "img-1")

expect_error("a pool keyframe is refused",
             lambda: timeline([segment("x")], assets=[
                 {"handle": "ref-1", "kind": "image", "role": "first_frame",
                  "filename": "a.png"}]),
             "belongs to one segment")
cited_keyframe = timeline([segment("open on @ref-1", assets=[
    {"handle": "img-1", "kind": "image", "role": "first_frame",
     "filename": "a.png"}])], assets=[sheet])
check("a keyframe segment citing the pool runs as REF2VA",
      cited_keyframe[0].mode, "REF2VA")
check("...with the sheet injected and the frame kept",
      ([a.filename for a in cited_keyframe[0].ref_images],
       cited_keyframe[0].first_frame.filename),
      (["sheet.png"], "a.png"))


# ---- one pass ---------------------------------------------------------------
#
# The same timeline read as the shots of a single generation. The assertions
# worth keeping are the ones about *merging*: handles are allocated per segment,
# so the same handle means different files in different shots and the same file
# wears different handles — and if the merge gets that wrong, the labels bind to
# the wrong tensors and, as everywhere else in this module, nothing raises.


def single(segments, **rest):
    return compiler.compile_single({"segments": segments, **rest},
                                   image_size_lookup=lambda _f: (1500, 1000))


def ref(handle, filename, role="reference"):
    return {"handle": handle, "kind": "image", "role": role, "filename": filename}


one = single([segment("a courier waits", duration_s=5),
              segment("the camera cuts to her hands", duration_s=4)],
             prompt="Live-action, cinematic")

check("the shots become one description",
      one.body,
      "[Shot 1] Live-action, cinematic. a courier waits "
      "[Shot 2] At 00:05.000, the camera cuts to her hands")
check("shot 1 carries no cut time", one.body.count("At 00:0"), 1)
# One generation, so the grid is applied once to the whole thing rather than per
# shot. 9 s -> 216 -> the nearest 17n+5.
check("the durations are summed and snapped once", one.frames, 209)
check("...and there is only one of it", one.continues, False)

check("a cut time the user wrote themselves is left alone",
      single([segment("opening"), segment("At 00:02.000, the shot cuts away")]).body,
      "[Shot 1] opening [Shot 2] At 00:02.000, the shot cuts away")

# The merge. Shot 2's `img-1` is a different file from shot 1's, and its `img-2`
# is the same file as shot 1's `img-1` — so the right answer is two references,
# with shot 2's two handles pointing at opposite ends of the list.
merged = single([
    segment("@img-1 walks in", assets=[ref("img-1", "a.png")]),
    segment("@img-1 sits beside @img-2", assets=[ref("img-1", "b.png"), ref("img-2", "a.png")]),
])
check("one reference per distinct file", [a.filename for a in merged.ref_images], ["a.png", "b.png"])
check("...cited from both shots by whichever handle each of them used",
      merged.body,
      "[Shot 1] <Picture 1> walks in [Shot 2] At 00:06.000, <Picture 2> sits beside <Picture 1>")

# The end frame is the video's final frame, so it belongs to the last shot —
# which is what the instruction line has to name, and the only case where it is
# not `Shot 1`.
frames = single([segment("she stands at the door", assets=[ref("img-1", "a.png", "first_frame")]),
                 segment("the camera cuts to the hallway"),
                 segment("she reaches the window", assets=[ref("img-1", "z.png", "last_frame")])])
check("frames at both ends make it FL2VA", frames.mode, "FL2VA")
check("the start frame is Picture 1 and the end frame Picture 2",
      frames.prompt.count("Picture 1 (from Shot 1)"), 1)
check("...and the end frame is reached by the last shot",
      frames.prompt.count("Picture 2 (from Shot 3)"), 1)

# A card may write several shots of its own; the rest of the timeline has to
# stay in step behind it, including the instruction line's Shot N.
own = single([segment("[Shot 1] opening [Shot 2] At 00:02.000, closer"),
              segment("out to the street", assets=[ref("img-1", "z.png", "last_frame")])])
check("a card numbering its own shots advances the count",
      own.body.endswith("[Shot 3] At 00:06.000, out to the street"), True)
check("...and the end frame follows it there", "(from [Shot 3])" in own.prompt, True)

expect_error("a card numbered out of step",
             lambda: single([segment("a"), segment("[Shot 7] misnumbered")]),
             "in this timeline it is [Shot 2]")
expect_error("a shot with nothing in it",
             lambda: single([segment("a"), segment("")]),
             "has no prompt")
expect_error("a start frame after the first shot",
             lambda: single([segment("a"), segment("b", assets=[ref("img-1", "z.png", "first_frame")])]),
             "the pass it is in opens on shot 1")
expect_error("an end frame before the last shot",
             lambda: single([segment("a", assets=[ref("img-1", "z.png", "last_frame")]), segment("b")]),
             "the pass it is in ends on shot 2")
frames_and_refs = single([segment("a", assets=[ref("img-1", "z.png", "first_frame")]),
                          segment("b @img-1", assets=[ref("img-1", "q.png")])])
check("frames in one shot and references in another share the pass",
      frames_and_refs.mode, "REF2VA")
check("...the frame staying shot 1's",
      frames_and_refs.first_frame.filename, "z.png")
expect_error("shots that disagree about the checkpoint",
             lambda: single([segment("a", checkpoint="fl2va"), segment("b", checkpoint="ref2va")]),
             "disagree about the checkpoint")
expect_error("shots that disagree about the soundscape",
             lambda: single([segment("a"), segment("b", soundscape="rain")], soundscape="silence"),
             "disagree about soundscape")

# Switching a chained timeline over leaves its seam flags in the blob. They
# describe joins that no longer exist, so they are ignored rather than refused —
# the alternative is a mode you cannot switch into without editing JSON.
check("carried-over seam flags are ignored",
      single([segment("a"), segment("b", **{"continue": True, "continue_audio": True})]).continues,
      False)

# ---- the refiner's rewrite --------------------------------------------------
#
# A refined body stands in for the user's sentence and is substituted exactly as
# a typed one is. That is the whole contract: it is stored with `@handles` in it
# rather than with ordinals, so adding or removing an asset re-labels a refined
# prompt correctly instead of leaving it pointing at the tensor that used to be
# in that slot. Storing labels instead would fail silently, which is the failure
# mode this module exists to prevent.

REWRITE = "A courier in @img-1 waits under a sodium lamp, shot on 16mm."


def refined(body=REWRITE, **rest):
    return {"body": body, "source": "a courier waits", **rest}


one_ref = compiler.compile_request(
    {"prompt": "a courier waits", "refined": refined(),
     "assets": [ref("img-1", "her.png")], "duration_s": 6},
    image_size_lookup=lambda _f: (1000, 1000))

check("the rewrite replaces the typed prompt",
      one_ref.body, "A courier in <Picture 1> waits under a sodium lamp, shot on 16mm.")
check("...and is wrapped by contextir like any other body",
      compiler.compile_request({"prompt": "a courier waits",
                                "refined": refined(body="A courier waits, in 16mm."),
                                "duration_s": 6}).prompt,
      "integrated_multimodal_description: [Shot 1] A courier waits, in 16mm.")

# The point of storing handles: a second reference in front of it moves the
# ordinal, and the rewrite has to move with it rather than keep pointing at 1.
moved = compiler.compile_request(
    {"prompt": "a courier waits", "refined": refined(),
     "assets": [ref("img-2", "street.png"), ref("img-1", "her.png")], "duration_s": 6},
    image_size_lookup=lambda _f: (1000, 1000))
check("a rewrite re-labels when the references move", "<Picture 2>" in moved.body, True)

check("switching the rewrite off falls back to the typed prompt",
      compiler.compile_request({"prompt": "a courier waits",
                                "refined": refined(enabled=False), "duration_s": 6}).body,
      "a courier waits")
check("an empty rewrite is no rewrite",
      compiler.compile_request({"prompt": "a courier waits",
                                "refined": refined(body="  "), "duration_s": 6}).body,
      "a courier waits")
expect_error("a rewrite naming an asset that is gone",
             lambda: compiler.compile_request(
                 {"prompt": "a courier waits", "refined": refined(), "duration_s": 6}),
             "no such asset is attached")

# A refined section replaces the derived one; the form is the same either way.
sectioned = compiler.compile_request(
    {"prompt": "her face is @img-1",
     "refined": {"body": "The woman from @img-1 turns to the window.",
                 "sections": {"subject_definitions": "<Subject 1>: the woman",
                              "summary": "[Ref2VA] a portrait",
                              "retention_analysis": "fully_preserved: her face"}},
     "assets": [ref("img-1", "her.png")], "duration_s": 6, "soundscape": "rain"})
check("a refined reference prompt gets the six-section form",
      [line.split(":")[0] for line in sectioned.prompt.split("\n\n")],
      ["subject_definitions", "summary", "retention_analysis",
       "detailed_description", "overall_soundscape"])
check("...and the derived one carries the same sections in the same order",
      [line.split(":")[0] for line in compiler.compile_request(
          {"prompt": "her face is @img-1",
           "assets": [ref("img-1", "her.png")], "duration_s": 6}).prompt.split("\n\n")],
      ["subject_definitions", "summary", "retention_analysis", "detailed_description"])
check("...with the refiner's summary kept over the derived one",
      "[Ref2VA] a portrait" in sectioned.prompt, True)

# In a chained timeline the rewrite has already absorbed the global prompt — the
# refiner was shown it — so joining it on again would say it twice.
PLAIN = "A courier waits under a sodium lamp, shot on 16mm."
chained_refine = timeline([segment("a courier waits", refined=refined(body=PLAIN))],
                          prompt="Live-action")
check("a refined segment does not get the global prompt twice", chained_refine[0].body, PLAIN)

one_pass_refine = single([segment("a courier waits", refined=refined(body="A courier waits, in 16mm.")),
                          segment("her hands", refined=refined(body="Her hands, closer."))],
                         prompt="Live-action")
check("one pass uses each shot's rewrite as its shot body",
      one_pass_refine.body,
      "[Shot 1] A courier waits, in 16mm. [Shot 2] At 00:06.000, Her hands, closer.")

# A shot-scoped rewrite is the segment's own sentence, not the piece: the
# refiner returns the global prompt as a field of its own now, so compile joins
# it in front of the rewrite exactly as it joins it in front of typed text.
# That is what keeps the timeline's global box a live input after refining —
# and only the unmarked blobs from before the marker existed, which absorbed
# the join when they were written, are still left whole.
check("refined_scope reads the marker",
      compiler.refined_scope({"refined": refined(scope="shot")}), "shot")
check("...and not off a legacy blob",
      compiler.refined_scope({"refined": refined()}), None)
check("...nor off a disabled rewrite",
      compiler.refined_scope({"refined": refined(scope="shot", enabled=False)}), None)
check("...nor off an empty body",
      compiler.refined_scope({"refined": {"body": "  ", "scope": "shot"}}), None)

scoped = timeline([segment("a courier waits", refined=refined(body=PLAIN, scope="shot"))],
                  prompt="Live-action")
check("a shot-scoped rewrite gets the global prompt joined in front",
      scoped[0].body, "Live-action\n" + PLAIN)
check("...and an empty global prompt joins nothing",
      timeline([segment("a courier waits",
                        refined=refined(body=PLAIN, scope="shot"))])[0].body,
      PLAIN)
check("a disabled shot-scoped rewrite falls back to the typed join",
      timeline([segment("a courier waits",
                        refined=refined(body=PLAIN, scope="shot", enabled=False))],
               prompt="Live-action")[0].body,
      "Live-action\na courier waits")

# The join composes with a reference card's own sections: the global prose
# leads the body, and the body is still wrapped as the six-section form.
scoped_ref = timeline(
    [segment("her face is @img-1",
             refined={"body": "The woman from @img-1 turns to the window.",
                      "scope": "shot", "source": "her face is @img-1",
                      "sections": {"subject_definitions": "<Subject 1>: the woman",
                                   "summary": "[Ref2VA] a portrait",
                                   "retention_analysis": "fully_preserved: her face"}},
             assets=[ref("img-1", "her.png")])],
    prompt="Live-action")
check("a shot-scoped reference rewrite keeps its sections around the joined body",
      scoped_ref[0].body, "Live-action\nThe woman from <Picture 1> turns to the window.")
check("...and still compiles to the six-section form",
      [line.split(":")[0] for line in scoped_ref[0].prompt.split("\n\n")][:4],
      ["subject_definitions", "summary", "retention_analysis", "detailed_description"])

one_pass_scoped = single(
    [segment("a courier waits", refined=refined(body="A courier waits, in 16mm.", scope="shot")),
     segment("her hands", refined=refined(body="Her hands, closer.", scope="shot"))],
    prompt="Live-action")
check("one pass joins the global prompt in front of a shot-scoped shot 1",
      one_pass_scoped.body,
      "[Shot 1] Live-action. A courier waits, in 16mm. "
      "[Shot 2] At 00:06.000, Her hands, closer.")

check("an absent render mode means chained", compiler.render_mode({}), "chained")
expect_error("an unknown render mode", lambda: compiler.render_mode({"render": "stitched"}), "unknown render mode")

# --- two-pass upscale --------------------------------------------------------

# At or under the native edge there is nothing to refine to, whatever the blob says.
check("no refine at native", build().refine, None)
check("no refine under native", build(short_edge=512).refine, None)
check("no refine at native even when asked", build(upscale="two_pass").refine, None)

over = build(short_edge=1152)
check("past native, pass one samples at the native canvas",
      (over.width, over.height), canvas.resolve_canvas(16 / 9, 768, H3))
check("...and the refine target is the slider's canvas",
      (over.refine.width, over.refine.height), canvas.resolve_canvas(16 / 9, 1152, H3))
check("...at the default denoise", over.refine.denoise, compiler.DEFAULT_REFINE_DENOISE)

direct = build(short_edge=1152, upscale="direct")
check("direct keeps the one-pass canvas and carries no refine",
      ((direct.width, direct.height), direct.refine),
      (canvas.resolve_canvas(16 / 9, 1152, H3), None))
expect_error("an unknown upscale mode", lambda: build(upscale="bigger"), "unknown upscale mode")

check("refine_denoise clamps rather than raising",
      (build(short_edge=1152, refine_denoise=2).refine.denoise,
       build(short_edge=1152, refine_denoise=0).refine.denoise),
      (compiler.MAX_REFINE_DENOISE, compiler.MIN_REFINE_DENOISE))
expect_error("a non-number refine_denoise",
             lambda: build(short_edge=1152, refine_denoise="lots"), "refine_denoise")

# The first pass can also sit under native — `sample_edge` lowers it, native
# stays both the default and the ceiling, and the target can be anywhere above.
low = build(short_edge=1152, sample_edge=512)
check("a lowered sample_edge moves pass one under native",
      (low.width, low.height), canvas.resolve_canvas(16 / 9, 512, H3))
check("...and still refines to the slider's canvas",
      (low.refine.width, low.refine.height), canvas.resolve_canvas(16 / 9, 1152, H3))
under = build(short_edge=768, sample_edge=512)
check("under native, sample_edge is what turns two passes on",
      ((under.width, under.height), (under.refine.width, under.refine.height)),
      (canvas.resolve_canvas(16 / 9, 512, H3), canvas.resolve_canvas(16 / 9, 768, H3)))
check("sample_edge clamps to native and to the canvas floor",
      (build(short_edge=1152, sample_edge=2000).width,
       build(short_edge=768, sample_edge=100).width),
      (canvas.resolve_canvas(16 / 9, 768, H3)[0], canvas.resolve_canvas(16 / 9, 384, H3)[0]))
check("a sample_edge at the slider is the one-pass render",
      build(short_edge=512, sample_edge=512).refine, None)
check("direct ignores sample_edge",
      build(short_edge=512, sample_edge=384, upscale="direct").refine, None)
expect_error("a non-number sample_edge", lambda: build(sample_edge="small"), "sample_edge")

# The adaptive canvas: the keyframe still owns the ratio, and both passes share it.
adaptive = build(assets=[image("img-1", "first_frame")], short_edge=1152)
check("adaptive two-pass samples at native with the keyframe's ratio",
      (adaptive.width, adaptive.height), canvas.canvas_from_image(1500, 1000, 768, H3)[:2])
check("...and refines to the same ratio at the slider",
      (adaptive.refine.width, adaptive.refine.height),
      canvas.resolve_canvas(1500 / 1000, 1152, H3))

# A timeline holds every segment to the pass-one canvas, and every segment
# refines to the same target — the concatenation happens after both passes.
two_pass_tl = timeline([segment(), segment()], short_edge=1152)
check("a two-pass timeline pins pass one at native",
      {(c.width, c.height) for c in two_pass_tl}, {canvas.resolve_canvas(16 / 9, 768, H3)})
check("...and refines every segment to the same target",
      {(c.refine.width, c.refine.height) for c in two_pass_tl},
      {canvas.resolve_canvas(16 / 9, 1152, H3)})
low_tl = timeline([segment()], short_edge=1152, sample_edge=512)[0]
check("a timeline's sample_edge reaches its segments",
      ((low_tl.width, low_tl.height), (low_tl.refine.width, low_tl.refine.height)),
      (canvas.resolve_canvas(16 / 9, 512, H3), canvas.resolve_canvas(16 / 9, 1152, H3)))
direct_tl = timeline([segment()], short_edge=1152, upscale="direct")[0]
check("a direct timeline is the old render",
      ((direct_tl.width, direct_tl.height), direct_tl.refine),
      (canvas.resolve_canvas(16 / 9, 1152, H3), None))

check("one pass inherits the timeline's two-pass choice",
      single([segment("a shot")], short_edge=1152).refine is not None, True)
check("...and its sample_edge",
      single([segment("a shot")], short_edge=768, sample_edge=512).refine is not None, True)
check("...and its direct choice",
      single([segment("a shot")], short_edge=1152, upscale="direct").refine, None)

# The still branch pins "direct": it has one decode and its graph has no refine
# pass — left unpinned, the slider above native would
# quietly sample at 768 and change nothing.
still_request = still._request({"request": {"prompt": "a poster", "short_edge": 2048}}, 5)
check("a still compiles direct past native", still_request.get("upscale"), "direct")
check("...and samples at the slider's own size",
      compiler.compile_request({**still_request, "aspect": "16:9"}).refine, None)

# --- the reference pool, one pass ---------------------------------------------
#
# In one pass the shots share a single merged reference list already; a pool
# asset cited in two shots must land in it once, with both citations renamed
# onto the one merged handle.

pool_single = single([segment("she waits, @ref-1", duration_s=5),
                      segment("cut to her again, @ref-1", duration_s=5)],
                     assets=[{"handle": "ref-1", "kind": "image",
                              "role": "reference", "filename": "sheet.png"}])
check("a pool reference cited twice merges to one",
      [a.filename for a in pool_single.ref_images], ["sheet.png"])
check("...and both citations point at it",
      pool_single.body.count("<Picture 1>"), 2)
check("a one-pass shot that cites nothing stays plain",
      single([segment("just a field", duration_s=5)],
             assets=[{"handle": "ref-1", "kind": "image",
                      "role": "reference", "filename": "sheet.png"}]).mode,
      "T2VA")

# A global citation in one pass: the global prompt opens shot 1's description
# un-renamed, so the merged pool has to keep calling the asset @ref-1 — and the
# one merged generation then carries it for the whole clip.
pool_global = single([segment("she waits", duration_s=5),
                      segment("her hands", duration_s=5)],
                     prompt="the piece follows @ref-1.",
                     assets=[{"handle": "ref-1", "kind": "image",
                              "role": "reference", "filename": "sheet.png"}])
check("a global citation reaches the one-pass request",
      [a.filename for a in pool_global.ref_images], ["sheet.png"])
# Under its own pool handle: the global prompt opens shot 1 un-renamed, so the
# merged pool has to still call the asset @ref-1 for the citation to resolve.
# Read past the shot marker `contextir` writes in front of it — what is being
# checked is the substitution, not where the description starts.
check("...under its own pool handle, so the join's citation resolves",
      "the piece follows <Picture 1>." in pool_global.body, True)
check("...as a reference generation", pool_global.mode, "REF2VA")

# ---- passes -----------------------------------------------------------------
#
# A run of merged segments is one generation, and the timeline is the runs
# chained end to end. The two old render modes are the extremes of that — no
# merges is chained, all merges is one pass — so the assertions worth having are
# about the middle, plus the one that says the extremes did not move.


def runs(segments, **rest):
    return compiler.timeline_runs({"segments": segments, **rest})


def merged(prompt="", **rest):
    return segment(prompt, merge=True, **rest)


check("no flags is one pass per segment",
      runs([segment(), segment(), segment()]), [(0, 1), (1, 2), (2, 3)])
check("a merged segment joins the one before it",
      runs([segment(), merged(), segment()]), [(0, 2), (2, 3)])
check("adjacent merges make one run",
      runs([segment(), merged(), merged()]), [(0, 3)])
check("a merge flag on segment 1 is ignored, like the seam flags",
      runs([merged(), segment()]), [(0, 1), (1, 2)])
check("a timeline saved as one pass still opens as one",
      runs([segment(), segment(), segment()], render="single"), [(0, 3)])

# The promise that makes this safe to ship: a timeline with no merges compiles
# to exactly the payloads it did before, byte for byte, so every segment node in
# an existing workflow stays a cache hit.
plain = [segment("one"), segment("two", **{"continue": True}), segment("three")]
check("an unmerged timeline's payloads are unchanged",
      compiler.timeline_payloads({"segments": plain, "prompt": "p"}),
      compiler.timeline_payloads({"segments": [dict(s) for s in plain], "prompt": "p"}))
check("...and a merge flag never reaches the request",
      "merge" in compiler.timeline_payloads(
          {"segments": [segment("a"), merged("b")]})[0]["request"],
      False)

# The rule that reproduces both old modes: the global prompt opens the first
# shot of every pass. One pass per segment means every segment gets it, which is
# what chained always did; one pass over all of them means only shot 1 does.
two_passes = compiler.timeline_payloads(
    {"segments": [segment("a", duration_s=5), merged("b", duration_s=4),
                  segment("c", duration_s=5), merged("d", duration_s=4)],
     "prompt": "Live-action"})
check("a partially merged timeline is one payload per pass", len(two_passes), 2)
check("each pass is its own description",
      [p["shots"] for p in two_passes], [2, 2])
check("the global prompt opens each pass's first shot",
      [p["request"]["prompt"].count("Live-action") for p in two_passes], [1, 1])
check("cut times restart at the pass, not the timeline",
      two_passes[1]["request"]["prompt"].count("At 00:05.000"), 1)
check("a pass's duration is the sum of its shots",
      [p["request"]["duration_s"] for p in two_passes], [9.0, 9.0])

# What a pass can only have one of is now a question about the pass. Frames
# and references can share a generation (Ref2VA reads pinned frames), so the
# split below is a choice about caching and control, not a requirement.
mixed = compiler.timeline_payloads(
    {"segments": [segment("opens", assets=[ref("img-1", "z.png", "first_frame")]),
                  merged("still the same shot"),
                  segment("a face @img-1", assets=[ref("img-1", "q.png")]),
                  merged("her hands @img-1", assets=[ref("img-1", "q.png")])]},
    image_size_lookup=lambda _f: (1500, 1000))
check("a keyframe pass and a reference pass in one timeline",
      [compiler.compile_segment(p, lambda _f: (1500, 1000)).mode for p in mixed],
      ["I2VA", "REF2VA"])
merged_both = compiler.timeline_payloads(
    {"segments": [segment("opens", assets=[ref("img-1", "z.png", "first_frame")]),
                  merged("a face @img-2", assets=[ref("img-2", "q.png")])]},
    image_size_lookup=lambda _f: (1500, 1000))
check("...and inside one pass they merge into REF2VA",
      compiler.compile_segment(merged_both[0], lambda _f: (1500, 1000)).mode,
      "REF2VA")

# The seam in front of a pass is the pass's; the seams inside it are gone.
seamed = compiler.timeline_payloads(
    {"segments": [segment("a"), merged("b", **{"continue": True}),
                  segment("c", **{"continue": True, "feather": 22})]})
check("a seam inside a pass is dropped with the seam",
      [p["continue"] for p in seamed], [False, True])
check("...and the blend rides with it", seamed[1].get("feather"), 22)
check("the passes are held to one canvas, like segments always were",
      len({(p["canvas"]["width"], p["canvas"]["height"]) for p in seamed}), 1)
check("one pass over the whole strip keeps its adaptive canvas",
      "canvas" in compiler.timeline_payloads({"segments": [segment("a"), merged("b")]})[0],
      False)

# A seam naming a segment that has since been merged into a pass lands on the
# pass: the frames that exist after decode are the pass's, not that segment's.
check("a seam into a merged pass resolves to the pass",
      [p.get("continue_from") for p in compiler.timeline_payloads(
          {"segments": [segment("a"), merged("b"), segment("c"),
                        segment("d", **{"continue": True, "continue_from": 1})]})],
      [None, None, 0])

# ---- supplied clips ---------------------------------------------------------
#
# A card that is not a generation: footage the user already has, cut into the
# strip. It compiles to a payload with no request in it at all, which is the
# claim every branch below rests on — there is no prompt to write, no mode to
# derive and no checkpoint to route to.


def clip(filename="shot.mp4", **rest):
    return {"kind": "clip", "filename": filename, **rest}


def clip_payloads(segments, image_size_lookup=None, **rest):
    return compiler.timeline_payloads({"segments": segments, **rest}, image_size_lookup)


one_clip = clip_payloads([segment("wide", duration_s=5),
                          clip(duration_s=3, width=1920, height=1080)])
check("a clip card is a payload of its own", len(one_clip), 2)
check("...carrying the file and the window, and no request",
      sorted(one_clip[1]), ["canvas", "clip", "continue", "continue_audio"])
check("...with the whole file when it is not trimmed",
      (one_clip[1]["clip"]["start"], one_clip[1]["clip"]["duration"]), (0.0, 3.0))
check("...and its sound on, which is what a clip usually comes for",
      one_clip[1]["clip"]["sound"], True)

# The trim is the window, and it is what decides the card's length: a clip's
# duration is not a setting, it is how much of the file plays.
trimmed = clip_payloads([clip(duration_s=30, trim={"start": 2.0, "end": 6.5})])
check("a trimmed clip plays its window",
      (trimmed[0]["clip"]["start"], trimmed[0]["clip"]["duration"]), (2.0, 4.5))
check("...and that is the length the budget counts",
      compiler.timeline_frames({"segments": [clip(duration_s=30, trim={"start": 2.0, "end": 6.5})]}),
      round(4.5 * H3.fps))
# Nothing samples a clip, so there is no 17n+5 grid for it to land on — a
# generated card of the same length is snapped and this one is not.
check("a clip is counted at its own length, unsnapped",
      compiler.timeline_frames({"segments": [clip(duration_s=3)]}), 72)
check("...where a generated card of the same length is snapped",
      compiler.timeline_frames({"segments": [segment("x", duration_s=3)]}),
      canvas.frames_for_seconds(3, H3))
expect_error("a clip with no length is refused",
             lambda: clip_payloads([clip()]), "needs its length")
expect_error("...and one with no file",
             lambda: clip_payloads([clip(filename="", duration_s=3)]), "names no file")

# What a clip cannot be part of. Merging says two cards are one sampler pass,
# and there is no sampler here — refused rather than ignored, because a strip
# that dropped the flag would price itself wrong on the bar and then fail in
# the graph.
expect_error("a clip cannot be merged into the pass before it",
             lambda: clip_payloads([segment("a"), clip(duration_s=3, merge=True)]),
             "cannot share a generation")
expect_error("...and nothing can be merged into a clip",
             lambda: clip_payloads([clip(duration_s=3), merged("b")]),
             "no generation there to merge into")
expect_error("a timeline holding footage is not one pass",
             lambda: clip_payloads([segment("a"), clip(duration_s=3)], render="single"),
             "cannot be rendered as one pass")

# The seam in front of a clip does not continue *into* it — a clip is not
# conditioned on anything. (What those switches mean on a clip card is the seam
# running the other way, which is the shot before it ending on its first frame.)
into = clip_payloads([segment("a"), clip(duration_s=3, **{"continue": True,
                                                          "continue_audio": True})])
check("a clip is never conditioned on the segment before it",
      (into[1]["continue"], into[1]["continue_audio"]), (False, False))

# A generation *after* a clip continues from it exactly as it would from a
# generated pass: what a seam inherits is decoded frames, and by the time it is
# crossed the clip's frames exist.
after = clip_payloads([clip(duration_s=3, width=1920, height=1080),
                       segment("b", duration_s=5, **{"continue": True, "feather": 22,
                                                     "continue_audio": True})])
check("a segment after a clip continues from it",
      (after[1]["continue"], after[1]["continue_audio"], after[1]["feather"]),
      (True, True, 22))

# ---- the canvas a clip sets -------------------------------------------------
#
# Footage was shot at the size it was shot at, and cropping it to a pill's
# preference throws away picture that cannot be got back. So a clip outranks
# the ratio pill — but not a keyframe on segment 1, which is the rule that
# already existed and that every timeline without footage still follows.

vertical = clip_payloads([segment("a", duration_s=5),
                          clip(duration_s=3, width=1080, height=1920)],
                         aspect="16:9", short_edge=768)
check("a clip's own shape sets the timeline's, over the pill",
      vertical[0]["canvas"]["width"] < vertical[0]["canvas"]["height"], True)
check("...for every pass, since they are played end to end",
      vertical[0]["canvas"], vertical[1]["canvas"])
check("...and the slider still owns the scale",
      min(vertical[0]["canvas"]["width"], vertical[0]["canvas"]["height"]), 768)
# `from_image` says a keyframe in this generation set the canvas, and `encode`
# reads it to decide whether a keyframe may be stretched onto the canvas or has
# to be cropped into it. A clip is not a keyframe and sets nothing to match.
check("...without claiming a keyframe set it",
      vertical[0]["canvas"]["from_image"], False)

check("a keyframe on segment 1 still wins",
      clip_payloads([segment("a", duration_s=5, assets=[ref("img-1", "z.png", "first_frame")]),
                     clip(duration_s=3, width=1080, height=1920)],
                    image_size_lookup=lambda _f: (1500, 1000))[0]["canvas"]["from_image"],
      True)
check("a clip that never recorded its size leaves the pill alone",
      clip_payloads([segment("a", duration_s=5), clip(duration_s=3)],
                    aspect="16:9")[0]["canvas"]["label"], "16:9")
check("the first clip decides when two disagree",
      clip_payloads([clip("a.mp4", duration_s=3, width=1080, height=1920),
                     clip("b.mp4", duration_s=3, width=1920, height=1080)]
                    )[0]["canvas"]["width"] < 768 * 2, True)

# The piece's own aspect source outranks the whole precedence order: it is the
# user naming the source instead of accepting the rule.
chosen_card = clip_payloads([segment("a", duration_s=5,
                                     assets=[ref("img-1", "z.png", "first_frame")]),
                             segment("b @img-1", duration_s=5,
                                     assets=[ref("img-1", "tall.png")])],
                            aspect_source={"card": 2, "handle": "img-1"},
                            image_size_lookup=lambda f: (768, 1344) if f == "tall.png"
                                                        else (1500, 1000))
check("a named card's reference sets the timeline's canvas",
      (chosen_card[0]["canvas"]["width"] < chosen_card[0]["canvas"]["height"],
       chosen_card[0]["canvas"]["from_image"]),
      (True, False))
check("naming segment 1's own anchor is the auto rule",
      clip_payloads([segment("a", duration_s=5,
                             assets=[ref("img-1", "z.png", "first_frame")])],
                    aspect_source={"card": 1, "handle": "img-1"},
                    image_size_lookup=lambda _f: (1500, 1000))[0]["canvas"]["from_image"],
      True)
check("the pill can be forced against a clip",
      clip_payloads([segment("a", duration_s=5),
                     clip(duration_s=3, width=1080, height=1920)],
                    aspect="16:9", aspect_source="pill")[0]["canvas"]["label"],
      "16:9")
check("a pool reference can set it",
      clip_payloads([segment("a", duration_s=5)],
                    assets=[{"handle": "ref-1", "kind": "image",
                             "role": "reference", "filename": "tall.png"}],
                    aspect_source={"handle": "ref-1"},
                    image_size_lookup=lambda f: (768, 1344) if f == "tall.png"
                                                else (1500, 1000)
                    )[0]["canvas"]["height"] > 768, True)
expect_error("a card the strip does not have is refused",
             lambda: clip_payloads([segment("a", duration_s=5)],
                                   aspect_source={"card": 4, "handle": "img-1"},
                                   image_size_lookup=lambda _f: (1500, 1000)),
             "the strip has 1")

# In one pass the piece's `{card, handle}` has to survive the merge's renaming:
# the merged request carries the merged handle, and the canvas follows it.
merged_source = compiler.compile_single(
    {"segments": [segment("a", duration_s=5),
                  segment("b @img-1", duration_s=5,
                          assets=[ref("img-1", "tall.png")])],
     "aspect_source": {"card": 2, "handle": "img-1"}},
    image_size_lookup=lambda f: (768, 1344) if f == "tall.png" else (1500, 1000))
check("the aspect source survives the one-pass merge",
      merged_source.width < merged_source.height, True)

# What the clip is conformed to on the way into the file is the size the
# generated passes *deliver* — which past a two-pass render is not the size
# they sample at.
two = clip_payloads([segment("a", duration_s=5), clip(duration_s=3)],
                    aspect="16:9", short_edge=896, upscale="two_pass", sample_edge=768)
check("a two-pass timeline samples under its target",
      two[0]["canvas"]["height"], 768)
check("...and the clip is conformed to what comes out, not to what is sampled",
      two[1]["clip"]["height"], 896)

# ---- a lone generation works its own canvas out, pinned or not ---------------
#
# The Creator used to hand `render.emit` a payload it built by hand, with no
# `canvas` key on it: a lone generation had nothing to be held to, so a start
# frame set the aspect adaptively at compile time. It goes through
# `timeline_payloads` now like every other piece, which stamps the one geometry
# onto every payload — and the whole merge rests on that stamp being the answer
# the generation would have reached on its own.
#
# `_timeline_canvas` says as much ("payload 1 is compiled exactly as a lone
# generation would be") but nothing checked it, and the adaptive cases are
# exactly where pinning and deriving could quietly diverge.

_SIZES = {"tall.png": (768, 1366), "wide.png": (1920, 816), "square.png": (1024, 1024)}
_look = lambda name: _SIZES.get(os.path.basename(name))


def lone_shot(keyframe=None, **fields):
    blob = {"version": 1, "prompt": "a room", "duration_s": 6,
            "aspect": "16:9", "short_edge": 768, "loras": [], "models": {},
            "assets": ([{"handle": "img-1", "kind": "image",
                         "role": "first_frame", "filename": keyframe}] if keyframe else [])}
    blob.update(fields)
    return blob


def derived_and_pinned(blob):
    """What this generation compiles to the old way and the new way.

    Old: the hand-built payload the Creator used to emit, with no canvas on it.
    New: the payload `timeline_payloads` writes for the same blob, canvas and all.
    """
    old = compiler.compile_segment(
        {"request": dict(blob), "continue": False, "continue_audio": False}, _look)
    new = compiler.compile_segment(
        compiler.timeline_payloads(dict(blob), image_size_lookup=_look)[0], _look)
    fields = ("width", "height", "frames", "seconds", "mode", "checkpoint", "prompt")
    return ([getattr(old, f) for f in fields], [getattr(new, f) for f in fields])


for label, blob in [
    ("no keyframe", lone_shot()),
    ("a 9:16 keyframe under a 16:9 pill", lone_shot("tall.png")),
    ("a 21:9 keyframe under a 16:9 pill", lone_shot("wide.png")),
    ("a square keyframe", lone_shot("square.png")),
    ("a keyframe at a narrower edge", lone_shot("tall.png", short_edge=640)),
    ("a keyframe on a two-pass render",
     lone_shot("tall.png", short_edge=1152, sample_edge=768, upscale="two_pass")),
    ("a pinned aspect with no keyframe to argue", lone_shot(aspect="1:1")),
]:
    old, new = derived_and_pinned(blob)
    check(f"the stamped canvas is the derived one — {label}", new, old)

passed("all contract tests passed")


# ---- takes and holds --------------------------------------------------------
#
# A strip shot a pass at a time. What is checked here is the rewrite, because
# the rewrite is the whole mechanism: everything downstream of it only ever
# sees a piece made of shots and clips, exactly as it did before any of this.

def strip(*segments, **fields):
    blob = {"version": 2, "prompt": "", "aspect": "16:9", "short_edge": 768,
            "loras": [], "models": {}, "segments": list(segments)}
    blob.update(fields)
    return blob


def shot(prompt="a room", seconds=6, **fields):
    return {"prompt": prompt, "duration_s": seconds, "assets": [], **fields}


def take(seconds=6.0, **fields):
    return {"filename": "minimax/renders/takes/H3_00001_s01.mp4",
            "duration_s": seconds, "width": 1280, "height": 720,
            "has_audio": True, **fields}


untouched = strip(shot("one"), shot("two"), shot("three"))
check("a strip with no holds is handed straight back",
      compiler.rendered_piece(untouched) is compiler.as_piece(untouched), True)

# Segment 1 kept, 2 and 3 not shot yet: one clip, and nothing else.
sequential = strip(shot("one", hold=True, take=take()),
                   shot("two", hold=True), shot("three", hold=True))
rendered = compiler.rendered_piece(sequential)
check("a kept card becomes a clip", [s.get("kind") for s in rendered["segments"]], ["clip"])
check("...of its take's file", rendered["segments"][0]["filename"],
      "minimax/renders/takes/H3_00001_s01.mp4")
check("...at its take's length", rendered["segments"][0]["duration_s"], 6.0)
check("...and held cards with no take are not in the render",
      len(rendered["segments"]), 1)

# The ordinary next step: 1 kept, 2 in the render, 3 still held.
step2 = strip(shot("one", hold=True, take=take()),
              shot("two", **{"continue": True}), shot("three", hold=True))
rendered = compiler.rendered_piece(step2)
check("the card being shot survives the rewrite",
      [s.get("kind", "shot") for s in rendered["segments"]], ["clip", "shot"])
check("the seam into it is untouched", rendered["segments"][1].get("continue"), True)
check("the cards keep their numbers on the strip",
      [s["card_no"] for s in rendered["segments"]], [1, 2])
payloads = compiler.timeline_payloads(rendered, image_size_lookup=_look)
check("the take is spliced rather than sampled", "clip" in payloads[0], True)
check("and the shot after it continues from the take", payloads[1]["continue"], True)

# The seam a kept card was generated with is not a seam any more.
kept_seam = strip(shot("one"), shot("two", hold=True, take=take(),
                                    **{"continue": True, "feather": 22}))
rendered = compiler.rendered_piece(kept_seam)
check("a kept card's own incoming seam is dropped",
      [rendered["segments"][1].get(key) for key in ("continue", "feather")], [None, None])

# Holds belong to the pass: a merged run is one take, spliced once.
merged = strip(shot("one", hold=True, take=take(seconds=12.0)),
               shot("two", merge=True, hold=True, take=take()),
               shot("three"))
rendered = compiler.rendered_piece(merged)
check("a merged run is one clip of the pass's take",
      [s.get("kind", "shot") for s in rendered["segments"]], ["clip", "shot"])
check("...at the pass's own length", rendered["segments"][0]["duration_s"], 12.0)

expect_error("a strip with nothing left to render",
             lambda: compiler.rendered_piece(
                 strip(shot("one", hold=True), shot("two", hold=True))),
             "held with nothing to play")

# ...but a strip where every card plays a take is the end of a shoot: it samples
# nothing and writes the piece out of the film it already has.
finished = strip(shot("one", hold=True, take=take()), shot("two", hold=True, take=take()))
check("a fully kept strip renders as footage",
      [s["kind"] for s in compiler.rendered_piece(finished)["segments"]], ["clip", "clip"])
expect_error("a take that does not say how long it is",
             lambda: compiler.rendered_piece(
                 strip(shot("one", hold=True,
                            take={"filename": "a.mp4", "duration_s": 0}))),
             "does not say how long it is")

# One pass over the whole strip: a hold there holds the generation, because
# there is only one and no half of it to hold.
single = strip(shot("one"), shot("two"), render="single")
check("a one-pass strip with no holds is unchanged",
      compiler.rendered_piece(single) is compiler.as_piece(single), True)
single_held = strip(shot("one", hold=True, take=take(seconds=12.0)),
                    shot("two", hold=True), render="single")
rendered = compiler.rendered_piece(single_held)
check("a held one-pass strip plays its take",
      [rendered["render"], len(rendered["segments"])], ["chained", 1])

check("a card with no seed runs on the piece's", compiler.segment_seed(shot(), 0), None)
check("a card with one runs on its own", compiler.segment_seed(shot(seed=7), 0), 7)
expect_error("a seed that is not a number",
             lambda: compiler.segment_seed(shot(seed="x"), 0), "seed must be a whole number")


# ---- what a card's bookkeeping must not reach ---------------------------------
#
# A request is the segment node's cache key. The strip keeps four keys on a card
# that say what has been *done* with the generation rather than what it is, and
# every one of them used to be copied straight into the request — so re-rolling
# a seed, or shooting one card of six, re-encoded conditioning that had not
# changed. `render.emit` holds the seed out of the payload for precisely this
# reason and was quietly undone by the copy.

def _request(**fields):
    return compiler.timeline_payloads(strip(shot("a room", **fields)))[0]["request"]


plain_request = _request()
for _key, _value in (("seed", 4242), ("take", take()), ("hold", True), ("card_no", 3)):
    check(f"a card's {_key} is not part of what it generates",
          _request(**{_key: _value}), plain_request)

# ...and the same card, compiled as part of a render that holds its neighbours
# back, is the same generation it is in the whole render. This is the one that
# costs money: a piece shot a pass at a time compiles every card through
# `rendered_piece`, which stamps `card_no` on all of them.
_whole = compiler.timeline_payloads(strip(shot("one"), shot("two"), shot("three")))
_part = compiler.timeline_payloads(compiler.rendered_piece(
    strip(shot("one", hold=True), shot("two", hold=True), shot("three"))))
check("a card shot alone generates what it generates in the whole render",
      _part[0]["request"], _whole[2]["request"])


# ---- a seam cannot inherit from a card that is not in the render --------------
#
# The other half of shooting a piece a pass at a time. A held card is dropped,
# so the card behind it moves up and its seam quietly points at somebody else's
# last frame — which is a wrong shot that looks right until the piece is
# assembled. Shooting out of order is free exactly across cuts, and this is what
# makes that true rather than merely advisable.

expect_error("a seam whose card has not been shot",
             lambda: compiler.rendered_piece(
                 strip(shot("one", hold=True, take=take()),
                       shot("two", hold=True),
                       shot("three", **{"continue": True}))),
             "segment 3 continues from segment 2, which is not in this render")
expect_error("...and a seam that only carries sound",
             lambda: compiler.rendered_piece(
                 strip(shot("one", hold=True), shot("two", continue_audio=True))),
             "segment 2 continues from segment 1")
expect_error("...and a named source that has not been shot",
             lambda: compiler.rendered_piece(
                 strip(shot("one", hold=True), shot("two", hold=True, take=take()),
                       shot("three", **{"continue": True, "continue_from": 1}))),
             "segment 3 continues from segment 1")

# A cut is the thing that makes an order free, so a card with no seam shoots
# whenever it likes — which is the whole of "start with segment 6, then 4".
_solo = compiler.rendered_piece(strip(shot("one", hold=True), shot("two", hold=True),
                                      shot("three")))
check("a card behind a cut shoots out of order",
      [s["card_no"] for s in _solo["segments"]], [3])

# ...and the seam onto a kept take goes on working, because the take is in the
# render: it is the film that card's frames come from.
_after = compiler.timeline_payloads(compiler.rendered_piece(
    strip(shot("one", hold=True, take=take()), shot("two", **{"continue": True}))))
check("a card behind a kept take still continues from it",
      (_after[-1]["continue"], "continue_from" in _after[-1]), (True, False))

# `continue_from` is a number on the strip and was being read as a position in
# the render. They are the same number until something earlier is dropped, and
# after that a card named its source and inherited from a different one.
_named = compiler.rendered_piece(
    strip(shot("one", hold=True),                       # dropped: never shot
          shot("two", hold=True, take=take()),
          shot("three", hold=True, take=take()),
          shot("four", hold=True, take=take()),
          shot("five", **{"continue": True, "continue_from": 2})))
_at = compiler.timeline_payloads(_named)[-1]["continue_from"]
check("a named seam source follows the card it names into a shortened render",
      _named["segments"][_at]["card_no"], 2)
