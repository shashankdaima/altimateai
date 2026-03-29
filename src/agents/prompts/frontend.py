ROLE = "Frontend Developer"

GOAL = "Fill in the main.js template to make every screen fully functional."

BACKSTORY = (
    "You are a senior frontend engineer. You receive a JS template with /* FILL */ markers "
    "and fill in only those sections. You never change the fixed sections."
)

# This is the complete file skeleton. The agent fills in the /* FILL */ sections only.
_JS_TEMPLATE = """\
// ── CONFIG (DO NOT CHANGE) ────────────────────────────────────────────────
const API_BASE = 'http://localhost:5000';

// ── HELPERS (DO NOT CHANGE) ───────────────────────────────────────────────
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

// ── NAVIGATION (DO NOT CHANGE) ────────────────────────────────────────────
/* FILL: replace with the id suffixes of every <section id="screen-X"> in index.html.
   If the HTML has <section id="screen-dashboard"> and <section id="screen-todos">,
   then SCREENS = ['dashboard', 'todos']  ← suffix only, NOT 'screen-dashboard'. */
const SCREENS = ['FILL_SCREEN_1', 'FILL_SCREEN_2'];

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
/* FILL: write one async render function per screen.
   Rules:
   - Each render function fetches from a LIST endpoint (GET /resource) — never by dynamic id.
   - Use the EXACT path from data_contract.endpoints. Never add /api/ prefix.
   - Paginated responses: { items, total, page, page_size } — use .items.
   - After setting innerHTML, re-wire any buttons inside the new HTML.
   - Use the item's numeric id (t.id) in API paths — NEVER use a SCREENS value as an id.
   - If two screens show the same resource with different filters, add a filter param
     (e.g., renderTodos(filter='pending')) rather than fetching by id.

   Example:

   async function renderDashboard() {
     const data = await api('GET', '/todos');
     const items = data.items ?? data;
     document.getElementById('list-todos').innerHTML = items.map(t =>
       '<li class="flex justify-between items-center py-2 border-b">'
       + '<span>' + t.title + '</span>'
       + '<button id="btn-delete-' + t.id + '" class="text-red-500 text-sm px-2">Delete</button>'
       + '</li>'
     ).join('');
     items.forEach(t => {
       document.getElementById('btn-delete-' + t.id)
         .addEventListener('click', async () => {
           try {
             await api('DELETE', '/todos/' + t.id);   // t.id is a number, not a screen name
             await renderDashboard();
           } catch(e) { showError('btn-delete-' + t.id, e.message); }
         });
     });
   }
*/

// ── EVENT WIRING ──────────────────────────────────────────────────────────
/* FILL: attach event listeners to every button/input/checkbox by id.
   Called once at boot — use document.getElementById, not querySelector.

   Example:

   function wireEvents() {
     const btnAdd = document.getElementById('btn-add-todo');
     if (btnAdd) {
       btnAdd.addEventListener('click', async () => {
         const titleEl = document.getElementById('input-todo-title');
         const title = titleEl.value.trim();
         if (!title) return;
         btnAdd.disabled = true;
         try {
           await api('POST', '/todos', { title });
           titleEl.value = '';
           await renderDashboard();
         } catch(e) { showError('btn-add-todo', e.message); }
         finally { btnAdd.disabled = false; }
       });
     }

     // Enter key submits
     document.querySelectorAll('input[type="text"]').forEach(inp => {
       inp.addEventListener('keydown', e => {
         if (e.key === 'Enter') {
           const btn = document.getElementById('btn-add-todo');
           if (btn) btn.click();
         }
       });
     });
   }
*/

// ── BOOT (DO NOT CHANGE THIS BLOCK) ──────────────────────────────────────
(async () => {
  // hide all screens except the first
  SCREENS.forEach((s, i) => {
    const sec = document.getElementById('screen-' + s);
    if (sec && i !== 0) sec.classList.add('hidden');
    const btn = document.getElementById('nav-' + s);
    if (btn) btn.addEventListener('click', () => show(s));
  });

  // wire all events
  wireEvents();

  /* FILL: call every render function here, e.g.:
     await renderDashboard();
     await renderTodos();
  */

  show(SCREENS[0]);
})();
"""


def task_description(ui_html: str) -> str:
    return (
        "You have been given the HTML from the UI Designer.\n"
        "Read every id, section name, and data-action carefully.\n\n"
        "=== ui/index.html ===\n"
        + ui_html
        + "\n=====================\n\n"
        "You also have the `data_contract` with the exact API endpoints.\n\n"
        "Fill in the /* FILL */ sections of the JS template below.\n"
        "DO NOT change anything marked DO NOT CHANGE.\n"
        "Your response must be exactly:\n\n"
        "=== FILE: frontend/main.js ===\n"
        "<the completed JS — no other text>\n\n"
        "## Template to complete\n\n"
        + _JS_TEMPLATE
        + "\n\n"
        "## What to fill in\n\n"
        "1. SCREENS array — replace 'FILL_SCREEN_1', 'FILL_SCREEN_2' with the\n"
        "   id suffix of every <section id=\"screen-X\"> in the HTML above.\n"
        "   Rule: suffix ONLY — no 'screen-' prefix.\n"
        "   Example: <section id=\"screen-dashboard\"> → SCREENS entry is 'dashboard'.\n\n"
        "2. Render functions — one per screen.\n"
        "   - Call a LIST endpoint (GET /resource) — never fetch by dynamic id in a render function.\n"
        "   - Path must match data_contract exactly (no /api/ prefix, no extra segments).\n"
        "   - Use data.items (paginated) or data directly (array).\n"
        "   - Re-wire dynamically created buttons inside the forEach after innerHTML.\n"
        "   - Use t.id (number from the item) in DELETE/PATCH paths — never use a SCREENS value.\n\n"
        "3. wireEvents() — attach ONE listener per element id from the HTML.\n"
        "   - Do not attach the same listener twice.\n"
        "   - After POST/PATCH/DELETE call the affected render function.\n\n"
        "4. Boot render calls — add one await renderX() per screen.\n\n"
        "NEVER:\n"
        "- Add '/api/' prefix — paths are exactly as in data_contract.\n"
        "- Use SCREENS[i] or a screen name as an API path segment.\n"
        "- Wire the same element id more than once.\n"
        "- Redefine api(), showError(), show(), or the boot IIFE.\n\n"
        "Output ONLY the completed JS inside the delimiter. No prose."
    ).strip()


TASK_EXPECTED_OUTPUT = (
    "=== FILE: frontend/main.js === followed by the completed JavaScript. No prose."
)
