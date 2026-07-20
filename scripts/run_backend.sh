#!/bin/bash
# Persistent backend server starter
export PATH="$HOME/.local/bin:$PATH"
export DATABASE_URL="duckdb:///:memory:"
cd /home/z/my-project/dataflow-platform/backend
exec uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1
