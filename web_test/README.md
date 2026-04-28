# SendBot — Web UI

React chat interface for the SENDIT customer-support chatbot. Connects to the FastAPI backend running on RunPod.

---

## Prerequisites

- **Node.js** 18+ (with npm)
- The chatbot API must be accessible (either locally or via SSH tunnel)

---

## Quick Start

```bash
# 1. Install dependencies (first time only)
npm install

# 2. Start the dev server
npm run dev
```

The app starts at **http://localhost:5173**.

---

## Connecting to the API

The app asks for the API URL on first launch (stored in `localStorage`).

- **If the API runs on RunPod**, open an SSH tunnel first:

  ```powershell
  ssh -N -L 9000:localhost:8000 runpod
  ```

  Then set the API URL in the app to: `http://localhost:9000`

- **If the API runs locally**: set it to `http://localhost:8000`

---

## Build for Production

```bash
npm run build     # outputs to dist/
npm run preview   # preview the production build locally
```
