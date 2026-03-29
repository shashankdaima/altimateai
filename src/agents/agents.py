import json
import re
import sys
from pathlib import Path

from crewai import Agent, Crew, LLM, Process, Task

# Make project root importable when running directly
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.tools.file_writer import write_json, write_text# noqa
from src.tools.pdf_reader import extract_text  # noqa
from src.agents.prompts import backend, contract, frontend, manager, ui_designer # noqa
from src.config import USE_LOCAL_MODEL

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_prd(prd_path: str) -> str:
    if prd_path.lower().endswith(".pdf"):
        return extract_text(prd_path)
    return Path(prd_path).read_text(encoding="utf-8")


def _parse_files(raw: str, prefix: str) -> dict[str, str]:
    """Extract files from agent output delimited by '=== FILE: <path> ==='."""
    pattern = re.compile(r"=== FILE:\s*(.+?)\s*===\s*\n(.*?)(?==== FILE:|$)", re.DOTALL)
    return {m.group(1).strip(): m.group(2).strip() for m in pattern.finditer(raw)}


def _save_files(files: dict[str, str], workspace: Path) -> None:
    for rel_path, content in files.items():
        dest = workspace / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
        print(f"  [saved] {dest}")


def _parse_contracts(raw: str) -> tuple[dict, dict]:
    """Extract design_contract and data_contract from JSON agent output."""
    cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()
    data = json.loads(cleaned)
    return data["design_contract"], data["data_contract"]


def _fix_contracts_with_llm(bad_raw: str, llm, max_retries: int = 3) -> tuple[dict, dict]:
    """Re-prompt the LLM to fix broken JSON, retrying up to max_retries times."""
    current = bad_raw
    for attempt in range(1, max_retries + 1):
        print(f"[contracts] JSON parse failed — asking LLM to fix it (attempt {attempt}/{max_retries}) ...")
        fix_task = Task(
            description=(
                "The following output was supposed to be a valid JSON object with keys "
                "`design_contract` and `data_contract`, but it has syntax errors.\n\n"
                "Broken output:\n"
                "```\n" + current + "\n```\n\n"
                "Return ONLY the corrected, valid JSON object — no markdown fences, "
                "no prose, no extra keys. Just raw JSON."
            ),
            expected_output="A single valid JSON object with keys `design_contract` and `data_contract`.",
            agent=Agent(
                role="JSON Repair Specialist",
                goal="Fix broken JSON and return only valid JSON.",
                backstory="You fix malformed JSON outputs. You return only raw valid JSON, nothing else.",
                llm=llm,
                verbose=False,
            ),
        )
        Crew(agents=[fix_task.agent], tasks=[fix_task], process=Process.sequential).kickoff()
        current = fix_task.output.raw
        try:
            return _parse_contracts(current)
        except Exception as exc:
            print(f"[contracts] Still invalid after attempt {attempt}: {exc}")
    raise ValueError(f"Could not produce valid contract JSON after {max_retries} attempts.")


# ---------------------------------------------------------------------------
# Agency
# ---------------------------------------------------------------------------

