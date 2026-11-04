"""scripts/cloud-session-setup.sh: the SessionStart hook that sets a Claude
cloud session up like `just setup`, with the Node of web/.nvmrc, and does
nothing anywhere else.

Runs the script itself through bash, with a fake nvm and a fake uv that
leave a trace in a temp directory, so the tests see what really ran."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
SETUP = SCRIPTS / "cloud-session-setup.sh"
NVMRC = (SCRIPTS.parent / "web" / ".nvmrc").read_text(encoding="utf-8").strip()

FAKE_NVM = """
nvm() {
  echo "nvm $*" >> "$TRACE"
  export PATH="$FAKE_NODE_BIN:$PATH"
}
"""
FAKE_UV = """#!/usr/bin/env bash
echo "uv $*" >> "$TRACE"
echo "uv output"
"""


def make_executable(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)
    return path


def setup(
    tmp_path: Path, *, remote: bool, with_nvm: bool = True
) -> subprocess.CompletedProcess[str]:
    home = tmp_path / "home"
    home.mkdir()
    if with_nvm:
        make_executable(home / ".nvm" / "nvm.sh", FAKE_NVM)
    make_executable(tmp_path / "node-bin" / "node", "#!/usr/bin/env bash\n")
    make_executable(tmp_path / "bin" / "uv", FAKE_UV)
    env = {
        "HOME": str(home),
        "PATH": f"{tmp_path / 'bin'}:{os.environ['PATH']}",
        "TRACE": str(tmp_path / "trace"),
        "FAKE_NODE_BIN": str(tmp_path / "node-bin"),
        "CLAUDE_ENV_FILE": str(tmp_path / "env-file"),
    }
    if remote:
        env["CLAUDE_CODE_REMOTE"] = "true"
    return subprocess.run(["bash", str(SETUP)], env=env, capture_output=True, encoding="utf-8")


def trace(tmp_path: Path) -> list[str]:
    return (tmp_path / "trace").read_text(encoding="utf-8").splitlines()


def test_does_nothing_outside_cloud_sessions(tmp_path: Path) -> None:
    result = setup(tmp_path, remote=False)

    assert result.returncode == 0, result.stderr
    assert not (tmp_path / "trace").exists()


def test_runs_just_setup_with_the_node_of_nvmrc(tmp_path: Path) -> None:
    result = setup(tmp_path, remote=True)

    assert result.returncode == 0, result.stderr
    assert trace(tmp_path) == [f"nvm use {NVMRC}", "uv run just setup"]


def test_puts_that_node_on_the_path_of_later_commands(tmp_path: Path) -> None:
    setup(tmp_path, remote=True)

    env_file = (tmp_path / "env-file").read_text(encoding="utf-8")
    assert env_file == f'export PATH="{tmp_path / "node-bin"}:$PATH"\n'


def test_keeps_setup_output_out_of_claudes_context(tmp_path: Path) -> None:
    result = setup(tmp_path, remote=True)

    assert result.stdout == ""


def test_names_the_fix_when_nvm_is_missing(tmp_path: Path) -> None:
    result = setup(tmp_path, remote=True, with_nvm=False)

    assert result.returncode != 0
    assert "setup script" in result.stderr
