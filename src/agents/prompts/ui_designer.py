ROLE = "UI Designer"

GOAL = (
    "Fill in the provided HTML template with the correct screens and UI elements "
    "from the design_contract. Do not change the template structure."
)

BACKSTORY = (
    "You are a UI developer. You receive a fixed HTML template and fill in each "
    "<section> with the correct elements, IDs, and Tailwind classes. "
    "You never deviate from the template structure."
)

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>FILL_APP_TITLE</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-50 text-gray-800 font-sans">

  <!-- Nav bar: one <button> per screen, id="nav-SCREEN_NAME" -->
  <nav class="bg-white shadow px-6 py-3 flex gap-3">
    <button id="nav-SCREEN1" class="px-4 py-2 rounded bg-blue-600 text-white font-medium">Screen 1</button>
    <button id="nav-SCREEN2" class="px-4 py-2 rounded bg-gray-200 text-gray-700 font-medium">Screen 2</button>
  </nav>

  <main class="max-w-3xl mx-auto p-6 space-y-6">

    <!-- SCREEN 1 — id must be screen-SCREEN1 -->
    <section id="screen-SCREEN1">
      <h2 class="text-2xl font-bold mb-4">Screen 1 Title</h2>

      <!-- List container — id="list-RESOURCE" -->
      <ul id="list-RESOURCE" class="space-y-2 mb-4"></ul>

      <!-- Add form -->
      <div class="flex gap-2">
        <input id="input-RESOURCE-title" type="text" placeholder="Enter title..."
               class="flex-1 border border-gray-300 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500" />
        <button id="btn-add-RESOURCE"
                class="px-4 py-2 rounded bg-blue-600 text-white font-medium hover:bg-blue-700">
          Add
        </button>
      </div>
    </section>

    <!-- SCREEN 2 — id must be screen-SCREEN2 -->
    <section id="screen-SCREEN2">
      <h2 class="text-2xl font-bold mb-4">Screen 2 Title</h2>
      <!-- FILL screen 2 content -->
    </section>

  </main>

  <!-- This line must be last inside <body> — DO NOT MOVE -->
  <script src="main.js"></script>
</body>
</html>"""


def task_description() -> str:
    return (
        "You have been given the `design_contract` from the Contract Architect.\n\n"
        "Fill in the HTML template below to match the design_contract.\n"
        "Replace every FILL_* / SCREEN1 / SCREEN2 / RESOURCE placeholder with real values.\n"
        "Add or remove <section> blocks to match exactly the screens in design_contract.screens "
        "(skip any auth screens).\n\n"
        "Rules:\n"
        "- NO AUTH screens.\n"
        "- Keep the template structure exactly — same <nav>, <main>, <script> order.\n"
        "- Every nav button must have id=\"nav-SCREENNAME\".\n"
        "- Every section must have id=\"screen-SCREENNAME\".\n"
        "- Every interactive element (input, button, list) must have a unique descriptive id.\n"
        "- Use Tailwind classes only — no <style> blocks.\n"
        "- <script src=\"main.js\"></script> must be the last line inside <body>.\n"
        "- No JavaScript anywhere.\n"
        "- Use realistic placeholder text inside elements.\n\n"
        "Output exactly:\n\n"
        "=== FILE: ui/index.html ===\n"
        + _HTML_TEMPLATE
    ).strip()


TASK_EXPECTED_OUTPUT = (
    "Exactly one file: '=== FILE: ui/index.html ===' — filled-in HTML template, no JS."
)
