from fastapi import APIRouter, HTTPException
from typing import List
from schemas import User

router = APIRouter(prefix="/users", tags=["users"])

# In-memory users DB
users_db: List[User] = [
    User(id=1, name="Alice", email="alice@example.com"),
    User(id=2, name="Bob", email="bob@example.com"),
]


@router.get("/", response_model=List[User])
def get_users():
    return users_db


@router.get("/{user_id}", response_model=User)
def get_user(user_id: int):
    for user in users_db:
        if user.id == user_id:
            return user
    raise HTTPException(status_code=404, detail="User not found")


@router.post("/", response_model=User, status_code=201)
def create_user(user: User):
    users_db.append(user)
    return user


@router.put("/{user_id}", response_model=User)
def update_user(user_id: int, user: User):
    for idx, u in enumerate(users_db):
        if u.id == user_id:
            users_db[idx] = user
            return user
    raise HTTPException(status_code=404, detail="User not found")


@router.delete("/{user_id}", status_code=204)
def delete_user(user_id: int):
    for idx, u in enumerate(users_db):
        if u.id == user_id:
            users_db.pop(idx)
            return
    raise HTTPException(status_code=404, detail="User not found")
