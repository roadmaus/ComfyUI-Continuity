"""The saved room keeps its turn, cancels its own prompt, and stays deleted.

Runs complete production modules with external API/DOM/storage mocks. No GPU,
ComfyUI server, real browser, network or user data is needed.
"""
import os
import subprocess

import layout
from harness import died, passed

layout.skip_without_node()
script = os.path.join(os.path.dirname(__file__), "chat_lifecycle.mjs")
result = subprocess.run(["node", "--experimental-vm-modules", script],
                        capture_output=True, text=True)
if result.returncode:
    died(result.stdout + result.stderr)
print(result.stdout.strip())
passed("chat lifecycle regressions passed")
