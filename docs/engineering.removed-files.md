# Engineering Removed Files

## Removal Log

| File Removed | Why Removed | Replacement |
|---|---|---|
| `frontend/dashboard/tsconfig.tsbuildinfo` | Generated TypeScript build artifact should not be version-controlled; causes noisy diffs and stale path metadata after renames. | Regenerated automatically by `npm run build` when needed. |

## Verification Notes

- Removal was validated by repository search to ensure no runtime imports reference the file.
- This deletion does not change runtime behavior.
