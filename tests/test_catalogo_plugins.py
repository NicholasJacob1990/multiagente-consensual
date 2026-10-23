"""O hook acrescenta apenas contexto e não decide permissões ou executa arquivos."""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "plugins/legal-br/hooks/legal_context.py"


def invoke(value):
    raw = value if isinstance(value, str) else json.dumps(value)
    result = subprocess.run([sys.executable, str(HOOK)], input=raw, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout) if result.stdout else None


def test_hook_adds_context_for_legal_path_without_echoing_private_path():
    private_path = "/private/cliente/Jurídico/peça confidencial.md"
    out = invoke({"tool_name": "Read", "tool_input": {"file_path": private_path}})
    assert out["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
    assert out["hookSpecificOutput"]["additionalContext"]
    assert private_path not in json.dumps(out)
    assert "permissionDecision" not in out["hookSpecificOutput"]


def test_hook_does_not_apply_to_arbitrary_files_or_other_tools():
    assert invoke({"tool_name": "Read", "tool_input": {"file_path": "/src/legal_context.py"}}) is None
    assert invoke({"tool_name": "Bash", "tool_input": {"file_path": "/legal/contrato.md"}}) is None


def test_hook_ignores_incomplete_or_malformed_events():
    for value in ["not JSON", [], {}, {"tool_name": "Read", "tool_input": []},
                  {"tool_name": "Read", "tool_input": {"file_path": []}}]:
        assert invoke(value) is None
