# vendor/

This directory holds the SQLite3 amalgamation needed to compile the ZO C++ kernel.

## Required files

- `sqlite3.c` — SQLite3 amalgamation source
- `sqlite3.h` — SQLite3 header

## Download (handled automatically by build.sh)

```bash
wget https://www.sqlite.org/2024/sqlite-amalgamation-3450300.zip
unzip sqlite-amalgamation-3450300.zip
cp sqlite-amalgamation-3450300/sqlite3.c vendor/
cp sqlite-amalgamation-3450300/sqlite3.h vendor/
```

Or simply run:

```bash
bash build.sh --rebuild
```

The build script auto-downloads sqlite3 if missing.
