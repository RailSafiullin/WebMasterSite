import uuid
from typing import Optional
from fastapi_users import schemas


class UserRead(schemas.BaseUser[uuid.UUID]):
    id: int
    username: Optional[str] = None
    email: str

class UserCreate(schemas.BaseUserCreate):
    id: int
    username: Optional[str] = None
    email: str

class UserCreateWithRole(UserCreate):
    role: int    

class UserCreateWithRoleWithoutPassword(schemas.BaseUserUpdate):
    id: int
    username: Optional[str] = None
    email: str
    password: Optional[str] = None
    role: int    

class UserUpdate(schemas.BaseUserUpdate):
    id: int
    username: Optional[str] = None
    email: str
