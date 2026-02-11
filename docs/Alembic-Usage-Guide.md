# Alembic Usage Guide — SmartCourse User Service

> Quick-reference for using Alembic migrations in this project's Dockerized environment.

---

## File Locations

| What              | Path                                                       |
| ----------------- | ---------------------------------------------------------- |
| Alembic config    | `services/user-service/alembic.ini`                        |
| Migration env     | `services/user-service/src/user_service/alembic/env.py`    |
| Migration scripts | `services/user-service/src/user_service/alembic/versions/` |
| Models            | `services/user-service/src/user_service/models/`           |
| Schemas           | `services/user-service/src/user_service/schemas/`          |

---

## Before Running Any Command

```bash
# Start Postgres first
docker compose up -d postgres
```

---

## Add a New Column (Step-by-Step)

### Step 1: Edit the Model

File: `services/user-service/src/user_service/models/user.py`

```python
class User(Base):
    __tablename__ = "users"
    # ... existing columns ...

    phone_number = Column(String(20), nullable=True)  # <-- ADD NEW COLUMN
```

### Step 2: Update Pydantic Schemas

**Important:** Import `Optional` from `typing` if using optional fields!

File: `services/user-service/src/user_service/schemas/user.py`

```python
from typing import Optional  # <-- DON'T FORGET THIS IMPORT

class UserResponse(BaseModel):
    # ... existing fields ...
    phone_number: Optional[str] = None  # <-- ADD TO RESPONSE

class UserUpdate(BaseModel):
    # ... existing fields ...
    phone_number: Optional[str] = Field(None, min_length=10, max_length=20)  # <-- ADD TO UPDATE
```

File: `services/user-service/src/user_service/schemas/auth.py` (if field is used in registration)

```python
from typing import Optional  # <-- DON'T FORGET THIS IMPORT

class UserRegister(BaseModel):
    # ... existing fields ...
    phone_number: Optional[str] = Field(None, min_length=10, max_length=20)  # <-- ADD
```

### Step 3: Update the Service (if needed)

File: `services/user-service/src/user_service/services/auth.py`

```python
user = await self.user_repo.create({
    # ... existing fields ...
    "phone_number": user_data.phone_number,  # <-- ADD
})
```

### Step 4: Generate Migration

```bash
docker compose run --rm user-service alembic revision --autogenerate -m "add_phone_number_to_users"
```

### Step 5: Review the Generated Migration

Check `services/user-service/src/user_service/alembic/versions/` for the new file. Verify:

```python
def upgrade() -> None:
    op.add_column('users', sa.Column('phone_number', sa.String(length=20), nullable=True))

def downgrade() -> None:
    op.drop_column('users', 'phone_number')
```

### Step 6: Apply Migration

```bash
docker compose run --rm user-service alembic upgrade head
```

### Step 7: Rebuild & Restart

```bash
docker compose build user-service
docker compose up -d user-service
```

### Step 8: Verify

```bash
docker compose exec postgres psql -U smartcourse -d smartcourse -c "\d users"
```

---

## Create a New Table (Step-by-Step)

### Step 1: Create the Model File

File: `services/user-service/src/user_service/models/enrollment.py`

```python
from datetime import datetime
from sqlalchemy import Column, Integer, ForeignKey, DateTime, String
from user_service.core.database import Base


class Enrollment(Base):
    __tablename__ = "enrollments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    course_id = Column(Integer, nullable=False)
    status = Column(String(50), default="active", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
```

### Step 2: Register in models/**init**.py

File: `services/user-service/src/user_service/models/__init__.py`

```python
from user_service.models.user import User
from user_service.models.instructor import InstructorProfile
from user_service.models.enrollment import Enrollment  # <-- ADD

__all__ = ["User", "InstructorProfile", "Enrollment"]  # <-- ADD TO LIST
```

### Step 3: Register in alembic/env.py

File: `services/user-service/src/user_service/alembic/env.py`

```python
# Import ALL models so they register with Base.metadata
from user_service.models import User, InstructorProfile, Enrollment  # <-- ADD HERE
```

