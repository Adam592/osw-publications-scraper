from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator

STARTING_POINT = date(2001, 1, 1)

class Publication(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    url: str
    title: str = Field(min_length=3, max_length=500)
    pub_type: str = Field(min_length=2)
    published: date
    authors: list[str] = Field(default_factory=list)
    regions: list[str] = Field(default_factory=list)

    @field_validator("url")
    @classmethod
    def url_points_to_publication(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")) or "/publikacje/" not in value:
            raise ValueError(f"Not a valid publication URL: {value!r}")
        return value

    @field_validator("published")
    @classmethod
    def date_is_valid(cls, value: date) -> date:
        if value < STARTING_POINT:
            raise ValueError(f"Invalid date, no publications before {STARTING_POINT}")
        elif value > date.today():
            raise ValueError(f"Provided date is in the future")
        return value

    @field_validator("authors", "regions")
    @classmethod
    def drop_blank_and_duplicates(cls, values: list[str]) -> list[str]:
        cleaned = [v.strip() for v in values if v and v.strip()]
        return list(dict.fromkeys(cleaned))