from datetime import datetime
from fastapi import APIRouter, File, HTTPException, UploadFile, Request
from fastapi.responses import StreamingResponse, RedirectResponse
from app.server_backup import create_full_backup, create_database_export, restore_full_backup
from app.access import require_admin

router = APIRouter()


@router.get("/backup")
def download_backup(request: Request):
    require_admin(request)
    try:
        payload = create_full_backup()
        filename = "moj_knjizni_koticek_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".zip"
        return StreamingResponse(iter([payload]), media_type="application/zip",
                                 headers={"Content-Disposition": f'attachment; filename="{filename}"'})
    except Exception as exc:
        raise HTTPException(500, f"Izvoz varnostne kopije ni uspel: {exc}") from exc


@router.get("/backup/database")
def download_database_export(request: Request):
    require_admin(request)
    try:
        payload = create_database_export()
        filename = "moj_knjizni_koticek_baza_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".json.gz"
        return StreamingResponse(iter([payload]), media_type="application/gzip",
                                 headers={"Content-Disposition": f'attachment; filename="{filename}"'})
    except Exception as exc:
        raise HTTPException(500, f"Izvoz baze ni uspel: {exc}") from exc


@router.post("/backup/restore")
async def restore_uploaded_backup(request: Request, file: UploadFile = File(...)):
    require_admin(request)
    if not file.filename:
        raise HTTPException(400, "Izberi datoteko varnostne kopije.")
    content = await file.read(300 * 1024 * 1024 + 1)
    try:
        # Validate the uploaded archive before touching the database. The restore
        # routine applies its changes in one DB transaction; on failure it rolls
        # back. No backup archive is retained on the shared hosting account.
        restore_full_backup(content, file.filename)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, f"Obnova ni uspela: {exc}") from exc
    return RedirectResponse("/settings?restore=ok", status_code=303)
