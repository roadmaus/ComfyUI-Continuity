"""MiniMax H3: two routed checkpoints, the `<Picture N>` ordinal protocol, the
17n+5 frame grid, KSampler behind a sigma shift.

The modules in here do not generalise and must not be forced to — LTX takes
plain prose through Gemma and has no ordinal protocol, no context IR, no
subject shelf. That they are H3's alone is the reason they are in this package.

No imports here: `payload` needs torch, and the suites load `contextir` and
`subjects` without it.
"""
