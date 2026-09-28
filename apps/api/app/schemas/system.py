from pydantic import BaseModel


class SystemInfo(BaseModel):
    name: str
    environment: str
    version: str
    llm_provider: str
    embedding_provider: str
