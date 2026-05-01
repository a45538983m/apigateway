from pydantic import BaseModel
from typing import Optional

class UserRegister(BaseModel):
    phone: str
    email: Optional[str] = None
    password: str
    full_name: Optional[str] = None
    license_number: str

class LoginForm(BaseModel):
    phone: str
    password: str