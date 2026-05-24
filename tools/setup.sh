#!/bin/bash
# setup.sh - Synthesus 3.0 Automated Setup (Linux/macOS)

echo "--- Synthesus 3.0 Setup ---"

# 1. Check & Install OS Dependencies
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    echo "Detected Linux. Installing system dependencies..."
    sudo apt update && sudo apt install -y python3 python3-venv python3-pip git curl build-essential nodejs npm postgresql-15 postgresql-server-dev-15
    if ! psql -d synthesus_params -c "SELECT 1" >/dev/null 2>&1; then
        echo "Setting up pgvector..."
        git clone https://github.com/pgvector/pgvector.git /tmp/pgvector && cd /tmp/pgvector && make && sudo make install && cd -
        sudo -u postgres psql -c "CREATE USER synthesus WITH PASSWORD 'synthesus';" || true
        sudo -u postgres psql -c "CREATE DATABASE synthesus_params OWNER synthesus;" || true
        sudo -u postgres psql -d synthesus_params -c "CREATE EXTENSION vector;" || true
    fi
elif [[ "$OSTYPE" == "darwin"* ]]; then
    echo "Detected macOS. Installing system dependencies..."
    command -v brew >/dev/null 2>&1 || { echo "Installing Homebrew..."; /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"; }
    brew install python git node postgresql@15 pgvector
    brew services start postgresql@15
    psql postgres -c "CREATE USER synthesus WITH PASSWORD 'synthesus';" || true
    psql postgres -c "CREATE DATABASE synthesus_params OWNER synthesus;" || true
    psql synthesus_params -c "CREATE EXTENSION vector;" || true
fi

# 2. Python Environment
echo "Setting up Python virtual environment..."
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
fi

# 3. Node.js Environment
echo "Installing Node.js dependencies..."
npm install

# 4. Initial Self-Improvement Loop (Warm start)
echo "Running initial self-improvement loop (training organs)..."
npm run self-improve

echo "--- Setup Complete! ---"
echo "To start Synthesus:"
echo "1. Activate venv: source .venv/bin/activate"
echo "2. Start server: uvicorn api.production_server:app --host 0.0.0.0 --port 5000"
