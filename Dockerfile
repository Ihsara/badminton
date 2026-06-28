# Always-on server image (uv-managed, per project rules).
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# git is needed at runtime: every Excel/nickname edit is committed to data/.git.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* \
    && git config --system --add safe.directory '*'

WORKDIR /app
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

# Install deps first (cached layer), then the project.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev

# The upcoming-tournament watcher (docker-compose `upcoming` service) drives a
# headless Chromium via Playwright, so the browser + its system libraries must be
# in the image. `install-deps` pulls the apt packages Chromium needs on
# bookworm-slim; `install chromium` fetches the browser itself. The web `server`
# command does not scrape, but both services share this one image.
RUN uv run playwright install-deps chromium \
    && uv run playwright install chromium

EXPOSE 8000
# data/ and web/ are bind-mounted at runtime (see docker-compose.yml) so commits
# and the regenerated data.json land on the host's private repo.
CMD ["uv", "run", "badminton", "server", "--host", "0.0.0.0", "--port", "8000"]
