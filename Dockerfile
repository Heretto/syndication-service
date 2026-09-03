# Build context: parent directory (contains both hop-core/ and syndication-service/)
# docker compose sets context: ../ from within the syndication-service directory
FROM python:3.12-slim
WORKDIR /app

# Install hop-core from the sibling directory copied into the build context
COPY hop-core/ /hop-core/
RUN pip install --no-cache-dir /hop-core

# Copy and install the syndication service
COPY syndication-service/ /app/
RUN pip install --no-cache-dir \
    "apscheduler==3.10.4" \
    "httpx==0.27.0" \
    "uvicorn[standard]==0.29.0" \
    "lxml==5.2.1" \
    "python-multipart==0.0.9" \
    "python-dotenv==1.0.1" \
    "alembic==1.13.3" \
    "slowapi==0.1.9" \
    "pyyaml==6.0.2"

# Install the package itself (makes `syndication` importable)
RUN pip install --no-cache-dir -e .

RUN mkdir -p /app/data

# Run as a non-root user for security
RUN useradd --no-create-home --shell /bin/false appuser \
    && chown -R appuser /app/data
USER appuser

ENV DATABASE_URL=sqlite:////app/data/syndication.db

# Run migrations then start the server
CMD sh -c "alembic upgrade head && uvicorn syndication.main:app --host 0.0.0.0 --port 8000"
