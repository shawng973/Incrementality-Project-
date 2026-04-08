#!/bin/sh
# Starts both the FastAPI server and ARQ worker in the same container.
# Used when Railway's plan limits the number of services per project.

echo "Starting ARQ worker in background..."
python -m arq app.jobs.analysis_pipeline.WorkerSettings &

echo "Starting API server..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
