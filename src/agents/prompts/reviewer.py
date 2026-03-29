ROLE = "QA Reviewer"

GOAL = (
    "Review every generated file against the contracts and report exactly which "
    "component (ui, frontend, backend) has issues and what must be fixed."
)

BACKSTORY = (
    "You are a meticulous QA engineer. You read contracts and generated code with equal "
    "care. You never guess — you only report concrete, actionable issues. "
    "Your output is always valid JSON so the pipeline can parse and act on it."
)


def task_description(
    design_contract: str,
    data_contract: str,
    ui_html: str,
    main_js: str,
    backend_py: str,
    compile_errors: str,
) -> str:
    return (
        "Review the generated files below against the contracts.\n\n"
        "## design_contract\n```json\n" + design_contract + "\n```\n\n"
        "## data_contract\n```json\n" + data_contract + "\n```\n\n"
        "## ui/index.html\n```html\n" + ui_html + "\n```\n\n"
        "## frontend/main.js\n```javascript\n" + main_js + "\n```\n\n"
        "## backend/main.py\n```python\n" + backend_py + "\n```\n\n"
        "## Compilation errors (empty string means no errors)\n"
        + (compile_errors or "(none)") + "\n\n"
        "---\n\n"
        "Output ONLY a JSON object — no prose, no markdown fences:\n\n"
        "{\n"
        '  "pass": <true only if ALL three ok fields are true, false otherwise>,\n'
        '  "ui":       { "ok": true,  "issues": "" },\n'
        '  "frontend": { "ok": true,  "issues": "" },\n'
        '  "backend":  { "ok": true,  "issues": "" }\n'
        "}\n\n"
        "CRITICAL: `pass` must be false if ANY component has ok=false. "
        "Setting pass=true with any ok=false is always wrong.\n\n"
        "Check each component against these criteria:\n\n"
        "### ui\n"
        "- Every screen in design_contract.screens (excluding auth) has a "
        "  <section id=\"screen-X\"> in index.html.\n"
        "- Every feature in design_contract.screens[*].features is present as a UI element.\n"
        "- <script src=\"main.js\"> exists just before </body>.\n"
        "- No inline JS (no onclick, no <script> blocks).\n\n"
        "### frontend\n"
        "- No syntax errors (check compile_errors field above).\n"
        "- SCREENS array values are id suffixes only (e.g. 'dashboard', not 'screen-dashboard').\n"
        "- No PLACEHOLDER_ or @@FILL markers remain in main.js.\n"
        "- All async render functions and wireEvents() are defined at the TOP LEVEL — "
        "  NOT inside the boot IIFE `(async () => { ... })()`.\n"
        "- Every data_contract endpoint used in main.js matches the contract path exactly "
        "  (no /api/ prefix, no extra path segments like /new or /delete).\n"
        "- Render functions only call LIST endpoints (GET /resource) — never by dynamic id.\n"
        "- API calls never use a SCREENS value as an item id — item ids come from data (t.id).\n"
        "- Every render function corresponds to a screen that exists in the HTML.\n"
        "- wireEvents() attaches listeners for every static button/input/checkbox id in the HTML.\n"
        "- No duplicate const declarations (e.g. const btnDelete declared twice).\n\n"
        "### backend\n"
        "- No syntax errors (check compile_errors field above).\n"
        "- CORSMiddleware is imported AND added via app.add_middleware.\n"
        "- Every endpoint in data_contract.endpoints is implemented.\n"
        "- Every SQLModel table class has a primary key field.\n"
        "- Table creation uses Model.model_validate(body.model_dump()) — reject Model(model_dict=...).\n"
        "- Updates use body.model_dump(exclude_unset=True) — reject body.model_dict(...).\n"
        "- No method called model_dict anywhere — the correct method is model_dump.\n"
        "- No undefined names referenced (e.g. schemas used before defined).\n\n"
        "Set ok=false and describe the concrete issues in the issues string. "
        "If everything is fine set ok=true and issues=\"\"."
    ).strip()


TASK_EXPECTED_OUTPUT = (
    "A single JSON object with keys: pass, ui, frontend, backend. "
    "Each sub-key has ok (bool) and issues (string). No prose outside the JSON."
)
