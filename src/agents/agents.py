import json
import re
import subprocess
import sys
from pathlib import Path

from json_repair import repair_json

from crewai import Agent, Crew, LLM, Process, Task

# Make project root importable when running directly
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.tools.file_writer import write_json, write_text# noqa
from src.tools.pdf_reader import extract_text  # noqa
from src.agents.prompts import backend, contract, frontend, manager, reviewer, ui_designer # noqa
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

    # 1. Try strict parse
    try:
        data = json.loads(cleaned)
        return data["design_contract"], data["data_contract"]
    except json.JSONDecodeError:
        pass

    # 2. Try programmatic repair (handles trailing commas, missing quotes, etc.)
    print("[contracts] Strict JSON parse failed — trying json_repair ...")
    repaired = repair_json(cleaned, return_objects=True)
    if isinstance(repaired, dict) and "design_contract" in repaired:
        print("[contracts] json_repair succeeded.")
        return repaired["design_contract"], repaired["data_contract"]

    raise ValueError("json_repair could not produce valid contracts.")


def _fix_contracts_with_llm(bad_raw: str, llm, max_retries: int = 3) -> tuple[dict, dict]:
    """Last resort: ask a dedicated LLM agent to rewrite the contracts as valid JSON."""
    repair_agent = Agent(
        role="JSON Contract Repair Specialist",
        goal="Rewrite broken JSON contracts as perfectly valid JSON.",
        backstory=(
            "You are an expert at reading malformed JSON and rewriting it correctly. "
            "You output ONLY raw JSON — no markdown, no prose, no explanation."
        ),
        llm=llm,
        verbose=False,
    )

    current = bad_raw
    for attempt in range(1, max_retries + 1):
        print(f"[contracts] LLM repair attempt {attempt}/{max_retries} ...")
        # Show the LLM the specific error so it knows what to target
        try:
            json.loads(re.sub(r"```(?:json)?\s*|\s*```", "", current).strip())
            error_hint = ""
        except json.JSONDecodeError as e:
            error_hint = f"\n\nSpecific error: {e}"

        fix_task = Task(
            description=(
                "The output below must be a valid JSON object with exactly two keys: "
                "`design_contract` and `data_contract`.\n"
                "It currently has syntax errors — rewrite it as valid JSON."
                + error_hint
                + "\n\nBroken output:\n```\n" + current + "\n```\n\n"
                "Return ONLY the corrected raw JSON. No markdown fences, no prose."
            ),
            expected_output="A valid JSON object with keys `design_contract` and `data_contract`.",
            agent=repair_agent,
        )
        Crew(agents=[repair_agent], tasks=[fix_task],
             process=Process.sequential).kickoff()
        current = fix_task.output.raw
        try:
            return _parse_contracts(current)
        except Exception as exc:
            print(f"[contracts] LLM repair attempt {attempt} still invalid: {exc}")

    raise ValueError(f"Could not produce valid contract JSON after {max_retries} LLM attempts.")


