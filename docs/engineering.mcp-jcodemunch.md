# jCodeMunch MCP Setup

This repository does not need a checked-in `mcp/` folder to use jCodeMunch. The application code does not import the vendored copy; MCP usage is configured in the client that launches the server.

## Recommended Launch Command

Use `uvx` so the MCP server is resolved outside the repo:

```bash
uvx --from jcodemunch-mcp jcodemunch-mcp
```

If you want a pinned version for repeatable local setup, replace the package name with a versioned spec such as `jcodemunch-mcp==0.2.26`.

## Example MCP Client Config

```json
{
  "mcpServers": {
    "jcodemunch": {
      "command": "uvx",
      "args": ["--from", "jcodemunch-mcp", "jcodemunch-mcp"]
    }
  }
}
```

## Notes

- `pip install jcodemunch-mcp` also works, but `uvx` avoids depending on a user PATH entry.
- Optional environment variables such as `GITHUB_TOKEN`, `ANTHROPIC_API_KEY`, and `GOOGLE_API_KEY` belong in the MCP client config, not in this repo.
- Direct invocation was verified from this workspace on 2026-03-07 with `uvx --from jcodemunch-mcp jcodemunch-mcp --help`.
