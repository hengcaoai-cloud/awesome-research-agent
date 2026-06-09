#!/usr/bin/env python3
"""Provider-agnostic headless LLM call used by digest_cards.py and viz.py.

Pick the agent CLI with the RESEARCH_AGENT_LLM env var:
    RESEARCH_AGENT_LLM=claude   (default)  -> `claude -p "<prompt>"`   (Claude Code)
    RESEARCH_AGENT_LLM=codex               -> `codex exec "<prompt>"`  (OpenAI Codex)

Both run the chosen CLI non-interactively and return the model's text on stdout.
Codex runs in a read-only sandbox (text generation only — never edits files).
"""
import os
import shutil
import subprocess

PROVIDER = os.environ.get("RESEARCH_AGENT_LLM", "claude").strip().lower()
_EXE = {"codex": "codex", "claude": "claude"}.get(PROVIDER, "claude")


def cli_name():
    return PROVIDER


def available():
    """True if the configured agent CLI is installed."""
    return shutil.which(_EXE) is not None


def complete(prompt, timeout=600):
    """Run the configured agent CLI on `prompt`; return (ok, text_or_error)."""
    exe = shutil.which(_EXE)
    if not exe:
        return False, (f"{_EXE} not found on PATH (set RESEARCH_AGENT_LLM=claude|codex "
                       f"and install that CLI)")
    if PROVIDER == "codex":
        # `codex exec` prints the final answer to stdout; read-only = no approvals.
        cmd = [exe, "exec", "--sandbox", "read-only", prompt]
    else:
        cmd = [exe, "-p", prompt]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, f"{_EXE} timed out after {timeout}s"
    except Exception as e:
        return False, f"{_EXE} failed: {e}"
    out = (r.stdout or "").strip()
    if r.returncode != 0 and len(out) < 20:
        return False, (r.stderr or out or f"{_EXE} returned no output").strip()[:300]
    return True, out


if __name__ == "__main__":
    import sys
    ok, txt = complete(" ".join(sys.argv[1:]) or "Reply with exactly: READY")
    print(("[%s] " % cli_name()) + ("" if ok else "ERROR: ") + txt)
