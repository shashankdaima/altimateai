"""
SoftwareAgency — CrewAI pipeline that turns a PRD into a working full-stack app.

Pipeline stages
───────────────
  Phase 1  manager → contracts → ui + backend   (sequential crew)
  Phase 2  frontend agent with injected UI HTML  (single-task crew)
  Phase 3  reviewer loop — up to MAX_REVIEW_ROUNDS fix passes
"""

import json
import re
import sys
from pathlib import Path

from crewai import Agent, Crew, LLM, Process, Task

# Make project root importable when running directly
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.tools.file_writer import write_json, write_text  # noqa
from src.agents.prompts import backend, contract, frontend, manager, reviewer, ui_designer  # noqa
from src.agents.utils import (  # noqa
    _fix_contracts_with_llm,
    _js_check,
    _compile_check,
    _load_prd,
    _parse_contracts,
    _parse_files,
    _read_ws,
    _save_files,
)
from src.config import USE_LOCAL_MODEL


class SoftwareAgency:
    """
    Orchestrates the full code-generation pipeline for a given PRD.

    Usage
    -----
        agency = SoftwareAgency("samples/TodoPRD.pdf", "workspaces/output")
        outputs = agency.run()
    """

    MAX_REVIEW_ROUNDS = 3

    def __init__(self, prd_path: str, workspace: str = "workspaces/output") -> None:
        """
        Initialise the agency.

        Parameters
        ----------
        prd_path:  Path to a PDF or plain-text PRD file.
        workspace: Directory where all generated artefacts will be written.
        """
        self.prd_path = prd_path
        self.ws = Path(workspace)
        self.ws.mkdir(parents=True, exist_ok=True)

        self.prd_text: str = _load_prd(prd_path)
        self.llm: LLM = self._make_llm()

        # Populated by _setup_agents()
        self.mgr_agent: Agent
        self.contract_agent: Agent
        self.ui_agent: Agent
        self.fe_agent: Agent
        self.be_agent: Agent
        self.review_agent: Agent

        # Populated during the run
        self.design_contract: dict = {}
        self.data_contract: dict = {}
        self.ui_html: str = ""
        self.outputs: dict = {}

    # ------------------------------------------------------------------
    # LLM factory
    # ------------------------------------------------------------------

    def _make_llm(self) -> LLM:
        """
        Return the LLM instance based on the MODEL_CONFIG env variable.

        Uses Anthropic Claude Sonnet when MODEL_CONFIG=cloud (default),
        or a local Ollama llama3.2 endpoint when MODEL_CONFIG=local.
        """
        if USE_LOCAL_MODEL:
            return LLM(model="anthropic/claude-sonnet-4-6")
        return LLM(model="ollama/llama3.2", base_url="http://localhost:11434")

    # ------------------------------------------------------------------
    # Agent setup
    # ------------------------------------------------------------------

    def _setup_agents(self) -> None:
        """
        Instantiate all CrewAI agents and store them as instance attributes.

        Each agent gets the shared LLM and the role/goal/backstory defined
        in its corresponding prompt module under src/agents/prompts/.
        """
        self.mgr_agent = Agent(
            role=manager.ROLE,
            goal=manager.GOAL,
            backstory=manager.BACKSTORY,
            llm=self.llm,
            verbose=True,
        )
        self.contract_agent = Agent(
            role=contract.ROLE,
            goal=contract.GOAL,
            backstory=contract.BACKSTORY,
            llm=self.llm,
            verbose=True,
        )
        self.ui_agent = Agent(
            role=ui_designer.ROLE,
            goal=ui_designer.GOAL,
            backstory=ui_designer.BACKSTORY,
            llm=self.llm,
            verbose=True,
        )
        self.fe_agent = Agent(
            role=frontend.ROLE,
            goal=frontend.GOAL,
            backstory=frontend.BACKSTORY,
            llm=self.llm,
            verbose=True,
        )
        self.be_agent = Agent(
            role=backend.ROLE,
            goal=backend.GOAL,
            backstory=backend.BACKSTORY,
            llm=self.llm,
            verbose=True,
        )
        self.review_agent = Agent(
            role=reviewer.ROLE,
            goal=reviewer.GOAL,
            backstory=reviewer.BACKSTORY,
            llm=self.llm,
            verbose=True,
        )

    # ------------------------------------------------------------------
    # Phase 1 — manager → contracts → ui + backend
    # ------------------------------------------------------------------

    def _run_phase1(self) -> tuple[Task, Task, Task, Task]:
        """
        Run the first sequential crew: manager → contracts → UI designer → backend.

        Returns the four completed Task objects so their outputs can be
        inspected and persisted by _persist_phase1().

        Flow
        ----
          task_plan      → manager reads the PRD and produces a Markdown plan
          task_contracts → contract architect produces design + data contracts
          task_ui        → UI designer produces ui/index.html from design_contract
          task_backend   → backend developer produces backend/main.py from data_contract
        """
        task_plan = Task(
            description=manager.task_description(self.prd_text),
            expected_output=manager.TASK_EXPECTED_OUTPUT,
            agent=self.mgr_agent,
        )
        task_contracts = Task(
            description=contract.task_description(),
            expected_output=contract.TASK_EXPECTED_OUTPUT,
            agent=self.contract_agent,
            context=[task_plan],
        )
        task_ui = Task(
            description=ui_designer.task_description(),
            expected_output=ui_designer.TASK_EXPECTED_OUTPUT,
            agent=self.ui_agent,
            context=[task_contracts],
        )
        task_backend = Task(
            description=backend.task_description(),
            expected_output=backend.TASK_EXPECTED_OUTPUT,
            agent=self.be_agent,
            context=[task_contracts],
        )

        Crew(
            agents=[self.mgr_agent, self.contract_agent, self.ui_agent, self.be_agent],
            tasks=[task_plan, task_contracts, task_ui, task_backend],
            process=Process.sequential,
            verbose=True,
        ).kickoff()

        return task_plan, task_contracts, task_ui, task_backend

    def _persist_phase1(
        self,
        task_plan: Task,
        task_contracts: Task,
        task_ui: Task,
        task_backend: Task,
    ) -> None:
        """
        Save all Phase 1 artefacts to the workspace and populate instance state.

        Writes
        ------
          plan.md
          contracts/design_contract.json
          contracts/data_contract.json
          ui/index.html
          frontend/index.html   (copy of ui/index.html, required by main.js)
          backend/main.py  (+ requirements.txt if produced)

        Also parses and repairs contract JSON, storing the dicts in
        self.design_contract, self.data_contract, and self.ui_html.
        """
        # Plan
        plan_text: str = task_plan.output.raw
        write_text(str(self.ws / "plan.md"), plan_text)
        self.outputs["plan"] = str(self.ws / "plan.md")

        # Contracts — attempt strict parse, then json_repair, then LLM repair
        try:
            self.design_contract, self.data_contract = _parse_contracts(
                task_contracts.output.raw
            )
        except Exception as exc:
            print(f"[contracts] Initial parse failed: {exc}")
            self.design_contract, self.data_contract = _fix_contracts_with_llm(
                task_contracts.output.raw, self.llm
            )

        write_json(str(self.ws / "contracts" / "design_contract.json"), self.design_contract)
        write_json(str(self.ws / "contracts" / "data_contract.json"), self.data_contract)
        self.outputs["design_contract"] = self.design_contract
        self.outputs["data_contract"] = self.data_contract

        # UI HTML
        ui_files = _parse_files(task_ui.output.raw, "ui/")
        _save_files(ui_files, self.ws)
        self.ui_html = ui_files.get("ui/index.html", task_ui.output.raw)

        # Copy ui/index.html → frontend/index.html so main.js loads alongside it
        fe_html_path = self.ws / "frontend" / "index.html"
        fe_html_path.parent.mkdir(parents=True, exist_ok=True)
        fe_html_path.write_text(self.ui_html, encoding="utf-8")
        print("  [copied] ui/index.html → frontend/index.html")

        # Backend
        be_files = _parse_files(task_backend.output.raw, "backend/")
        _save_files(be_files, self.ws)

    # ------------------------------------------------------------------
    # Phase 2 — frontend (needs UI HTML from Phase 1)
    # ------------------------------------------------------------------

    def _run_phase2(self, task_contracts: Task) -> None:
        """
        Run the second crew: frontend developer produces frontend/main.js.

        The UI HTML generated in Phase 1 is injected directly into the task
        description so the agent knows every element id and screen name before
        it fills in the JS template.

        Falls back to saving the raw agent output as main.js if the agent
        omits the '=== FILE: ===' delimiter.

        Parameters
        ----------
        task_contracts: The completed contracts Task from Phase 1, passed as
                        context so the agent can read the data_contract endpoints.
        """
        task_frontend = Task(
            description=frontend.task_description(self.ui_html),
            expected_output=frontend.TASK_EXPECTED_OUTPUT,
            agent=self.fe_agent,
            context=[task_contracts],
        )

        Crew(
            agents=[self.fe_agent],
            tasks=[task_frontend],
            process=Process.sequential,
            verbose=True,
        ).kickoff()

        fe_files = _parse_files(task_frontend.output.raw, "frontend/")
        if fe_files:
            _save_files(fe_files, self.ws)
        else:
            fallback = self.ws / "frontend" / "main.js"
            fallback.write_text(task_frontend.output.raw, encoding="utf-8")
            print(f"  [fallback] saved raw frontend output → {fallback}")

    # ------------------------------------------------------------------
    # Phase 3 — review loop
    # ------------------------------------------------------------------

    def _run_review_loop(self) -> None:
        """
        Run up to MAX_REVIEW_ROUNDS rounds of automated review and repair.

        Each round:
          1. Static checks (_compile_check, _js_check) produce deterministic
             error strings that are injected into the reviewer's task so it
             cannot overlook them.
          2. The reviewer LLM reads all artefacts + contract and outputs a
             structured JSON report: {pass, ui:{ok,issues}, frontend:{ok,issues},
             backend:{ok,issues}}.
          3. Any component flagged ok=false is re-generated with its issues
             appended to the original task description.
          4. If the reviewer reports pass=true, or no component was re-run,
             the loop exits early.
        """
        for round_num in range(1, self.MAX_REVIEW_ROUNDS + 1):
            print(f"\n[review] Round {round_num}/{self.MAX_REVIEW_ROUNDS} ...")

            static_errors = _compile_check(self.ws) + _js_check(self.ws)

            review_task = Task(
                description=reviewer.task_description(
                    design_contract=json.dumps(self.design_contract, indent=2),
                    data_contract=json.dumps(self.data_contract, indent=2),
                    ui_html=_read_ws(self.ws / "ui" / "index.html"),
                    main_js=_read_ws(self.ws / "frontend" / "main.js"),
                    backend_py=_read_ws(self.ws / "backend" / "main.py"),
                    compile_errors=static_errors,
                ),
                expected_output=reviewer.TASK_EXPECTED_OUTPUT,
                agent=self.review_agent,
            )
            Crew(
                agents=[self.review_agent],
                tasks=[review_task],
                process=Process.sequential,
                verbose=True,
            ).kickoff()

            report = self._parse_review_report(review_task.output.raw)
            if report is None:
                break

            print(f"[review] Report: {json.dumps(report, indent=2)}")

            # Compute pass ourselves — never trust the LLM's pass field directly,
            # since it sometimes sets pass=true while individual ok fields are false.
            all_ok = (
                report.get("ui", {}).get("ok", True)
                and report.get("frontend", {}).get("ok", True)
                and report.get("backend", {}).get("ok", True)
            )
            if all_ok:
                print("[review] All checks passed.")
                break

            reran = self._apply_review_fixes(report)
            if not reran:
                break

    def _parse_review_report(self, raw: str) -> dict | None:
        """
        Parse the reviewer's JSON output into a Python dict.

        Strips markdown code fences before parsing. Returns None if parsing
        fails so the caller can break out of the review loop gracefully.

        Parameters
        ----------
        raw: The raw string output from the reviewer agent.

        Returns
        -------
        A dict with keys 'pass', 'ui', 'frontend', 'backend', or None on error.
        """
        try:
            cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()
            return json.loads(cleaned)
        except Exception as exc:
            print(f"[review] Could not parse reviewer output: {exc}")
            return None

    def _apply_review_fixes(self, report: dict) -> bool:
        """
        Re-run whichever agents have issues reported by the reviewer.

        For each component (ui, frontend, backend) where ok=false, the
        original task is re-created with the reviewer's issues string appended
        to the description, then a fresh single-task crew is kicked off and
        the output saved to the workspace.

        Parameters
        ----------
        report: The parsed reviewer JSON report.

        Returns
        -------
        True if at least one component was re-run, False otherwise.
        """
        reran = False

        if not report.get("ui", {}).get("ok", True):
            print(f"[review] Fixing UI: {report['ui']['issues']}")
            t = Task(
                description=ui_designer.task_description()
                    + f"\n\nReviewer issues to fix:\n{report['ui']['issues']}",
                expected_output=ui_designer.TASK_EXPECTED_OUTPUT,
                agent=self.ui_agent,
            )
            Crew(agents=[self.ui_agent], tasks=[t], process=Process.sequential,
                 verbose=True).kickoff()
            new_ui = _parse_files(t.output.raw, "ui/")
            _save_files(new_ui, self.ws)
            self.ui_html = new_ui.get("ui/index.html", self.ui_html)
            (self.ws / "frontend" / "index.html").write_text(self.ui_html, encoding="utf-8")
            reran = True

        if not report.get("frontend", {}).get("ok", True):
            print(f"[review] Fixing frontend: {report['frontend']['issues']}")
            t = Task(
                description=frontend.task_description(self.ui_html)
                    + f"\n\nReviewer issues to fix:\n{report['frontend']['issues']}",
                expected_output=frontend.TASK_EXPECTED_OUTPUT,
                agent=self.fe_agent,
            )
            Crew(agents=[self.fe_agent], tasks=[t], process=Process.sequential,
                 verbose=True).kickoff()
            fe_fixed = _parse_files(t.output.raw, "frontend/")
            if fe_fixed:
                _save_files(fe_fixed, self.ws)
            else:
                (self.ws / "frontend" / "main.js").write_text(t.output.raw, encoding="utf-8")
            reran = True

        if not report.get("backend", {}).get("ok", True):
            print(f"[review] Fixing backend: {report['backend']['issues']}")
            t = Task(
                description=backend.task_description()
                    + f"\n\nReviewer issues to fix:\n{report['backend']['issues']}",
                expected_output=backend.TASK_EXPECTED_OUTPUT,
                agent=self.be_agent,
            )
            Crew(agents=[self.be_agent], tasks=[t], process=Process.sequential,
                 verbose=True).kickoff()
            _save_files(_parse_files(t.output.raw, "backend/"), self.ws)
            reran = True

        return reran

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def run(self) -> dict:
        """
        Execute the full pipeline and return a summary of written artefacts.

        Stages
        ------
          1. Set up all agents.
          2. Phase 1: manager → contracts → UI → backend.
          3. Persist Phase 1 outputs (parse contracts, save files).
          4. Phase 2: frontend (main.js) with injected UI HTML.
          5. Phase 3: review loop (up to MAX_REVIEW_ROUNDS passes).

        Returns
        -------
        A dict containing:
          plan            — path to plan.md
          design_contract — the parsed design contract dict
          data_contract   — the parsed data contract dict
          workspace       — absolute path to the output directory
        """
        self._setup_agents()

        task_plan, task_contracts, task_ui, task_backend = self._run_phase1()
        self._persist_phase1(task_plan, task_contracts, task_ui, task_backend)
        self._run_phase2(task_contracts)
        self._run_review_loop()

        self.outputs["workspace"] = str(self.ws.resolve())
        print(f"\n[done] All files written to {self.ws.resolve()}")
        return self.outputs


# ---------------------------------------------------------------------------
# Public helper kept for backward compatibility
# ---------------------------------------------------------------------------

def run_agency(prd_path: str, workspace: str = "workspaces/output") -> dict:
    """
    Convenience wrapper around SoftwareAgency.run().

    Parameters
    ----------
    prd_path:  Path to a PDF or plain-text PRD file.
    workspace: Directory where all generated artefacts will be written.

    Returns
    -------
    Same dict as SoftwareAgency.run().
    """
    return SoftwareAgency(prd_path, workspace).run()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m src.agents.agents <prd_path> [workspace_dir]")
        sys.exit(1)

    _prd = sys.argv[1]
    _ws = sys.argv[2] if len(sys.argv) > 2 else "workspaces/output"
    run_agency(_prd, _ws)
