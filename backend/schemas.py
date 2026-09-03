from datetime import date

from pydantic import BaseModel, Field, field_validator, model_validator


class TopicAnalysisInput(BaseModel):
    query: str = Field(min_length=1, max_length=160)
    source: str = Field(default="", max_length=160)
    color: str = Field(default="#005a8d", pattern=r"^#[0-9a-fA-F]{6}$")

    @field_validator("query", "source")
    @classmethod
    def clean_text(cls, value):
        return " ".join(value.split())


class TopicJobInput(BaseModel):
    analyses: list[TopicAnalysisInput] = Field(min_length=1, max_length=4)
    from_date: date
    to_date: date
    show_values: bool = True

    @model_validator(mode="after")
    def validate_interval(self):
        if self.from_date > self.to_date:
            raise ValueError("from_date must be before or equal to to_date")
        return self


class TopicJobCreated(BaseModel):
    id: str
    status: str
    progress: int
    cached: bool = False


class TopicJobResponse(BaseModel):
    id: str
    status: str
    progress: int
    result: dict | None = None
    error: str | None = None
