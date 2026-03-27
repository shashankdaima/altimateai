"""
AltimateAI — Main Entry Point
------------------------------
1. Runs the software agency pipeline on a PRD to generate frontend + backend code.
2. Starts the generated FastAPI backend in Docker on port 5000.
3. Serves the generated frontend HTML via nginx in Docker on port 3000.

Usage:
    uv run python -m src.main <prd_path> [workspace_dir]
    uv run python -m src.main samples/TodoPRD.pdf
    uv run python -m src.main stop
"""

import sys
import time
import textwrap
import pathlib

try:
    import docker
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "docker", "-q"])
    import docker

try:
    import requests as _requests
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "-q"])
    import requests as _requests

from src.agents.agents import run_agency


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BACKEND_CONTAINER  = "altimate-backend"
BACKEND_HOST_PORT  = 5000
BACKEND_IMAGE      = "altimate-backend:latest"

FRONTEND_CONTAINER = "altimate-frontend"
FRONTEND_HOST_PORT = 3000
FRONTEND_IMAGE     = "altimate-frontend:latest"

BACKEND_DOCKERFILE = textwrap.dedent("""\
    FROM python:3.12-slim
    WORKDIR /app
    COPY requirements.txt .
    RUN pip install --no-cache-dir fastapi uvicorn[standard] sqlmodel -r requirements.txt
    ENV PYTHONDONTWRITEBYTECODE=1
    CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
""")

FRONTEND_DOCKERFILE = textwrap.dedent("""\
    FROM nginx:alpine
    COPY nginx.conf /etc/nginx/conf.d/default.conf
    COPY . /usr/share/nginx/html
    EXPOSE 80
""")

FRONTEND_NGINX_CONF = textwrap.dedent("""\
    server {
        listen 80;
        root /usr/share/nginx/html;

        location / {
            try_files $uri $uri.html /index.html =404;
        }
    }
""")


# ---------------------------------------------------------------------------
# Shared Docker helpers
# ---------------------------------------------------------------------------

def _build(client: docker.DockerClient, path: pathlib.Path, tag: str) -> None:
    print(f"[docker] Building {tag} from {path} ...")
    _, logs = client.images.build(path=str(path), tag=tag, rm=True)
    for chunk in logs:
        line = chunk.get("stream", "").rstrip()
        if line:
            print(f"  {line}")


def _stop(client: docker.DockerClient, name: str) -> None:
    try:
        c = client.containers.get(name)
        print(f"[docker] Stopping {name} ...")
        c.stop(timeout=5)
        c.remove()
    except docker.errors.NotFound:
        pass


def _wait(url: str, timeout: int = 30) -> bool:
    print(f"[docker] Waiting for {url} ...")
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = _requests.get(url, timeout=2)
            if r.status_code < 500:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


# ---------------------------------------------------------------------------
# Backend sandbox (FastAPI — host port 5000)
# ---------------------------------------------------------------------------

def start_backend(backend_dir: pathlib.Path) -> None:
    if not backend_dir.exists():
        print(f"[error] Backend directory not found: {backend_dir}")
        sys.exit(1)

    (backend_dir / "Dockerfile").write_text(BACKEND_DOCKERFILE)

    client = docker.from_env()
    _stop(client, BACKEND_CONTAINER)
    _build(client, backend_dir, BACKEND_IMAGE)

    container = client.containers.run(
        BACKEND_IMAGE,
        name=BACKEND_CONTAINER,
        ports={"8000/tcp": BACKEND_HOST_PORT},
        volumes={str(backend_dir.resolve()): {"bind": "/app", "mode": "rw"}},
        detach=True,
        remove=False,
    )
    print(f"[docker] Backend container: {container.short_id}")

    url = f"http://localhost:{BACKEND_HOST_PORT}/docs"
    if _wait(url):
        print(f"[backend] Live at http://localhost:{BACKEND_HOST_PORT}")
        print(f"[backend] Swagger  : {url}")
        print(f"[backend] Hot-reload ON — edit {backend_dir}/main.py")
    else:
        print("[error] Backend health check timed out. Logs:")
        print(container.logs().decode())
        sys.exit(1)


# ---------------------------------------------------------------------------
# Frontend sandbox (nginx — host port 3000)
# ---------------------------------------------------------------------------

def start_frontend(frontend_dir: pathlib.Path) -> None:
    if not frontend_dir.exists():
        print(f"[error] Frontend directory not found: {frontend_dir}")
        sys.exit(1)

    (frontend_dir / "Dockerfile").write_text(FRONTEND_DOCKERFILE)

    client = docker.from_env()
    _stop(client, FRONTEND_CONTAINER)
    _build(client, frontend_dir, FRONTEND_IMAGE)

    container = client.containers.run(
        FRONTEND_IMAGE,
        name=FRONTEND_CONTAINER,
        ports={"80/tcp": FRONTEND_HOST_PORT},
        detach=True,
        remove=False,
    )
    print(f"[docker] Frontend container: {container.short_id}")

    url = f"http://localhost:{FRONTEND_HOST_PORT}"
    if _wait(url):
        print(f"[frontend] Live at {url}")
    else:
        print("[error] Frontend health check timed out. Logs:")
        print(container.logs().decode())
        sys.exit(1)


# ---------------------------------------------------------------------------
# Stop both
# ---------------------------------------------------------------------------

def stop_all() -> None:
    client = docker.from_env()
    _stop(client, BACKEND_CONTAINER)
    _stop(client, FRONTEND_CONTAINER)
    print("[docker] All containers stopped.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m src.main <prd_path> [workspace_dir]")
        print("       python -m src.main stop")
        sys.exit(1)

    if sys.argv[1] == "stop":
        stop_all()
        sys.exit(0)

    prd_path  = sys.argv[1]
    workspace = sys.argv[2] if len(sys.argv) > 2 else "workspaces/output"

    # Step 1 — generate all code via the agency
    print("\n=== Step 1: Running software agency pipeline ===\n")
    run_agency(prd_path, workspace)

    ws = pathlib.Path(workspace)

    # Step 2 — start backend
    print("\n=== Step 2: Starting FastAPI backend (port 5000) ===\n")
    start_backend(ws / "backend")

    # Step 3 — start frontend
    print("\n=== Step 3: Starting frontend via nginx (port 3000) ===\n")
    start_frontend(ws / "frontend")

    print("\n=== All systems go ===")
    print(f"  Frontend : http://localhost:{FRONTEND_HOST_PORT}")
    print(f"  Backend  : http://localhost:{BACKEND_HOST_PORT}/docs")
