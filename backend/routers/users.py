import uuid
from fastapi import APIRouter, HTTPException
from backend.database import get_db
from backend.models import UserCreate, UserResponse

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("", response_model=list[UserResponse])
def list_users():
    db = get_db()
    try:
        rows = db.execute("SELECT * FROM users ORDER BY name").fetchall()
        return [UserResponse(**dict(r)) for r in rows]
    finally:
        db.close()


@router.post("", response_model=UserResponse, status_code=201)
def create_user(user: UserCreate):
    if not user.name.strip():
        raise HTTPException(status_code=400, detail="Name is required")
    token = uuid.uuid4().hex
    db = get_db()
    try:
        cursor = db.execute(
            "INSERT INTO users (name, token) VALUES (?, ?)",
            (user.name.strip(), token),
        )
        db.commit()
        row = db.execute("SELECT * FROM users WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return UserResponse(**dict(row))
    finally:
        db.close()


@router.get("/by-token/{token}", response_model=UserResponse)
def get_user_by_token(token: str):
    db = get_db()
    try:
        row = db.execute("SELECT * FROM users WHERE token = ?", (token,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="User not found")
        return UserResponse(**dict(row))
    finally:
        db.close()


@router.delete("/{user_id}", status_code=204)
def delete_user(user_id: int):
    db = get_db()
    try:
        db.execute("DELETE FROM users WHERE id = ?", (user_id,))
        db.commit()
    finally:
        db.close()
