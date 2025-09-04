from pydantic import BaseModel, Field

class PromptItem(BaseModel):
    key: str = Field(..., examples=["GREETING"])
    value: str = Field(..., min_length=1, max_length=5000)

class PromptUpdate(BaseModel):
    value: str = Field(..., min_length=1, max_length=5000)
