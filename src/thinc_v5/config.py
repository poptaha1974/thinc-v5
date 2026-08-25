from typing import Literal

from pydantic import BaseModel, field_validator


class Settings(BaseModel):
    database_url: str
    environment: Literal["test", "development", "production"] = "development"

    @field_validator("database_url")
    @classmethod
    def require_database_url(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("database_url must not be empty")
        return value
