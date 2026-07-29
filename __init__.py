"""Hermes Memory UI plugin package.

This repository provides Dashboard and Desktop user interfaces. Hermes'
generic plugin loader also imports enabled plugins from their repository root,
so expose a minimal no-op register() hook while Hermes mounts the shared
dashboard/plugin_api.py backend separately.
"""


def register(ctx):
    """Register root-level Hermes extensions.

    The memory UI provides UI assets and API routes, so there are no root-level
    tools, commands, or hooks to register.
    """
    return None
