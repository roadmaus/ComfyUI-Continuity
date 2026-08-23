"""Route modules. Each registers itself on ComfyUI's server when imported —
the root `__init__.py` names them, and the order it names them in is the
order they register. `server_routes.py` predates this package and still holds
the asset, LoRA and settings routes; new routes land here.
"""
