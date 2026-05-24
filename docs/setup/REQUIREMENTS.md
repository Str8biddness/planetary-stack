### 📱 Termux (Android Terminal)
```bash
pkg update && pkg upgrade && pkg install -y python nodejs git build-essential && git clone https://github.com/Str8biddness/synthesus.git && cd synthesus && python -m venv venv && source venv/bin/activate && pip install -r requirements.txt && npm install
```

**Note:** PostgreSQL on Termux requires additional setup via proot. For a simpler setup, consider using SQLite3 instead:
```bash
pkg install sqlite
```