# AltimateAI — Software Agency

An agentic pipeline that turns a Product Requirements Document (PRD) into a
working full-stack application using a crew of specialised AI agents.

## Architecture

```
PRD (PDF or text)
    │
    ▼
┌─────────────────┐
│  Manager Agent  │  Reads PRD → produces structured Markdown project plan
└────────┬────────┘
         │ plan
         ▼
┌──────────────────────┐
│  Contract Architect  │  Produces design_contract.json + data_contract.json
└──────────┬───────────┘
           │
     ┌─────┴──────┐
     ▼            ▼
┌──────────┐  ┌─────────────────┐
│ UI Design│  │  Backend Agent  │  FastAPI + SQLModel (reads data_contract)
│  Agent   │  └─────────────────┘
└────┬─────┘
     │ HTML files
     ▼
┌───────────────────┐
│ Frontend Developer│  Adds JS/fetch logic (reads design_contract + HTML + data_contract)
└───────────────────┘
```

### Contracts

**`design_contract.json`** — drives UI/frontend work:
- `theme` — hex colour palette (primary, secondary, background, surface, text, accent, danger, success)
- `typography` — font family + base size
- `screens[]` — route, description, features list

**`data_contract.json`** — drives backend/frontend API work:
- `models[]` — Pydantic/SQLModel field definitions
- `endpoints[]` — method, path, request/response shapes, pagination flag

## Project Structure

```
altimateai/
├── src/
│   ├── main.py                    # Legacy standalone PDF summariser
│   └── agents/
│       ├── agents.py              # Crew assembly + run_agency() entry point
│       └── prompts/
│           ├── manager.py
│           ├── contract.py
│           ├── ui_designer.py
│           ├── frontend.py
│           └── backend.py
│   └── tools/
│       ├── pdf_reader.py          # extract_text, extract_pages, extract_metadata, extract_images
│       ├── file_writer.py         # write_text, write_json, write_csv, write_bytes, append_text
│       └── screenshot.py          # screenshot_url, screenshot_element, screenshot_html, screenshot_pdf
├── samples/                       # Sample PRD files
├── workspaces/                    # Generated output (gitignored)
│   └── output/
│       ├── plan.md
│       ├── contracts/
│       │   ├── design_contract.json
│       │   └── data_contract.json
│       ├── ui/                    # Raw HTML designs from UI Designer
│       ├── frontend/              # Interactive HTML + JS from Frontend Dev
│       └── backend/               # FastAPI application from Backend Dev
├── pyproject.toml
└── CLAUDE.md
```

## Running the Agency

```bash
# Run the full pipeline on a PDF PRD
uv run python -m src.agents.agents samples/MyProduct.pdf

# Specify a custom output directory
uv run python -m src.agents.agents samples/MyProduct.pdf workspaces/my_project
```

## Environment

Create a `.env` file in the project root:

```
ANTHROPIC_API_KEY=sk-ant-...
```

## Dependencies

- `crewai[anthropic]` — agent orchestration
- `pymupdf` — PDF text extraction
- `playwright` — headless browser screenshots

Install Playwright browsers once:
```bash
uv run playwright install chromium
```

## Agent Responsibilities

| Agent | Input | Output |
|---|---|---|
| Manager | Raw PRD text | `plan.md` — Markdown task breakdown |
| Contract Architect | plan.md | `design_contract.json` + `data_contract.json` |
| UI Designer | design_contract | `ui/*.html` — static HTML mockups |
| Frontend Developer | design_contract + HTML + data_contract | `frontend/*.html` — interactive HTML + JS |
| Backend Developer | data_contract | `backend/` — full FastAPI app |
