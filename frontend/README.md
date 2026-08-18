# Frontend

React 18 + Vite + TypeScript + TailwindCSS + D3.js

## Structure

- `src/components/` — Reusable UI components
- `src/pages/` — Page components
- `src/hooks/` — Custom React hooks
- `src/utils/` — API client, helpers
- `src/types/` — TypeScript types (mirrors API schemas)

## Running

```bash
cd frontend
npm install
npm run dev
```

## Design System

Colors, typography, spacing from `03_UIUX_Design.md` encoded in `tailwind.config.js`.

## API Proxy

Vite dev server proxies `/api/*` to `http://api:8000` (see `vite.config.ts`).