# Synthesus 3.0 Installation Guide

Welcome to Synthesus! This guide will walk you through setting up Synthesus on your computer step by step. It's designed to be easy for everyone, even if you're not a tech expert. We'll get you from zero to running your own AI assistant in under 30 minutes.

## What is Synthesus?

Synthesus 3.0 is a next-generation synthetic reasoning engine. It uses a core symbolic world-model combined with specialized ML "organs" to provide high-autonomy decision making without large language models.

### Key V3 Features
- **Autonomy Engine**: Advisor, Co-pilot, and Autopilot modes.
- **Knowledge Cloud**: Shared world lore with semantic search (FAISS) and "lore evolution" (witnessed events).
- **Universal Substrate (V2)**: Hybrid parameter layer with cloud (Postgres) and local (Smart FS) persistence.
- **Social Fabric**: Multi-NPC relationships, faction dynamics, and rumor propagation.
- **Self-Improvement**: Automated learning from session traces with `npm run self-improve`.
- **C++ Kernel Bridge**: High-performance reasoning bridge (Native, IPC, and Fallback modes).
- **V3 Core**: Shared synthetic brain across GM, SysOps, and Chat domains.

---

## Prerequisites (What You Need)

Before starting, make sure your computer has:
- **Python 3.10 or newer**
- **Node.js 18+ and npm** (Required for the V3 reasoning engine and self-improvement loop)
- **PostgreSQL 15+** (Required for the V2 Parameter Cloud and vector storage)
- **pgvector extension** (Must be enabled in your Postgres database)
- **C++ Compiler** (Optional: GCC/Clang on Linux/macOS, MSVC on Windows for the native kernel)
- **A web browser** (Chrome, Firefox, or Edge)

## One-Line Full Setup (No Dependencies Installed)

If you are starting on a fresh machine with no software installed, use these commands to handle system-level dependencies, cloning, and initial configuration in one go.

### Linux (Debian/Ubuntu)
```bash
sudo apt update && \
sudo apt install -y python3 python3-venv python3-pip git curl build-essential nodejs npm postgresql-15 postgresql-server-dev-15 && \
git clone https://github.com/pgvector/pgvector.git && cd pgvector && make && sudo make install && cd .. && \
sudo -u postgres psql -c "CREATE USER synthesus WITH PASSWORD 'synthesus';" && \
sudo -u postgres psql -c "CREATE DATABASE synthesus_params OWNER synthesus;" && \
sudo -u postgres psql -d synthesus_params -c "CREATE EXTENSION vector;" && \
cd ~ && git clone https://github.com/Str8biddness/synthesus.git synthesus3.0 && \
cd synthesus3.0 && python3 -m venv venv && source venv/bin/activate && \
pip install -r requirements.txt && npm install && npm run self-improve && \
psql -d synthesus_params -f migrations/001_create_parameter_store.sql && \
uvicorn api.production_server:app --host 0.0.0.0 --port 5000
```

### macOS (Homebrew)
```bash
brew install python git node postgresql@15 pgvector && \
brew services start postgresql@15 && \
psql postgres -c "CREATE USER synthesus WITH PASSWORD 'synthesus';" && \
psql postgres -c "CREATE DATABASE synthesus_params OWNER synthesus;" && \
psql synthesus_params -c "CREATE EXTENSION vector;" && \
cd ~ && git clone https://github.com/Str8biddness/synthesus.git synthesus3.0 && \
cd synthesus3.0 && python3 -m venv venv && source venv/bin/activate && \
pip install -r requirements.txt && npm install && npm run self-improve && \
psql synthesus_params -f migrations/001_create_parameter_store.sql && \
uvicorn api.production_server:app --host 0.0.0.0 --port 5000
```

### Windows (PowerShell, using winget + Docker)
```powershell
winget install -e --id Python.Python.3.12 ; `
winget install -e --id Git.Git ; `
winget install -e --id OpenJS.NodeJS.LTS ; `
winget install -e --id Docker.DockerDesktop ; `
cd $HOME ; `
git clone https://github.com/Str8biddness/synthesus.git synthesus3.0 ; `
cd synthesus3.0 ; `
docker run -d --name synthesus-db -e POSTGRES_PASSWORD=synthesus -e POSTGRES_DB=synthesus_params -p 5432:5432 pgvector/pgvector:pg16 ; `
py -3 -m venv venv ; `
.\venv\Scripts\Activate.ps1 ; `
pip install -r requirements.txt ; `
npm install ; `
npm run self-improve ; `
uvicorn api.production_server:app --host 0.0.0.0 --port 5000
```

