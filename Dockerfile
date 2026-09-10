FROM python:3.12-slim
WORKDIR /app

# Install all dependencies (including pinned hop-core release) before copying source
# so Docker can cache this layer independently of application code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source and install the package itself
COPY . /app/
RUN pip install --no-cache-dir -e .

RUN mkdir -p /app/data

# Run as a non-root user for security
RUN useradd --no-create-home --shell /bin/false appuser \
    && chown -R appuser /app/data
USER appuser

ENV DATABASE_URL=sqlite:////app/data/syndication.db

CMD sh -c "alembic upgrade head && uvicorn syndication.main:app --host 0.0.0.0 --port 8000"
