# Build context: /Users/Jarod/_heretto  (parent of both hop-core and syndication-service)
# docker compose sets context: ../
FROM python:3.12-slim
WORKDIR /app

# Install hop-core from the sibling directory copied into the build context
COPY hop-core/ /hop-core/
RUN pip install --no-cache-dir /hop-core

# Copy and install the syndication service
COPY syndication-service/ /app/
RUN pip install --no-cache-dir \
    apscheduler \
    "httpx>=0.27.0" \
    "uvicorn[standard]" \
    lxml \
    python-multipart \
    python-dotenv \
    alembic \
    "slowapi>=0.1.9" \
    pyyaml

# Install the package itself (makes `syndication` importable)
RUN pip install --no-cache-dir -e .

RUN mkdir -p /app/data

ENV DATABASE_URL=sqlite:////app/data/syndication.db

# Run migrations then start the server
CMD sh -c "alembic upgrade head && uvicorn syndication.main:app --host 0.0.0.0 --port 8000"
