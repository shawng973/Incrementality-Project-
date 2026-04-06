#!/bin/sh
# Starts both the FastAPI server and ARQ worker in the same container.
# Used when Railway's plan limits the number of services per project.

set -e

echo "Starting ARQ worker in background..."
python -m arq app.jobs.analysis_pipeline.WorkerSettings &
WORKER_PID=$!

echo "Starting API server..."
uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" &
API_PID=$!

# If either process exits, kill both and exit with an error
wait -n
kill $WORKER_PID $API_PID 2>/dev/null
exit 1