def run_agency(prd_path: str, workspace: str = "workspaces/output") -> dict:
    """
    Run the full software agency pipeline.

    Args:
        prd_path:  Path to a PDF or text PRD file.
        workspace: Directory where all generated files will be saved.

    Returns:
        A dict with keys: plan, design_contract, data_contract,
        and the paths of every written file.
    """
    ws = Path(workspace)
    ws.mkdir(parents=True, exist_ok=True)

    prd_text = _load_prd(prd_path)
    if(USE_LOCAL_MODEL):
        llm = LLM(model="anthropic/claude-sonnet-4-6")
    else:
        llm = LLM(model="ollama/llama3.2", base_url="http://localhost:11434")

    # ------------------------------------------------------------------
    # Agents
    # ------------------------------------------------------------------
    mgr_agent = Agent(
        role=manager.ROLE,
        goal=manager.GOAL,
        backstory=manager.BACKSTORY,
        llm=llm,
        verbose=True,
    )

    contract_agent = Agent(
        role=contract.ROLE,
        goal=contract.GOAL,
        backstory=contract.BACKSTORY,
        llm=llm,
        verbose=True,
    )

    ui_agent = Agent(
        role=ui_designer.ROLE,
        goal=ui_designer.GOAL,
        backstory=ui_designer.BACKSTORY,
        llm=llm,
        verbose=True,
    )

    fe_agent = Agent(
        role=frontend.ROLE,
        goal=frontend.GOAL,
        backstory=frontend.BACKSTORY,
        llm=llm,
        verbose=True,
    )

    be_agent = Agent(
        role=backend.ROLE,
        goal=backend.GOAL,
        backstory=backend.BACKSTORY,
        llm=llm,
        verbose=True,
    )

    # ------------------------------------------------------------------
    # Tasks
    # ------------------------------------------------------------------
    task_plan = Task(
        description=manager.task_description(prd_text),
        expected_output=manager.TASK_EXPECTED_OUTPUT,
        agent=mgr_agent,
    )

    task_contracts = Task(
        description=contract.task_description(),
        expected_output=contract.TASK_EXPECTED_OUTPUT,
        agent=contract_agent,
        context=[task_plan],
    )

    task_ui = Task(
        description=ui_designer.task_description(),
        expected_output=ui_designer.TASK_EXPECTED_OUTPUT,
        agent=ui_agent,
        context=[task_contracts],
    )

    task_backend = Task(
        description=backend.task_description(),
        expected_output=backend.TASK_EXPECTED_OUTPUT,
        agent=be_agent,
        context=[task_contracts],
    )

    # ------------------------------------------------------------------
    # Phase 1: manager → contracts → ui + backend (parallel-ish, sequential process)
    # ------------------------------------------------------------------
    crew_phase1 = Crew(
        agents=[mgr_agent, contract_agent, ui_agent, be_agent],
        tasks=[task_plan, task_contracts, task_ui, task_backend],
        process=Process.sequential,
        verbose=True,
    )
    crew_phase1.kickoff()

    # ------------------------------------------------------------------
    # Persist phase 1 outputs
    # ------------------------------------------------------------------
    outputs: dict = {}

    plan_text: str = task_plan.output.raw
    write_text(str(ws / "plan.md"), plan_text)
    outputs["plan"] = str(ws / "plan.md")

    try:
        design_contract, data_contract = _parse_contracts(task_contracts.output.raw)
    except Exception as exc:
        print(f"[contracts] Initial parse failed: {exc}")
        design_contract, data_contract = _fix_contracts_with_llm(task_contracts.output.raw, llm)

    write_json(str(ws / "contracts" / "design_contract.json"), design_contract)
    write_json(str(ws / "contracts" / "data_contract.json"), data_contract)
    outputs["design_contract"] = design_contract
    outputs["data_contract"] = data_contract

    ui_files = _parse_files(task_ui.output.raw, "ui/")
    _save_files(ui_files, ws)

    # Copy ui/index.html → frontend/index.html so main.js loads alongside it
    ui_html = ui_files.get("ui/index.html", task_ui.output.raw)
    fe_html_path = ws / "frontend" / "index.html"
    fe_html_path.parent.mkdir(parents=True, exist_ok=True)
    fe_html_path.write_text(ui_html, encoding="utf-8")
    print(f"  [copied] ui/index.html → frontend/index.html")

    be_files = _parse_files(task_backend.output.raw, "backend/")
    _save_files(be_files, ws)

    # ------------------------------------------------------------------
    # Phase 2: frontend — inject actual UI HTML into the task description
    # ------------------------------------------------------------------

    task_frontend = Task(
        description=frontend.task_description(ui_html),
        expected_output=frontend.TASK_EXPECTED_OUTPUT,
        agent=fe_agent,
        context=[task_contracts],
    )

    crew_phase2 = Crew(
        agents=[fe_agent],
        tasks=[task_frontend],
        process=Process.sequential,
        verbose=True,
    )
    crew_phase2.kickoff()

    # Only main.js is expected — save it into frontend/
    fe_files = _parse_files(task_frontend.output.raw, "frontend/")
    if fe_files:
        _save_files(fe_files, ws)
    else:
        # Agent didn't use the delimiter — save raw output as main.js
        fallback = ws / "frontend" / "main.js"
        fallback.write_text(task_frontend.output.raw, encoding="utf-8")
        print(f"  [fallback] saved raw frontend output → {fallback}")

    outputs["workspace"] = str(ws.resolve())
    print(f"\n[done] All files written to {ws.resolve()}")
    return outputs


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m src.agents.agents <prd_path> [workspace_dir]")
        sys.exit(1)

    prd = sys.argv[1]
    ws = sys.argv[2] if len(sys.argv) > 2 else "workspaces/output"
    run_agency(prd, ws)
