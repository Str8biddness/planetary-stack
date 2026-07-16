# Synthesus 4.0 - Global Requirements

This document outlines the dependencies for the entire Synthesus 4.0 ecosystem, including the **Ghostkey Desktop App**, the **Android Host Backend**, and the **Synthesus Cognitive Framework**.

## 🐍 Python Requirements (v3.10+)

The following packages are required for the AI core and Desktop GUI:

- **GUI & Interface:** `customtkinter`, `packaging`, `darkdetect`
- **Cognitive Engine:** `numpy`, `scipy`, `scikit-learn`, `faiss-cpu`, `pydantic`
- **API & Networking:** `fastapi`, `uvicorn`, `httpx`, `python-dotenv`
- **Data & Persistence:** `sqlalchemy`, `asyncpg`, `pgvector`, `tenacity`
- **Utilities:** `rich`, `jinja2`

## 📦 Node.js Requirements (v18+)

Required for the Synthesus Framework's web dashboard and multimodal amplification layers:

- `typescript`
- `vite` (for frontend components)
- `jest` (for testing)

## 🖥️ System-Specific Dependencies

### Linux (Ubuntu/Debian)
- `build-essential` (for C++ extensions)
- `python3-dev`, `python3-venv`
- `libtk8.6` (for Tkinter support)

### Termux (Android)
- `python`, `nodejs`
- `build-essential`
- `tur-repo` (for specialized packages like `pgvector` or `faiss` if needed)

### Windows
- `Git for Windows`
- `Python 3.11+` (Ensure "Add to PATH" is checked)
- `C++ Build Tools` (Required for some core C++ optimizations)
