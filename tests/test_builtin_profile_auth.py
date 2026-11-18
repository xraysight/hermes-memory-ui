"""Host-authenticated regression for the built-in memory profile selector."""
import os
import subprocess

import pytest

from test_profile_scope_regressions import ROOT, discover_host_runtime


def test_builtin_profiles_through_real_host_auth():
    host_python, source, reasons = discover_host_runtime()
    if host_python is None or source is None:
        pytest.skip(
            "Hermes host integration prerequisites unavailable; set HERMES_HOST_PYTHON and "
            f"HERMES_AGENT_SOURCE ({'; '.join(reasons) or 'no candidates'})"
        )
    environment = os.environ.copy()
    environment["HERMES_AGENT_SOURCE"] = str(source)
    result = subprocess.run(
        [str(host_python), str(ROOT / "tests" / "builtin_profile_auth_http_regression.py")],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "builtin-profile auth HTTP regression: ok" in result.stdout
