ROLE = "Frontend Developer"

GOAL = (
    "Write main.js — the single JavaScript file that brings index.html to life "
    "by wiring the API, implementing screen navigation, and rendering real data."
)

BACKSTORY = (
    "You are a senior frontend engineer. You write clean vanilla JS with async/await "
    "and the Fetch API. You never touch the HTML — your only output is main.js. "
    "You never use React, Vue, or jQuery."
)

_TEMPLATE = """\
const API_BASE = 'http://localhost:5000';

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
  document.getElementById(nearId)
    .insertAdjacentHTML('afterend',
      '<p class="text-red-500 text-sm mt-1 error-msg">' + msg + '</p>');
  setTimeout(() => document.querySelectorAll('.error-msg')
    .forEach(el => el.remove()), 3000);
}

// ── Navigation ───────────────────────────────────────────────────────────────
// Fill this with every id suffix from <section id="screen-X"> in index.html

const SCREENS = ['REPLACE_WITH_SCREEN_NAMES'];

function show(name) {
  SCREENS.forEach(s => {
    document.getElementById('screen-' + s).classList.toggle('hidden', s !== name);
    const btn = document.getElementById('nav-' + s);
    if (btn) {
      btn.classList.toggle('bg-blue-600',   s === name);
      btn.classList.toggle('text-white',    s === name);
      btn.classList.toggle('bg-gray-200',   s !== name);
      btn.classList.toggle('text-gray-700', s !== name);
    }
  });
}

// ── Render functions (one per screen) ────────────────────────────────────────
// Each function fetches real data and writes HTML into the section element.
// Paginated responses have shape: { items: [...], total, page, page_size }
// — always access .items, never treat the response as an array directly.

async function renderTodos() {
  const data = await api('GET', '/todos');
  const items = data.items ?? data;
  const el = document.getElementById('list-todos');
  el.innerHTML = items.map(t =>
    '<li class="flex justify-between items-center py-2 border-b">'
    + '<span>' + t.title + '</span>'
    + '<button id="btn-delete-' + t.id + '" data-id="' + t.id + '"'
    + ' class="text-red-500 text-sm">Delete</button>'
    + '</li>'
  ).join('');
  // wire delete buttons rendered above
  items.forEach(t => {
    document.getElementById('btn-delete-' + t.id)
      .addEventListener('click', async () => {
        await api('DELETE', '/todos/' + t.id);
        await renderTodos();
      });
  });
}

// ── Event listeners ───────────────────────────────────────────────────────────

function wireEvents() {
  // Add-todo button
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
        await renderTodos();
      } catch (e) { showError('btn-add-todo', e.message); }
      finally { btnAdd.disabled = false; }
    });
  }

  // Enter key on text inputs triggers associated button
  document.querySelectorAll('input[type="text"]').forEach(input => {
    input.addEventListener('keydown', e => {
      if (e.key === 'Enter') {
        const btn = document.getElementById('btn-add-todo');
        if (btn) btn.click();
      }
    });
  });

  // Checkbox toggles
  document.querySelectorAll('input[type="checkbox"]').forEach(chk => {
    chk.addEventListener('change', async () => {
      const id = chk.dataset.id;
      if (!id) return;
      await api('PATCH', '/todos/' + id, { completed: chk.checked });
      await renderTodos();
    });
  });
}

// ── Boot ──────────────────────────────────────────────────────────────────────

(async () => {
  SCREENS.forEach((s, i) => {
    const sec = document.getElementById('screen-' + s);
    if (i !== 0) sec.classList.add('hidden');
    const btn = document.getElementById('nav-' + s);
    if (btn) btn.addEventListener('click', () => show(s));
  });

  wireEvents();
  await renderTodos();
  show(SCREENS[0]);
})();
"""


def task_description(ui_html: str) -> str:
    return (
        "You have been given the following HTML from the UI Designer.\n"
        "Read every id, data-action, section name, and input carefully.\n\n"
        "=== ui/index.html ===\n"
        + ui_html
        + "\n=====================\n\n"
        "You also have:\n"
        "- The `design_contract` — screens and feature lists.\n"
        "- The `data_contract` — exact API paths, methods, and payloads.\n\n"
        "Write `main.js` by filling in the template below.\n"
        "Your response must start with the delimiter line and contain ONLY JavaScript.\n"
        "Do NOT include any text, explanation, or markdown before or after the delimiter.\n\n"
        "=== FILE: frontend/main.js ===\n\n"
        "## Template — replace placeholder comments with real code\n\n"
        "```javascript\n"
        + _TEMPLATE
        + "```\n\n"
        "## Critical rules\n\n"
        "1. SCREENS array: replace 'REPLACE_WITH_SCREEN_NAMES' with the actual id suffixes\n"
        "   from every <section id=\"screen-X\"> found in the HTML above.\n"
        "2. API paths: use EXACTLY the paths from data_contract.endpoints — no /api/ prefix\n"
        "   unless the contract specifies it. E.g. if contract says /todos use /todos.\n"
        "3. Paginated responses return { items, total, page, page_size } — always use .items.\n"
        "4. Write one render function per screen. Call ALL of them in the boot block.\n"
        "5. wireEvents() must attach listeners to every button, input, and checkbox by id.\n"
        "6. After every POST/PATCH/DELETE call the affected render function to refresh the DOM.\n"
        "7. Disable buttons during async calls (btn.disabled = true / false in finally).\n"
        "8. NO AUTH — no redirects, no tokens, every screen is always accessible.\n"
        "9. Your entire response is the JS file content only — no surrounding text."
    ).strip()


TASK_EXPECTED_OUTPUT = (
    "Exactly one file starting with '=== FILE: frontend/main.js ===' — "
    "pure JavaScript only, no prose."
)