> [!NOTE]
> - You may need to confirm package installations manually (especially on macOS/Windows prompt).
> - If any specific step fails, please fall back to the **Detailed Setup** section below.

---

## One-Liner Installation (Recommended)


Run the command for your operating system from the repository root to automate the entire setup:

**Linux / macOS:**
```bash
chmod +x setup.sh && ./setup.sh
```

**Windows (PowerShell):**
```powershell
Set-ExecutionPolicy Bypass -Scope Process -Force; ./setup.ps1
```

---

## Universal Setup (Docker - Recommended)

If you have Docker installed, you can run the entire Synthesus stack (including the pgvector database) with a single command:

```bash
docker compose up -d
```
*(Requires a `docker-compose.yml` file in the root directory)*

---

## Quick Start (Manual Setup)


### Step 1: Download the Code
1. Open a web browser.
2. Go to https://github.com/Str8biddness/synthesus
3. Click the green "Code" button.
4. Click "Download ZIP".
5. Unzip the file to a folder on your computer (e.g., your Desktop).
6. Open a terminal (Command Prompt on Windows, Terminal on macOS/Linux).
7. Navigate to the folder: `cd Desktop/synthesus` (adjust if you put it elsewhere).

### Step 2: Set Up Environments
1. **Python**: Create and activate a virtual environment, then `pip install -r requirements.txt`.
2. **Node.js**: Run `npm install` to install the V3 reasoning and training dependencies.

### Step 3: Run the Self-Improvement Loop
Synthesus 3.0 learns from every interaction. To train the initial organs:
```bash
npm run self-improve
```

### Step 4: Start the Server
1. In the terminal: `uvicorn api.production_server:app --host 0.0.0.0 --port 5000`
2. Open your web browser and go to http://localhost:5000

That's it! You're now running Synthesus. Try typing "why is my computer slow?" in SysOps mode.

---

## Core Components Setup (New in Phase 12+)

### Knowledge Cloud & Lore Evolution
The Knowledge Cloud is a shared semantic repository that all NPCs can query. It evolves as NPCs "witness" events and propagate rumors.
- **Storage**: Data is stored in `data/knowledge_cloud/`.
- **Search**: Uses FAISS for sub-millisecond semantic similarity.
- **Evolution**: Historical changes are tracked in `evolution.json`.

### Universal Parameter Substrate (V2)
Synthesus 3.0 uses a "Universal Substrate" to unify access to character genomes and world parameters.
- **Local (Smart FS)**: Fallback storage in `characters/` and `data/`.
- **Cloud (Postgres)**: High-scale storage for billions of parameters.
- **Database Setup**:
    1. Install PostgreSQL and the `pgvector` extension.
    2. Create a database: `CREATE DATABASE synthesus_params;`
    3. Run the schema: `psql -d synthesus_params -f migrations/001_create_parameter_store.sql`
    4. Set your environment variable: `DATABASE_URL=postgresql://user:pass@localhost:5432/synthesus_params`

### Multi-NPC Social Fabric
NPCs now have persistent relationships and faction alignments.
- **Gossip**: Rumors spread through NPC-to-NPC messaging with "truth decay."
- **Relationships**: Tracked per-player and per-NPC in `cognitive/social_fabric.py`.

---

## Detailed Setup (If Quick Start Doesn't Work)

### Step 1: Install Python
1. Go to https://www.python.org/downloads/
2. Download Python 3.10 or later.
3. Run the installer.
4. Check it's installed: Open terminal and type `python --version`. It should show something like "Python 3.11.0".

### Step 2: Clone the Repository
1. Install Git if you don't have it: https://git-scm.com/downloads
2. Open terminal.
3. Run: `git clone https://github.com/Str8biddness/synthesus.git`
4. Go into the folder: `cd synthesus`

### Step 3: Set Up Virtual Environment
1. Create environment: `python -m venv venv`
2. Activate it:
   - Windows: `venv\Scripts\activate`
   - macOS/Linux: `source venv/bin/activate`
3. Your terminal prompt should change (e.g., show `(venv)`).

