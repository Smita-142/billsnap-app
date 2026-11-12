from urllib.parse import quote

import httpx
from fastapi import HTTPException, status

from app.core.config import get_settings


def _storage_credentials() -> tuple[str, str, str]:
    settings = get_settings()
    base_url = settings.supabase_url
    service_key = settings.supabase_service_role_key
    bucket = settings.supabase_storage_bucket
    if not base_url or not service_key or not bucket:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase Storage is not configured.",
        )
    return (
        base_url.rstrip("/"),
        service_key.get_secret_value(),
        bucket,
    )


async def upload_temporary_image(path: str, content: bytes, mime_type: str) -> None:
    base_url, key, bucket = _storage_credentials()
    encoded_path = quote(path, safe="/")
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"{base_url}/storage/v1/object/{quote(bucket, safe='')}/{encoded_path}",
                content=content,
                headers={
                    "Authorization": f"Bearer {key}",
                    "apikey": key,
                    "Content-Type": mime_type,
                    "x-upsert": "false",
                },
            )
        response.raise_for_status()
    except httpx.HTTPStatusError as error:
        raise HTTPException(status_code=502, detail="Supabase Storage rejected the temporary upload.") from error
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail="Supabase Storage could not be reached.") from error


async def download_temporary_image(path: str, max_bytes: int) -> bytes:
    base_url, key, bucket = _storage_credentials()
    encoded_path = quote(path, safe="/")
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            async with client.stream(
                "GET",
                f"{base_url}/storage/v1/object/{quote(bucket, safe='')}/{encoded_path}",
                headers={"Authorization": f"******", "apikey": key},
            ) as response:
                response.raise_for_status()
                content_length = response.headers.get("content-length")
                if content_length and int(content_length) > max_bytes:
                    raise HTTPException(status_code=413, detail="Stored image exceeds the OCR size limit.")
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    content.extend(chunk)
                    if len(content) > max_bytes:
                        raise HTTPException(status_code=413, detail="Stored image exceeds the OCR size limit.")
                return bytes(content)
    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError) as error:
        raise HTTPException(status_code=502, detail="The temporary image could not be read for bill validation.") from error


async def delete_storage_object(path: str) -> None:
    base_url, key, bucket = _storage_credentials()
    encoded_path = quote(path, safe="/")
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.delete(
                f"{base_url}/storage/v1/object/{quote(bucket, safe='')}/{encoded_path}",
                headers={"Authorization": f"Bearer {key}", "apikey": key},
            )
        if response.status_code not in (200, 204, 404):
            response.raise_for_status()
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail="Storage cleanup failed; a retry has been queued.") from error
