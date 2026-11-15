from pydantic import BaseModel, EmailStr, Field

class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

class LoginIn(BaseModel):
    email: EmailStr
    password: str

class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)

class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=10000)
    preferred_language: str | None = Field(default=None, max_length=35)


class MediaJobIn(BaseModel):
    media_type: str = Field(pattern="^(image|video)$")
    prompt: str = Field(min_length=3, max_length=4000)
    reference_url: str | None = Field(default=None, max_length=2048)


class ProjectFileWriteIn(BaseModel):
    content: str = Field(max_length=512 * 1024)
