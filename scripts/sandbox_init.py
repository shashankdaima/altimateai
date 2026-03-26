"""
Flask Docker Sandbox
--------------------
Starts a Flask app in a Docker container with hot-reload enabled.
The workspace directory is mounted as a volume, so any code written
to app.py (e.g. by an agent) is picked up automatically.

Usage:
    python sandbox_init.py          # start sandbox
    python sandbox_init.py stop     # stop & remove container
"""

import os
import sys
import time
import textwrap
import subprocess
import tempfile
import pathlib

try:
    import docker
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "docker", "-q"])
    import docker

try:
    import requests
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "-q"])
    import requests


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CONTAINER_NAME = "flask-sandbox"
HOST_PORT = 5050
CONTAINER_PORT = 5000
IMAGE_TAG = "flask-sandbox:latest"

# Workspace lives next to this script so it survives restarts
WORKSPACE_DIR = pathlib.Path(__file__).parent / "../workspaces/flask_workspace"

# ---------------------------------------------------------------------------
# Initial Flask app written to workspace
# ---------------------------------------------------------------------------

INITIAL_APP_PY = textwrap.dedent("""\
    from flask import Flask, jsonify, request

    app = Flask(__name__)


    # ── built-in routes ────────────────────────────────────────────────────

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok", "service": "flask-sandbox"})


    # ── AGENT ROUTES — append new @app.route blocks below this line ────────


    if __name__ == "__main__":
        app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=True)
""")

DOCKERFILE_CONTENT = textwrap.dedent("""\
    FROM python:3.11-slim
    WORKDIR /app
    RUN pip install --no-cache-dir flask
    ENV FLASK_ENV=development
    ENV PYTHONDONTWRITEBYTECODE=1
    CMD ["python", "-u", "app.py"]
""")

REQUIREMENTS_TXT = "flask>=3.0\n"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def setup_workspace() -> pathlib.Path:
    """Create workspace dir + initial files if they don't exist."""
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

    app_file = WORKSPACE_DIR / "app.py"
    if not app_file.exists():
        app_file.write_text(INITIAL_APP_PY)
        print(f"[sandbox] Created {app_file}")
    else:
        print(f"[sandbox] Reusing existing {app_file}")

    (WORKSPACE_DIR / "Dockerfile").write_text(DOCKERFILE_CONTENT)
    (WORKSPACE_DIR / "requirements.txt").write_text(REQUIREMENTS_TXT)

    return WORKSPACE_DIR


def build_image(client: "docker.DockerClient") -> None:
    print(f"[sandbox] Building image {IMAGE_TAG} ...")
    image, logs = client.images.build(
        path=str(WORKSPACE_DIR),
        tag=IMAGE_TAG,
        rm=True,
    )
    for chunk in logs:
        line = chunk.get("stream", "").rstrip()
        if line:
            print(f"  {line}")
    print(f"[sandbox] Image built: {IMAGE_TAG}")


def stop_existing(client: "docker.DockerClient") -> None:
    try:
        old = client.containers.get(CONTAINER_NAME)
        print(f"[sandbox] Stopping existing container {CONTAINER_NAME} ...")
        old.stop(timeout=5)
        old.remove()
    except docker.errors.NotFound:
        pass


def start_container(client: "docker.DockerClient") -> "docker.models.containers.Container":
    print(f"[sandbox] Starting container {CONTAINER_NAME} on port {HOST_PORT} ...")
    container = client.containers.run(
        IMAGE_TAG,
        name=CONTAINER_NAME,
        ports={f"{CONTAINER_PORT}/tcp": HOST_PORT},
        volumes={
            str(WORKSPACE_DIR): {"bind": "/app", "mode": "rw"}
        },
        detach=True,
        remove=False,
    )
    return container


def wait_for_health(timeout: int = 30) -> bool:
    url = f"http://localhost:{HOST_PORT}/health"
    print(f"[sandbox] Waiting for {url} ...")
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(url, timeout=2)
            if r.status_code == 200:
                print(f"[sandbox] Health check passed: {r.json()}")
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


# ---------------------------------------------------------------------------
# Agent-facing helper
# ---------------------------------------------------------------------------

def add_route(route_code: str) -> None:
    """
    Append a new Flask route to app.py inside the workspace.
    Because the container mounts the workspace with hot-reload, Flask will
    automatically pick up the change — no restart needed.

    Example
    -------
    add_route('''
    @app.route("/hello", methods=["GET"])
    def hello():
        return jsonify({"message": "Hello, World!"})
    ''')
    """
    app_file = WORKSPACE_DIR / "app.py"
    content = app_file.read_text()

    marker = "# ── AGENT ROUTES — append new @app.route blocks below this line ────────"
    if marker not in content:
        raise ValueError("Marker line not found in app.py — was the file modified?")

    insertion = "\n" + textwrap.dedent(route_code).strip() + "\n"
    new_content = content.replace(marker, marker + insertion, 1)
    app_file.write_text(new_content)
    print(f"[sandbox] Route added to {app_file}")


# ---------------------------------------------------------------------------
# Start / Stop
# ---------------------------------------------------------------------------

def start():
    client = docker.from_env()
    setup_workspace()
    build_image(client)
    stop_existing(client)
    container = start_container(client)

    print(f"[sandbox] Container ID: {container.short_id}")

    if wait_for_health():
        print(f"\n[sandbox] Flask sandbox is live at http://localhost:{HOST_PORT}")
        print(f"[sandbox] Health endpoint : http://localhost:{HOST_PORT}/health")
        print(f"[sandbox] Workspace       : {WORKSPACE_DIR}/app.py")
        print(f"[sandbox] Hot-reload is ON — edit app.py and Flask restarts automatically")
    else:
        print("[sandbox] ERROR: health check timed out. Container logs:")
        print(container.logs().decode())
        sys.exit(1)


def stop():
    client = docker.from_env()
    stop_existing(client)
    print(f"[sandbox] Container {CONTAINER_NAME} stopped and removed.")


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "start"
    if cmd == "stop":
        stop()
    elif cmd == "start":
        start()
    else:
        print(f"Unknown command: {cmd}. Use 'start' or 'stop'.")
        sys.exit(1)
