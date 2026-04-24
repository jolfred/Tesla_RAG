from docx import Document

def read_docx(path):
    doc = Document(path)
    return "\n".join([p.text for p in doc.paragraphs])