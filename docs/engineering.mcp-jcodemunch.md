# jCodeMunch MCP Integration

This repository now vendors `jcodemunch-mcp` under:

- `mcp/jcodemunch-mcp`

Source was copied from `/Users/sourrrish/MCPs/jcodemunch-mcp` on 2026-03-07.
The copy excludes local machine artifacts (`.git`, `.DS_Store`, `bin/`, `lib/`, `include/`, `pyvenv.cfg`).

## Install Into Project Virtualenv

```bash
source .venv/bin/activate
python -m pip install -e mcp/jcodemunch-mcp
jcodemunch-mcp --help
```

## MCP Client Configuration

Use either the local virtualenv executable or `uvx`.

### Option 1: Project virtualenv executable

```json
{
  "mcpServers": {
    "jcodemunch": {
      "command": "/Users/sourrrish/Aegis AI/.venv/bin/jcodemunch-mcp",
      "args": []
    }
  }
}
```

### Option 2: Run from vendored source with `uvx`

```json
{
  "mcpServers": {
    "jcodemunch": {
      "command": "uvx",
      "args": [
        "--from",
        "/Users/sourrrish/Aegis AI/mcp/jcodemunch-mcp",
        "jcodemunch-mcp"
      ]
    }
  }
}
```

## Updating the Vendored Copy

```bash
mkdir -p mcp
rsync -a \
  --exclude '.git' \
  --exclude '.DS_Store' \
  --exclude 'bin' \
  --exclude 'include' \
  --exclude 'lib' \
  --exclude 'pyvenv.cfg' \
  /Users/sourrrish/MCPs/jcodemunch-mcp/ \
  mcp/jcodemunch-mcp/
```
