ROLE = "Frontend Developer"

GOAL = "Fill in the marked zones of the main.js template to make every screen functional."

BACKSTORY = (
    "You are a senior frontend engineer. You receive a JS file with clearly marked fill zones "
    "and write code only inside those zones. You never touch anything outside a fill zone."
)

# ---------------------------------------------------------------------------
# JS skeleton — agent writes code ONLY inside // @@FILL ... // @@END_FILL zones.
# Every other line is fixed and must be reproduced verbatim.
# ---------------------------------------------------------------------------
_JS_TEMPLATE = """\
// ── CONFIG ────────────────────────────────────────────────────────────────
const API_BASE = 'http://localhost:5000';

// ── HELPERS ───────────────────────────────────────────────────────────────
async function api(method, path, body) {
  const opts = { method, headers: {} };
  if (body) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(API_BASE + path, opts);
  if (!res.ok) throw new Error(await res.text());
  return res.status === 204 ? null : res.json();
}

function showError(nearId, msg) {
  const el = document.getElementById(nearId);
  if (!el) return;
  el.insertAdjacentHTML('afterend',
    '<p class="text-red-500 text-sm mt-1 error-msg">' + msg + '</p>');
  setTimeout(() => document.querySelectorAll('.error-msg')
    .forEach(e => e.remove()), 3000);
}

// ── SCREENS ───────────────────────────────────────────────────────────────
// @@FILL_SCREENS — replace ONLY the array values; keep the rest exactly as-is.
// Each value is the id suffix from <section id="screen-X"> — e.g. 'dashboard', NOT 'screen-dashboard'.
const SCREENS = ['PLACEHOLDER_1', 'PLACEHOLDER_2'];
// @@END_FILL_SCREENS

function show(name) {
  SCREENS.forEach(s => {
    const sec = document.getElementById('screen-' + s);
    if (sec) sec.classList.toggle('hidden', s !== name);
    const btn = document.getElementById('nav-' + s);
    if (btn) {
      btn.classList.toggle('bg-blue-600', s === name);
      btn.classList.toggle('text-white',  s === name);
      btn.classList.toggle('bg-gray-200', s !== name);
      btn.classList.toggle('text-gray-700', s !== name);
    }
  });
}

// ── RENDER FUNCTIONS ──────────────────────────────────────────────────────
// @@FILL_RENDER_FUNCTIONS
// Write one async function per screen here, at the TOP LEVEL (not inside any other function).
// Rules:
//   • Fetch from a LIST endpoint — do NOT fetch a single item by id inside a render function.
//   • Path = exact path from data_contract (no /api/ prefix, no extra segments).
//   • Paginated responses: use data.items; plain arrays: use data directly.
//   • After setting innerHTML, re-wire any buttons created inside the new HTML.
//   • Use t.id (the item's numeric id) in DELETE/PATCH paths.
//   • Write ONLY functions for screens that exist in the HTML above.
//
// Example:
//   async function renderDashboard() {
//     const data = await api('GET', '/todos');
//     const items = data.items ?? data;
//     document.getElementById('list-todos').innerHTML = items.map(t =>
//       '<li>' + t.title
//       + ' <button id="btn-del-' + t.id + '">Delete</button></li>'
//     ).join('');
//     items.forEach(t => {
//       document.getElementById('btn-del-' + t.id)
//         .addEventListener('click', async () => {
//           await api('DELETE', '/todos/' + t.id);
//           await renderDashboard();
//         });
//     });
//   }
// @@END_FILL_RENDER_FUNCTIONS

// ── EVENT WIRING ──────────────────────────────────────────────────────────
// @@FILL_WIRE_EVENTS
// Write the complete wireEvents function here, at the TOP LEVEL.
// Rules:
//   • Wire every static button/input/checkbox from the HTML by its exact id.
//   • Each element id must appear at most ONCE — no duplicate listeners.
//   • After POST/PATCH/DELETE, call the affected render function.
//   • Do NOT wire buttons that are created dynamically inside innerHTML —
//     those are wired inside their render function.
//
// Example:
//   function wireEvents() {
//     const btnAdd = document.getElementById('btn-add-todo');
//     if (btnAdd) btnAdd.addEventListener('click', async () => {
//       const titleEl = document.getElementById('input-todo-title');
//       const title = titleEl.value.trim();
//       if (!title) return;
//       btnAdd.disabled = true;
//       try {
//         await api('POST', '/todos', { title });
//         titleEl.value = '';
//         await renderDashboard();
//       } catch(e) { showError('btn-add-todo', e.message); }
//       finally { btnAdd.disabled = false; }
//     });
//   }
// @@END_FILL_WIRE_EVENTS

// ── BOOT ──────────────────────────────────────────────────────────────────
(async () => {
  SCREENS.forEach((s, i) => {
    const sec = document.getElementById('screen-' + s);
    if (sec && i !== 0) sec.classList.add('hidden');
    const btn = document.getElementById('nav-' + s);
    if (btn) btn.addEventListener('click', () => show(s));
  });

  wireEvents();

  // @@FILL_BOOT_RENDERS — add one await renderX(); line per screen, nothing else.
  // @@END_FILL_BOOT_RENDERS

  show(SCREENS[0]);
})();
"""


