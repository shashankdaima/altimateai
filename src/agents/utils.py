import json
import re
import subprocess
import sys
from pathlib import Path

from json_repair import repair_json

from crewai import Agent, Crew, Process, Task

# Make project root importable when running directly
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.tools.pdf_reader import extract_text  # noqa

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
    """
    Static + syntax checks on frontend/main.js.

    Runs `node --check` for syntax errors, then applies pattern checks for
    common structural mistakes the LLM tends to produce.
    """
    js_path = ws / "frontend" / "main.js"
    if not js_path.exists():
        return "\nfrontend/main.js not found"
    code = js_path.read_text(encoding="utf-8")
    issues = []

    # 1. Syntax check via node --check
    node = subprocess.run(
        ["node", "--check", str(js_path)],
        capture_output=True, text=True,
    )
    if node.returncode != 0:
        issues.append("JS syntax error:\n" + node.stderr.strip())

    # 2. Unfilled placeholder values still present
    if "PLACEHOLDER_" in code or "FILL_SCREEN_" in code:
        issues.append("JS: SCREENS array still has placeholder values — replace with actual screen id suffixes")

    # 3. SCREENS values must not have 'screen-' prefix
    screens_match = re.search(r"const SCREENS\s*=\s*\[([^\]]+)\]", code)
    if screens_match and "screen-" in screens_match.group(1):
        issues.append(
            "JS: SCREENS array contains 'screen-' prefix — use suffix only "
            "(e.g. 'dashboard', not 'screen-dashboard')"
        )

    # 4. No /api/ prefix in API calls
    if "'/api/" in code or '"/api/' in code:
        issues.append("JS: /api/ prefix in API call — use EXACTLY the path from data_contract")

    # 5. wireEvents must be defined at the top level
    if "function wireEvents" not in code:
        issues.append("JS: wireEvents() function is missing")

    # 6. Functions defined inside the boot IIFE
    # The boot IIFE starts with `(async () => {` — detect `async function` or
    # `function` declared after that marker, which means they are inside the IIFE.
    iife_pos = code.find("(async () => {")
    if iife_pos != -1:
        iife_body = code[iife_pos:]
        inner_fns = re.findall(r"\n\s{2,}(?:async\s+)?function\s+\w+", iife_body)
        if inner_fns:
            names = ", ".join(re.findall(r"function\s+(\w+)", " ".join(inner_fns)))
            issues.append(
                f"JS: function(s) defined inside the boot IIFE: {names}. "
                "All functions must be at the top level."
            )

    # 7. Unfilled fill-zone markers left in output
    if "@@FILL" in code or "@@END_FILL" in code:
        issues.append("JS: @@FILL / @@END_FILL markers were not replaced — fill zones are incomplete")

    return ("\n" + "\n".join(issues)) if issues else ""

