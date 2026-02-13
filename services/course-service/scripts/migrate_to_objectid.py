"""
MongoDB Migration Script: Integer IDs → ObjectId Strings

Run this script ONCE to migrate existing course content from integer module_id/lesson_id
to ObjectId strings and add is_active fields.

Usage (Docker):
    docker compose run --rm course-service python scripts/migrate_to_objectid.py
"""

import asyncio
import secrets
import sys
from pathlib import Path

# Add src to path for config import
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from motor.motor_asyncio import AsyncIOMotorClient

from config import settings


def generate_objectid_string() -> str:
    """Generate a 24-char hex string compatible with MongoDB ObjectId format."""
    return secrets.token_hex(12)

MONGO_URI = settings.MONGODB_URL
DATABASE_NAME = settings.MONGODB_DB_NAME
COLLECTION_NAME = "course_content"


async def migrate_content():
    """Migrate all course content documents."""
    client = AsyncIOMotorClient(MONGO_URI)
    db = client[DATABASE_NAME]
    collection = db[COLLECTION_NAME]

    cursor = collection.find({})
    migrated_count = 0

    async for doc in cursor:
        course_id = doc.get("course_id")
        modules = doc.get("modules", [])
        updated_modules = []

        for module in modules:
            old_module_id = module.get("module_id")
            if isinstance(old_module_id, int):
                module["module_id"] = generate_objectid_string()
            elif old_module_id is None:
                module["module_id"] = generate_objectid_string()

            if "is_active" not in module:
                module["is_active"] = True

            lessons = module.get("lessons", [])
            updated_lessons = []
            for lesson in lessons:
                old_lesson_id = lesson.get("lesson_id")
                if isinstance(old_lesson_id, int):
                    lesson["lesson_id"] = generate_objectid_string()
                elif old_lesson_id is None:
                    lesson["lesson_id"] = generate_objectid_string()

                if "is_active" not in lesson:
                    lesson["is_active"] = True

                resources = lesson.get("resources", [])
                for resource in resources:
                    if "resource_id" not in resource:
                        resource["resource_id"] = generate_objectid_string()
                    if "is_active" not in resource:
                        resource["is_active"] = True

                updated_lessons.append(lesson)

            module["lessons"] = updated_lessons
            updated_modules.append(module)

        await collection.update_one(
            {"_id": doc["_id"]},
            {"$set": {"modules": updated_modules}},
        )
        migrated_count += 1
        print(f"Migrated course_id={course_id}")

    print(f"\nMigration complete. {migrated_count} documents updated.")
    client.close()


if __name__ == "__main__":
    asyncio.run(migrate_content())