def task_description(ui_html: str) -> str:
    return (
        "You are given the HTML file from the UI Designer and the data_contract.\n"
        "Your job: fill in ONLY the four marked zones in the JS template below.\n\n"
        "=== ui/index.html ===\n"
        + ui_html
        + "\n=====================\n\n"
        "=== INSTRUCTIONS ===\n\n"
        "Zone 1 — @@FILL_SCREENS\n"
        "  Replace 'PLACEHOLDER_1', 'PLACEHOLDER_2', … with the id suffix of every\n"
        "  <section id=\"screen-X\"> found in the HTML. Suffix only — no 'screen-' prefix.\n"
        "  Count the screens first, then adjust the array length to match.\n\n"
        "Zone 2 — @@FILL_RENDER_FUNCTIONS\n"
        "  Write one async function per screen. Each calls a LIST endpoint from\n"
        "  data_contract (e.g. GET /todos). No /api/ prefix. No fetching by id.\n"
        "  Only write functions for screens that actually exist in the HTML.\n\n"
        "Zone 3 — @@FILL_WIRE_EVENTS\n"
        "  Write the wireEvents() function. Wire every static button/input from the\n"
        "  HTML by its exact id. One listener per id — no duplicates.\n\n"
        "Zone 4 — @@FILL_BOOT_RENDERS\n"
        "  Add one 'await renderX();' line per screen — nothing else.\n\n"
        "=== HARD RULES (violations cause a re-run) ===\n"
        "  • Do NOT write any code outside the four fill zones.\n"
        "  • Do NOT define functions or declare variables inside the boot IIFE.\n"
        "  • Do NOT redeclare const SCREENS, API_BASE, api, showError, or show.\n"
        "  • Do NOT add /api/ to any path — use EXACTLY the path from data_contract.\n"
        "  • Do NOT invent screens that are not in the HTML.\n"
        "  • Do NOT leave any @@FILL or @@END_FILL marker in your output.\n"
        "  • Do NOT leave the PLACEHOLDER_ strings in the SCREENS array.\n"
        "  • Every statement must end with a semicolon or closing brace — no syntax errors.\n\n"
        "=== OUTPUT FORMAT ===\n"
        "Output exactly one block:\n\n"
        "=== FILE: frontend/main.js ===\n"
        "<completed JS>\n\n"
        "No prose, no explanation, no markdown fences around the file.\n\n"
        "=== TEMPLATE TO COMPLETE ===\n\n"
        + _JS_TEMPLATE
    ).strip()


TASK_EXPECTED_OUTPUT = (
    "=== FILE: frontend/main.js === followed by the completed JavaScript. No prose."
)
