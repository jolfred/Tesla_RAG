def read_docx(file_path: str) -> str | None:
    try:
        from docx import Document
        doc = Document(file_path)
        return '\n'.join(p.text for p in doc.paragraphs)
    except Exception:
        return None