def _read_ws(path: Path) -> str:
    """Read a workspace file, return empty string if missing."""
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _compile_check(ws: Path) -> str:
    """Run py_compile on backend/main.py and grep for known runtime pitfalls."""
    backend_py = ws / "backend" / "main.py"
    if not backend_py.exists():
        return "backend/main.py not found"
    result = subprocess.run(
        [sys.executable, "-m", "py_compile", str(backend_py)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return f"backend/main.py syntax error:\n{result.stderr}"

    # Additional static checks for known runtime pitfalls
    code = backend_py.read_text(encoding="utf-8")
    issues = []
    if "model_dict" in code:
        issues.append("model_dict() is not a real Pydantic/SQLModel method — use model_dump() instead")
    if "body.dict(" in code:
        issues.append("body.dict() is deprecated — use body.model_dump()")
    if "CORSMiddleware" not in code:
        issues.append("CORSMiddleware missing — CORS will be broken")
    return "\n".join(issues)


def _js_check(ws: Path) -> str:
    """Static checks on frontend/main.js for known pitfalls."""
    js_path = ws / "frontend" / "main.js"
    if not js_path.exists():
        return "\nfrontend/main.js not found"
    code = js_path.read_text(encoding="utf-8")
    issues = []

    # SCREENS values must be plain suffixes (no 'screen-' prefix inside the array)
    import re
    screens_match = re.search(r"const SCREENS\s*=\s*\[([^\]]+)\]", code)
    if screens_match:
        entries = screens_match.group(1)
        if "screen-" in entries:
            issues.append(
                "JS: SCREENS array contains 'screen-' prefix — values must be "
                "suffixes only (e.g. 'dashboard', not 'screen-dashboard')"
            )

    # API paths must not contain /api/
    if "'/api/" in code or '"/api/' in code:
        issues.append("JS: API call uses /api/ prefix — paths must match data_contract exactly (no /api/)")

    # Must define wireEvents
    if "function wireEvents" not in code:
        issues.append("JS: wireEvents() function is missing")

    return ("\n" + "\n".join(issues)) if issues else ""


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
    print("  [copied] ui/index.html → frontend/index.html")

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
        fallback = ws / "frontend" / "main.js"
        fallback.write_text(task_frontend.output.raw, encoding="utf-8")
        print(f"  [fallback] saved raw frontend output → {fallback}")

    # ------------------------------------------------------------------
    # Phase 3: review loop — up to 3 attempts per component
    # ------------------------------------------------------------------
    review_agent = Agent(
        role=reviewer.ROLE,
        goal=reviewer.GOAL,
        backstory=reviewer.BACKSTORY,
        llm=llm,
        verbose=True,
    )

    MAX_REVIEW_ROUNDS = 3
    for round_num in range(1, MAX_REVIEW_ROUNDS + 1):
        print(f"\n[review] Round {round_num}/{MAX_REVIEW_ROUNDS} ...")

        # Collect compile + static errors
        compile_errors = _compile_check(ws)
        compile_errors += _js_check(ws)

        review_task = Task(
            description=reviewer.task_description(
                design_contract=json.dumps(design_contract, indent=2),
                data_contract=json.dumps(data_contract, indent=2),
                ui_html=_read_ws(ws / "ui" / "index.html"),
                main_js=_read_ws(ws / "frontend" / "main.js"),
                backend_py=_read_ws(ws / "backend" / "main.py"),
                compile_errors=compile_errors,
            ),
            expected_output=reviewer.TASK_EXPECTED_OUTPUT,
            agent=review_agent,
        )
        Crew(agents=[review_agent], tasks=[review_task],
             process=Process.sequential, verbose=True).kickoff()

        try:
            raw = re.sub(r"```(?:json)?\s*|\s*```", "", review_task.output.raw).strip()
            report = json.loads(raw)
        except Exception as exc:
            print(f"[review] Could not parse reviewer output: {exc}")
            break

        print(f"[review] Report: {json.dumps(report, indent=2)}")

        if report.get("pass"):
            print("[review] All checks passed.")
            break

        reran = False

        # Re-run UI designer
        if not report.get("ui", {}).get("ok", True):
            print(f"[review] Fixing UI: {report['ui']['issues']}")
            t = Task(
                description=ui_designer.task_description()
                    + f"\n\nReviewer issues to fix:\n{report['ui']['issues']}",
                expected_output=ui_designer.TASK_EXPECTED_OUTPUT,
                agent=ui_agent,
                context=[task_contracts],
            )
            Crew(agents=[ui_agent], tasks=[t], process=Process.sequential,
                 verbose=True).kickoff()
            new_ui = _parse_files(t.output.raw, "ui/")
            _save_files(new_ui, ws)
            ui_html = new_ui.get("ui/index.html", ui_html)
            (ws / "frontend" / "index.html").write_text(ui_html, encoding="utf-8")
            reran = True

        # Re-run frontend
        if not report.get("frontend", {}).get("ok", True):
            print(f"[review] Fixing frontend: {report['frontend']['issues']}")
            t = Task(
                description=frontend.task_description(ui_html)
                    + f"\n\nReviewer issues to fix:\n{report['frontend']['issues']}",
                expected_output=frontend.TASK_EXPECTED_OUTPUT,
                agent=fe_agent,
            )
            Crew(agents=[fe_agent], tasks=[t], process=Process.sequential,
                 verbose=True).kickoff()
            fe_fixed = _parse_files(t.output.raw, "frontend/")
            if fe_fixed:
                _save_files(fe_fixed, ws)
            else:
                (ws / "frontend" / "main.js").write_text(
                    t.output.raw, encoding="utf-8")
            reran = True

        # Re-run backend
        if not report.get("backend", {}).get("ok", True):
            print(f"[review] Fixing backend: {report['backend']['issues']}")
            t = Task(
                description=backend.task_description()
                    + f"\n\nReviewer issues to fix:\n{report['backend']['issues']}",
                expected_output=backend.TASK_EXPECTED_OUTPUT,
                agent=be_agent,
                context=[task_contracts],
            )
            Crew(agents=[be_agent], tasks=[t], process=Process.sequential,
                 verbose=True).kickoff()
            _save_files(_parse_files(t.output.raw, "backend/"), ws)
            reran = True

        if not reran:
            break

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
