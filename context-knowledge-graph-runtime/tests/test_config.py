"""Verify the single-file configuration contract without local credentials."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("process_override", [False, True])
def test_only_runtime_env_is_loaded_and_process_environment_wins(tmp_path, process_override):
    runtime = tmp_path / "runtime"
    package = runtime / "src" / "context_knowledge_graph"
    package.mkdir(parents=True)
    config = package / "config.py"
    config.write_text(
        (Path(__file__).parents[1] / "src" / "context_knowledge_graph" / "config.py").read_text()
    )
    (tmp_path / ".env").write_text(
        "CONTEXT_KNOWLEDGE_GRAPH_DATABASE=root-database\n"
        "CONTEXT_KNOWLEDGE_GRAPH_LEXICAL_INDEX=root-index\n"
    )
    (runtime / ".env").write_text("CONTEXT_KNOWLEDGE_GRAPH_DATABASE=runtime-database\n")
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("CONTEXT_KNOWLEDGE_GRAPH_")
    }
    if process_override:
        env["CONTEXT_KNOWLEDGE_GRAPH_DATABASE"] = "process-database"
    code = (
        "import json, runpy, sys; "
        "settings = runpy.run_path(sys.argv[1])['Settings'](); "
        "print(json.dumps([settings.database, settings.lexical_index]))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code, str(config)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(result.stdout) == [
        "process-database" if process_override else "runtime-database",
        "context_knowledge_graph_rules_lexical",
    ]
