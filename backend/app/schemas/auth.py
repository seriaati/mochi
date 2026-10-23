from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    password: str = Field(max_length=1024)


class SessionOut(BaseModel):
    authenticated: bool
