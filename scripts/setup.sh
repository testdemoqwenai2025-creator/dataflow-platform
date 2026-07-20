#!/bin/bash
# DataFlow Platform — Development Setup Script
# Usage: bash scripts/setup.sh

set -e

echo "🚀 Setting up DataFlow Platform..."
echo ""

# ── Check Prerequisites ──
check_command() {
    if ! command -v "$1" &> /dev/null; then
        echo "❌ $1 is not installed. Please install it first."
        echo "   $2"
        exit 1
    fi
    echo "✅ $1 found"
}

check_command python3 "https://www.python.org/downloads/"
check_command node "https://nodejs.org/"
check_command npm "Comes with Node.js"
check_command git "https://git-scm.com/"

# ── Backend Setup ──
echo ""
echo "📦 Setting up backend..."
cd backend

if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "✅ Created Python virtual environment"
fi

source venv/bin/activate
pip install -r requirements.txt --quiet
echo "✅ Installed Python dependencies"

# Create data directory for DuckDB
mkdir -p data
echo "✅ Created data directory"

cd ..

# ── Frontend Setup ──
echo ""
echo "📦 Setting up frontend..."
cd frontend

npm install --silent
echo "✅ Installed Node.js dependencies"

cd ..

# ── Environment Files ──
echo ""
echo "🔧 Setting up environment files..."

if [ ! -f "backend/.env" ]; then
    cat > backend/.env << 'EOF'
# Database
DATABASE_URL=duckdb:///data/analytics.duckdb
POSTGRES_URL=postgresql://dataflow:dataflow@localhost:5432/dataflow

# Auth
SECRET_KEY=dev-secret-key-change-in-production
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# Redis
REDIS_URL=redis://localhost:6379/0

# CORS
CORS_ORIGINS=http://localhost:3000,http://localhost:8000

# Environment
ENVIRONMENT=development
EOF
    echo "✅ Created backend/.env"
fi

if [ ! -f "frontend/.env.local" ]; then
    cat > frontend/.env.local << 'EOF'
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000/ws
EOF
    echo "✅ Created frontend/.env.local"
fi

# ── Done ──
echo ""
echo "🎉 Setup complete! Start developing with:"
echo ""
echo "   # Terminal 1 — Backend"
echo "   cd backend && source venv/bin/activate"
echo "   uvicorn main:app --reload --port 8000"
echo ""
echo "   # Terminal 2 — Frontend"
echo "   cd frontend && npm run dev"
echo ""
echo "   Frontend: http://localhost:3000"
echo "   Backend:  http://localhost:8000"
echo "   API Docs: http://localhost:8000/docs"
