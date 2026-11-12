from fastapi import HTTPException, status


def require_redaction_service() -> None:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Pixel-level privacy detection and redaction are not configured. No image was modified or sent to an external provider.",
    )
