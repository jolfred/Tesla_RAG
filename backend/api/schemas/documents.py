from pydantic import BaseModel


class DocumentUploadResponse(BaseModel):
    id: str
    title: str
    status: str = "uploaded"
