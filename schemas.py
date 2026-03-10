from pydantic import BaseModel

# What we need when someone registers
class UserCreate(BaseModel):
    username: str
    password: str

# What we give back when they log in
class Token(BaseModel):
    access_token: str
    token_type: str

# What we show when someone asks for user info
class UserResponse(BaseModel):
    username: str
    is_premium: bool

    class Config:
        from_attributes = True