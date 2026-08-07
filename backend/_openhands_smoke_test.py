"""Throwaway smoke test: verify the OpenHands SDK installs and runs on this machine.

Not wired into any SWARM code. Run directly:
    .\\.venv\\Scripts\\python.exe backend\\_openhands_smoke_test.py
"""

import os
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if sys.path and Path(sys.path[0]).resolve() == SCRIPT_DIR:
    sys.path.pop(0)

REPO_ROOT = SCRIPT_DIR.parent
SMOKE_HOME = REPO_ROOT / ".openhands_smoke_home"
SMOKE_HOME.mkdir(exist_ok=True)

os.environ["HOME"] = str(SMOKE_HOME)
os.environ["USERPROFILE"] = str(SMOKE_HOME)
os.environ.setdefault("APPDATA", str(SMOKE_HOME / "AppData" / "Roaming"))
os.environ.setdefault("LOCALAPPDATA", str(SMOKE_HOME / "AppData" / "Local"))
os.environ.setdefault("OPENHANDS_SUPPRESS_BANNER", "1")

from dotenv import load_dotenv

load_dotenv(REPO_ROOT / ".env")

from openhands.sdk import LLM, Conversation
from openhands.sdk.event import MessageEvent
from openhands.tools.preset.default import get_default_agent

WORKSPACE = Path(__file__).resolve().parent / "_openhands_smoke_workspace"
PERSISTENCE_DIR = WORKSPACE / ".openhands_persistence"
TASK = "Create a single Python file hello.py that prints 'OpenHands is working' and run it."


def main() -> int:
    analyst_fallbacks = os.environ.get("LLM_ANALYST_FALLBACK_MODELS", "")
    fallback_model = next(
        (candidate.strip() for candidate in analyst_fallbacks.split(",") if candidate.strip()),
        "",
    )
    model = (
        os.environ.get("OPENHANDS_SMOKE_MODEL")
        or fallback_model
        or os.environ.get("LLM_ANALYST_MODEL")
        or "groq/openai/gpt-oss-120b"
    )
    base_url = os.environ.get("OPENHANDS_SMOKE_BASE_URL")
    if model.startswith("groq/") and not base_url:
        # The OpenHands SDK's Groq guide recommends the OpenAI-compatible
        # endpoint for native tool calls.
        model = f"openai/{model.removeprefix('groq/')}"
        base_url = "https://api.groq.com/openai/v1"
    api_key = (
        os.environ.get("OPENHANDS_SMOKE_API_KEY")
        or os.environ.get("LLM_ANALYST_API_KEY")
        or os.environ.get("GROQ_API_KEY")
    )
    if not api_key:
        print(
            "ERROR: Set OPENHANDS_SMOKE_API_KEY, LLM_ANALYST_API_KEY, "
            "or GROQ_API_KEY in .env"
        )
        return 1

    WORKSPACE.mkdir(exist_ok=True)
    PERSISTENCE_DIR.mkdir(exist_ok=True)
    hello_py = WORKSPACE / "hello.py"
    if hello_py.exists():
        hello_py.unlink()

    print(f"=== OpenHands smoke test ===")
    print(f"LLM: {model}")
    if base_url:
        print(f"LLM base URL: {base_url}")
    print(f"Workspace: {WORKSPACE}")
    print(f"Task: {TASK}")
    print("=" * 60)

    llm = LLM(
        model=model,
        api_key=api_key,
        base_url=base_url,
        max_output_tokens=200,
        num_retries=3,
        retry_min_wait=45,
        reasoning_effort="none",
    )
    # Basic default agent: default system prompt, default tools (terminal,
    # file_editor, task_tracker). No custom prompt or tools.
    agent = get_default_agent(llm=llm, cli_mode=True)
    conversation = Conversation(
        agent=agent,
        workspace=str(WORKSPACE),
        persistence_dir=str(PERSISTENCE_DIR),
        visualizer=None,
    )

    run_error = None
    try:
        conversation.send_message(TASK)
        conversation.run()
    except Exception as exc:  # noqa: BLE001 - smoke test, print everything
        run_error = exc

    print("=" * 60)
    print("=== Agent run finished ===")

    if run_error is not None:
        print(f"RUN ERROR: {type(run_error).__name__}: {run_error}")

    # Final agent message from the conversation history.
    final_message = None
    for event in reversed(list(conversation.state.events)):
        if isinstance(event, MessageEvent) and event.source == "agent":
            text_parts = [c.text for c in event.llm_message.content if hasattr(c, "text")]
            final_message = "\n".join(text_parts).strip() or None
            break
    print(f"Final agent message: {final_message or '(none)'}")

    # Verify hello.py was created and actually runs.
    print("=" * 60)
    created = hello_py.exists()
    print(f"hello.py created: {created}")
    ran_ok = False
    if created:
        print("--- hello.py contents ---")
        print(hello_py.read_text(encoding="utf-8"))
        print("--- running hello.py ---")
        result = subprocess.run(
            [sys.executable, str(hello_py)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        print(f"stdout: {result.stdout.strip()}")
        print(f"stderr: {result.stderr.strip()}")
        print(f"exit code: {result.returncode}")
        ran_ok = result.returncode == 0 and "OpenHands is working" in result.stdout

    print("=" * 60)
    success = created and ran_ok and run_error is None
    print(f"SMOKE TEST RESULT: {'PASS' if success else 'FAIL'}")
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
