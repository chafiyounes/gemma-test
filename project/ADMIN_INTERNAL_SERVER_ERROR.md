# Admin “Internal server error” (500)

Symptom: the staff console or `/api/admin/*` returns JSON `{"detail":"Internal server error"}` (generic) after document or overview actions.

## Quick checks on the pod

1. **API log (real traceback)**  
   ```bash
   tail -80 /workspace/gemma-test/logs/api.log
   # or, if logging goes to tmux only:
   grep -i "error\\|exception\\|traceback" /workspace/gemma-test/logs/fastapi.log | tail -40
   ```

2. **Health**  
   `curl -sS http://127.0.0.1:8000/health`

3. **Documents overview (manager cookie required)**  
   Reproduce with browser devtools → Network → failing request URL and response body.

## Causes we hardened in code

- **`get_overview()`** could crash the whole `/api/admin/documents/overview` response if **one category** misbehaved or if **`RAG_DEFAULT_CATEGORY`** in `.env` was invalid (sanitization raised `DocumentAdminError`). Overview now **skips bad categories** and falls back to `procedures` for the default label when needed.
- **`DocStore.reload()`** could crash if **one .md / .txt / .docx / .pdf** raised during indexing. Loading now **logs and skips** bad files instead of failing the whole RAG reload.

## Surface the real error message (temporary)

In `.env` on the pod:

```env
API_EXPOSE_ERROR_DETAIL=true
```

Restart the API (`bash scripts/restart_api.sh`). JSON 500 responses will include `exception type` and message. **Turn off in production** after debugging (can leak paths or internals).

## Apply-plan still fails

- Prefer the **admin UI** message or, with `API_EXPOSE_ERROR_DETAIL=true`, the response `detail`.
- Business rule failures are usually **400** with a clear string (e.g. file exists, ambiguous name).
- If you see **`warnings`** after save: disk write succeeded but **`reload_document_store()`** had a problem earlier (now less likely with per-file skip).

## Deploy

After a code fix: push `main`, then from the laptop run `python scripts/deploy_runner.py --skip-deps` (see `project/DEPLOYMENT.md`).
