# Engineering Removed Files

## Removal Log

| File Removed | Why Removed | Replacement |
|---|---|---|
| `frontend/dashboard/tsconfig.tsbuildinfo` | Generated TypeScript build artifact should not be version-controlled; causes noisy diffs and stale path metadata after renames. | Regenerated automatically by `npm run build` when needed. |
| `mcp/jcodemunch-mcp/` | Vendored third-party MCP source was not used by the application runtime and duplicated an externally installable tool. | Configure `jcodemunch-mcp` directly in the MCP client; see `docs/engineering.mcp-jcodemunch.md`. |

## Verification Notes

- Removal was validated by repository search to ensure no runtime imports reference the file.
- This deletion does not change runtime behavior.
- jCodeMunch remains usable after removal because it is launched as an external MCP server, not imported by repository code.
