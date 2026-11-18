import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_builtin_profile_selection():
    result = subprocess.run(
        ["node", str(ROOT / "tests/dashboard_builtin_profiles_smoke.mjs"),
         str(ROOT / "dashboard/dist/index.js")],
        cwd=ROOT, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
