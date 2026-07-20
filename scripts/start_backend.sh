#!/bin/bash
export PATH="$HOME/.local/bin:$PATH"
cd /home/z/my-project/dataflow-platform/backend
uvicorn main:app --host 0.0.0.0 --port 8000