### Step 4: Install Dependencies
1. Run: `pip install -r requirements.txt`
2. This installs all needed libraries. It might take a few minutes.

### Step 5: Run the Server
1. Start the server: `uvicorn api.production_server:app --host 0.0.0.0 --port 5000`
2. If port 5000 is busy, try `--port 8000` instead.
3. Server starts at http://localhost:5000

---

## Using the Web Interface

### Basic Usage
1. Open http://localhost:5000 in your browser.
2. You'll see a simple page with a text box.
3. Type your question (e.g., "Why is my system lagging?").
4. Click "Send".
5. The AI responds with an answer.

### Switching Domains
1. Above the text box, there's a dropdown labeled "Mode:".
2. Choose:
   - **SysOps**: For computer problems (default).
   - **GM**: For gaming or story advice.
   - **Assistant**: General help.
   - **Legal**: Legal questions (coming soon).
3. Ask questions relevant to that mode.

### Viewing Reasoning Details
1. After getting an answer, click "Show reasoning details".
2. See:
   - **Role/Tone**: How the AI is responding (e.g., investigator/confident).
   - **Engines Used**: Which parts of the AI brain were used.
   - **Key Explanations**: Top reasons or causes.
   - **Actions Taken**: What the AI did (e.g., checked rules).

### Providing Feedback
1. After each answer, there are thumbs up 👍 and thumbs down 👎 buttons.
2. Click 👍 if the answer was helpful.
3. Click 👎 if not.
4. This helps the AI learn and improve over time.

### SysOps Mode Special Features
- Diagnoses issues like high CPU, memory problems, or disk I/O.
- Shows a warning: It only recommends actions, never changes your system without permission.
- Use for questions like "My computer is slow", "High CPU usage", or "Disk full".

### Trainer Status
- At the bottom, see "Last Batch" (when AI last learned), "Learned Rules" (how many rules it knows), and "Sandbox Mode" (safe or not).

---

## How It Works (Simplified)

Synthesus has a "dual brain" like humans:
- **Left Brain**: Fast pattern matching for quick answers.
- **Right Brain**: 9 thinking modules for deeper understanding.
- **ML Swarm**: 12 tiny AI models for detecting intent, emotions, etc.
- **SysOps Domain**: Special rules for computer issues, like high CPU causes slowdowns.

No internet needed after setup—runs on your computer!

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "Python not found" | Install Python from python.org |
| "Module not installed" | Run `pip install -r requirements.txt` again |
| "FAISS not found" | Ensure `faiss-cpu` is in requirements and installed |
| "Postgres Connection Refused" | Check `DATABASE_URL` and ensure Postgres is running |
| "pgvector missing" | Enable extension: `CREATE EXTENSION vector;` in your DB |
| Server won't start | Check port: try `uvicorn ... --port 8000` |
| Web page blank | Make sure server is running and go to http://localhost:5000 |
| Slow responses | Normal for first query—AI is learning |
| Can't switch domains | Refresh the page and try again |

If stuck, check the terminal for error messages and search them online.

---

## Advanced Options

### Building C++ Kernel (Optional, for Speed)
The C++ Kernel Bridge provides a significant performance boost. It auto-detects three modes:
1. **NATIVE**: The fastest mode, using a compiled pybind11 module.
2. **IPC**: Subprocess communication.
3. **FALLBACK**: Pure Python (always available).

**To build the native module:**
1. Install CMake and a C++ compiler (GCC/MSVC).
2. Run the build script:
   ```bash
   # Linux/macOS
   bash build.sh --rebuild
   
   # Windows (PowerShell)
   ./build.sh --rebuild
   ```
3. The server will automatically switch to **NATIVE** mode on the next start.

### Character Studio (Create Your Own AI)
1. Run: `python studio/character_studio.py`
2. Open http://localhost:8500
3. Design custom AI characters.

### API Usage (For Developers)
- Use endpoints like `/api/v1/query` for programmatic access.
- See http://localhost:5000/docs for full API docs.

---

## Support

- **GitHub Issues**: Report problems at https://github.com/Str8biddness/synthesus/issues
- **Documentation**: Check TECHNICAL_DOCUMENTATION.md for details.
- **Community**: Join discussions on GitHub.

Enjoy your new AI assistant! Remember, it's learning from your feedback, so keep interacting. 🚀