"""Request / response models. They are also what Swagger UI (/docs) shows as the API documentation."""
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000, description="The user's question.")

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"question": "How many days of annual leave do full-time employees get per year?"}]}
    )

    @field_validator("question")
    @classmethod
    def not_blank(cls, value: str) -> str:
        """Reject whitespace-only questions (they pass min_length but are meaningless)."""
        value = value.strip()
        if not value:
            raise ValueError("question must not be empty or whitespace")
        return value


class QueryResponse(BaseModel):
    answer: str = Field(..., description="Answer grounded in the retrieved documents, with [S#] citation tags.")
    sources: List[str] = Field(
        ..., description="Cited sources. Each entry starts with its tag so it maps to the [S#] tags in the answer."
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "answer": "Full-time employees get 21 days of annual leave per year. [S1]",
                    "sources": ["[S1] hr_leave_policy.pdf, p.1, chunk 0"],
                }
            ]
        }
    )


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    vector_store_loaded: bool
    vector_store_dir: Optional[str] = Field(default=None, description="Folder the vector store was loaded from.")
    num_chunks: Optional[int] = None
    embedding_model: Optional[str] = None
    ollama_reachable: bool
    ollama_model: Optional[str] = None
    model_available: bool
    detail: Optional[str] = Field(default=None, description="Human-readable reason when status is 'degraded'.")
