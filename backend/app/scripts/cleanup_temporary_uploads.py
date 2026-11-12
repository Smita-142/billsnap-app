import asyncio

from app.database.connection import get_session_factory
from app.services.temporary_upload_service import purge_expired_temporary_uploads


async def main():
    factory = get_session_factory()
    async with factory() as session:
        removed, pending = await purge_expired_temporary_uploads(session)
    print(f"Expired temporary uploads processed: {removed}; storage cleanup pending: {pending}")


if __name__ == "__main__":
    asyncio.run(main())
