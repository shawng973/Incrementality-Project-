# Multi-stage build for the Incremental Tool backend.
# Stage 1 installs WeasyPrint's native dependencies (pango, gobject, cairo)
# which are required for PDF generation.

FROM python:3.11-slim AS base

# System packages needed by WeasyPrint (pango + cairo stack)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ".[dev]" 2>/dev/null || pip install --no-cache-dir -e .

# Copy source
COPY . .

# API server (default command — Railway overrides this per-service via railway.toml)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
