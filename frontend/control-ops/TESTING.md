# Ops Control Testing

## Preflight

- Ensure the local reverse proxy is running and `ops-control.localhost`, `control.localhost`, and `control-api.localhost` resolve locally.
- Verify the ops console responds at `http://ops-control.localhost`.
- Verify the control API responds at `http://control-api.localhost/health/live`.
- For authenticated browser checks, seed `risk_token` and optionally `risk_username` in browser `localStorage`.

## Commands

- `npm run build`
- `npm test`
- `npm run test:e2e`

## Browser Notes

- The Playwright suite assumes the app is already reachable through the local reverse proxy.
- API interactions are mocked in-browser so the suite can validate auth, navigation, and visible error states without a live backend dataset.
