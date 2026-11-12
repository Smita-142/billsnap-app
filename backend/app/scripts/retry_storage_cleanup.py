import asyncio

from app.database.connection import get_session_factory
from app.services.deletion_service import process_storage_cleanup_jobs


async def main():
    factory = get_session_factory()
    async with factory() as session:
        completed, pending = await process_storage_cleanup_jobs(session)
    print(f"Storage cleanup jobs completed: {completed}; still pending: {pending}")


if __name__ == "__main__":
    asyncio.run(main())
