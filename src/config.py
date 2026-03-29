import textwrap
from dotenv import load_dotenv
import os

# ---------------------------------------------------------------------------
# Loaded envs
# ---------------------------------------------------------------------------
load_dotenv()
MODEL_CONFIG = os.environ.get("MODEL_CONFIG", "local")
CLAUDE_API_KEY= os.environ.get("CLAUDE_API_KEY", "")
USE_LOCAL_MODEL=(MODEL_CONFIG=="local")

# ---------------------------------------------------------------------------
# Container config
# ---------------------------------------------------------------------------

BACKEND_CONTAINER = "altimate-backend"
BACKEND_IMAGE     = "altimate-backend:latest"
BACKEND_HOST_PORT = 5000

FRONTEND_CONTAINER = "altimate-frontend"
FRONTEND_HOST_PORT = 3000
FRONTEND_IMAGE     = "altimate-frontend:latest"

# ---------------------------------------------------------------------------
# Dockerfiles
# ---------------------------------------------------------------------------

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