### Step 4: Create Pydantic Schemas

File: `services/user-service/src/user_service/schemas/enrollment.py`

```python
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class EnrollmentCreate(BaseModel):
    course_id: int


class EnrollmentResponse(BaseModel):
    id: int
    user_id: int
    course_id: int
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
```

### Step 5: Generate Migration

```bash
docker compose run --rm user-service alembic revision --autogenerate -m "create_enrollments_table"
```

### Step 6: Review the Generated Migration

Verify the migration creates the table with all columns, indexes, and foreign keys.

### Step 7: Apply Migration

```bash
docker compose run --rm user-service alembic upgrade head
```

### Step 8: Rebuild & Restart

```bash
docker compose build user-service
docker compose up -d user-service
```

### Step 9: Verify

```bash
docker compose exec postgres psql -U smartcourse -d smartcourse -c "\d enrollments"
```

---

## Quick Reference Commands

| Task                    | Command                                                                                 |
| ----------------------- | --------------------------------------------------------------------------------------- |
| Start Postgres          | `docker compose up -d postgres`                                                         |
| Generate migration      | `docker compose run --rm user-service alembic revision --autogenerate -m "description"` |
| Apply all migrations    | `docker compose run --rm user-service alembic upgrade head`                             |
| Rollback last migration | `docker compose run --rm user-service alembic downgrade -1`                             |
| Check current version   | `docker compose run --rm user-service alembic current`                                  |
| View migration history  | `docker compose run --rm user-service alembic history`                                  |
| Rebuild service         | `docker compose build user-service`                                                     |
| Restart service         | `docker compose up -d user-service`                                                     |
| Check table structure   | `docker compose exec postgres psql -U smartcourse -d smartcourse -c "\d tablename"`     |

---

## Common Mistakes to Avoid

1. **Forgetting `from typing import Optional`** — Causes runtime errors when using `Optional[str]`
2. **Not importing new models in `env.py`** — Autogenerate won't detect the new table
3. **Not registering models in `models/__init__.py`** — Model won't be accessible elsewhere
4. **Forgetting to rebuild the Docker image** — Old code runs instead of new code
5. **Not updating schemas** — API won't accept/return the new field

---

## Remove a Column

1. Remove the column from the model
2. Generate: `docker compose run --rm user-service alembic revision --autogenerate -m "remove_column_name"`
3. Review the migration file
4. Apply: `docker compose run --rm user-service alembic upgrade head`
5. Rebuild: `docker compose build user-service && docker compose up -d user-service`

---

## Rename a Column (Manual Migration)

Autogenerate **cannot** detect renames. Create a manual migration:

```bash
docker compose run --rm user-service alembic revision -m "rename_phone_to_phone_number"
```

Edit the generated file:

```python
def upgrade() -> None:
    op.alter_column('users', 'phone', new_column_name='phone_number')

def downgrade() -> None:
    op.alter_column('users', 'phone_number', new_column_name='phone')
```

---

## Troubleshooting

| Problem                             | Solution                                                              |
| ----------------------------------- | --------------------------------------------------------------------- |
| "Target database is not up to date" | `docker compose run --rm user-service alembic upgrade head`           |
| "Can't locate revision"             | `docker compose run --rm user-service alembic stamp head`             |
| Empty migration generated           | Import all models in `env.py`                                         |
| "Relation already exists"           | `docker compose run --rm user-service alembic stamp head`             |
| Multiple heads                      | `docker compose run --rm user-service alembic merge heads -m "merge"` |

---

## Autogenerate Limitations

**CAN detect:** New/dropped tables, new/dropped columns, type changes, nullable changes, indexes, constraints

**CANNOT detect:** Column renames, table renames, data migrations, some CHECK constraints

---

## Best Practices

1. **Never use `create_all` in app code** — Alembic owns the schema
2. **Always review** generated migrations before applying
3. **Commit migration files** to git
4. **One logical change per migration**
5. **Import new models in `env.py`** — autogenerate only sees imported models
6. **Don't forget imports** — especially `from typing import Optional`
