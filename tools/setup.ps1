# setup.ps1 - Synthesus 3.0 Automated Setup (Windows)

Write-Host "--- Synthesus 3.0 Setup ---" -ForegroundColor Cyan

# 1. Check & Install OS Dependencies (winget)
Write-Host "Checking system dependencies..." -ForegroundColor Cyan
$deps = @("Python.Python.3.12", "Git.Git", "OpenJS.NodeJS.LTS", "Docker.DockerDesktop")
foreach ($dep in $deps) {
    if (!(winget list --id $dep -e)) {
        Write-Host "Installing $dep..."
        winget install -e --id $dep --accept-package-agreements --accept-source-agreements
    }
}

# 2. Database Setup (Docker)
Write-Host "Checking database container..." -ForegroundColor Cyan
if (!(docker ps -a --filter "name=synthesus-db" --format "{{.Names}}")) {
    Write-Host "Starting pgvector database container..."
    docker run -d --name synthesus-db -e POSTGRES_PASSWORD=synthesus -e POSTGRES_DB=synthesus_params -p 5432:5432 pgvector/pgvector:pg16
}

# 2. Python Environment
Write-Host "Setting up Python virtual environment..."
python -m venv .venv
& .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
if (Test-Path "requirements.txt") {
    pip install -r requirements.txt
}

# 3. Node.js Environment
Write-Host "Installing Node.js dependencies..."
npm install

# 4. Initial Self-Improvement Loop (Warm start)
Write-Host "Running initial self-improvement loop (training organs)..."
npm run self-improve

Write-Host "--- Setup Complete! ---" -ForegroundColor Green
Write-Host "To start Synthesus:"
Write-Host "1. Activate venv: .venv\Scripts\Activate.ps1"
Write-Host "2. Start server: uvicorn api.production_server:app --host 0.0.0.0 --port 5000"
