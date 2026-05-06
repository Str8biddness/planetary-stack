# Synthesus 4.0: Ghostkey Quad Brain Monorepo

Welcome to the unified home of **Synthesus 4.0**. This repository consolidates the Ghostkey AI Android components, the Desktop Terminal, and the core Synthesus Cognitive Framework.

## ⚡ Quick Install One-Liners

Choose your OS and paste the command into your terminal. This will clone the repo and install all Python dependencies.

### 📱 Termux (Android)
```bash
pkg update && pkg upgrade && pkg install -y python nodejs git build-essential && git clone https://github.com/Str8biddness/Synthesus_4.0.git && cd Synthesus_4.0 && python -m venv venv && source venv/bin/activate && pip install customtkinter packaging -r synthesus_framework/requirements.txt
```

### 🐧 Linux (Ubuntu/Debian)
```bash
sudo apt update && sudo apt install -y python3-venv python3-pip nodejs npm git && git clone https://github.com/Str8biddness/Synthesus_4.0.git && cd Synthesus_4.0 && python3 -m venv venv && source venv/bin/activate && pip install customtkinter packaging -r synthesus_framework/requirements.txt
```

### 🪟 Windows (PowerShell - Run as Admin)
```powershell
git clone https://github.com/Str8biddness/Synthesus_4.0.git; cd Synthesus_4.0; python -m venv venv; .\venv\Scripts\Activate.ps1; pip install customtkinter packaging -r synthesus_framework/requirements.txt
```

---

## 📂 Project Structure

- `desktop_app.py`: The futuristic GUI terminal for PC.
- `backend.py`: The bridge between the AI core and the Android/Desktop interfaces.
- `app/`: Source code for the Ghostkey Android application.
- `synthesus_framework/`: The core cognitive engine, cognitive modules, and ML organs.

## 🛠️ Detailed Requirements
See [REQUIREMENTS_4.0.md](./REQUIREMENTS_4.0.md) for a full breakdown of dependencies.

## 🚀 Launching the Desktop App
Once installed, run:
```bash
python desktop_app.py
```
