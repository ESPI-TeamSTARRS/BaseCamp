FROM python:3.13-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 UV_PYTHON_DOWNLOADS=never
# git n'est necessaire qu'ici (etage de build) : la dependance `visage-id` (team IA) s'installe depuis
# un commit epingle de son depot public; ni git ni apt ne sont dans l'image finale. Les modeles ONNX
# sont dans le package : aucun telechargement a l'execution.
RUN apt-get update     && apt-get install -y --no-install-recommends git     && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev
COPY app ./app
COPY alembic.ini ./
COPY alembic ./alembic
RUN uv sync --frozen --no-dev

FROM python:3.13-slim AS runtime
RUN groupadd --system app && useradd --system --gid app --home /app app
# pip (et ses bibliotheques embarquees) est inutile a l'execution : l'app tourne depuis /app/.venv.
RUN python -m pip uninstall -y pip
WORKDIR /app
COPY --from=builder --chown=app:app /app /app
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
USER app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --retries=3 \
  CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/health', timeout=2)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
