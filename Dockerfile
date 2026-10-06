FROM python:3.13-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-default-groups --group web --no-install-project
COPY src ./src
RUN uv sync --locked --no-default-groups --group web --no-editable

FROM python:3.13-slim
# uid 1000 owns the host directory mounted at /data
RUN useradd --create-home --uid 1000 app && mkdir /data && chown app /data
COPY --from=build /app/.venv /app/.venv
ARG APP_VERSION=dev
ENV PATH=/app/.venv/bin:$PATH APP_VERSION=$APP_VERSION
USER app
EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz')"
CMD ["wingspan", "--host", "0.0.0.0", "--port", "8000", "--no-browser", "--db", "/data/games.db"]
