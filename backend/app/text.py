import io
import re
from pypdf import PdfReader


def normalize_pdf_text(text: str) -> str:
    """Repair tracked lettering only when a line is overwhelmingly single glyphs.

    Single spaces separate glyphs in these PDFs; double spaces separate words.
    Never apply to ordinary prose or indiscriminately remove word boundaries.
    """
    all_tokens = text.split()
    tracked_page = len(all_tokens) > 30 and sum(len(t) == 1 for t in all_tokens) / len(all_tokens) > .85
    lines = []
    for line in text.splitlines():
        tokens = line.split()
        if len(tokens) >= (2 if tracked_page else 8) and sum(len(t) == 1 for t in tokens) / len(tokens) > .85:
            line = re.sub(r'(?<=\S) (?=\S)', '', line)
        lines.append(line.strip())
    return '\n'.join(lines)


def extract(data: bytes, suffix: str) -> list[tuple[int, str]]:
    if suffix == '.pdf':
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise ValueError('Şifreli PDF desteklenmiyor.')
        if len(reader.pages) > 300:
            raise ValueError('En fazla 300 sayfalık PDF yükleyebilirsiniz.')
        return [(i + 1, normalize_pdf_text(page.extract_text() or '')) for i, page in enumerate(reader.pages)]
    try:
        return [(1, data.decode('utf-8-sig'))]
    except UnicodeDecodeError as exc:
        raise ValueError('Metin dosyası UTF-8 biçiminde olmalı.') from exc


def chunks(pages: list[tuple[int, str]], size: int = 1000, overlap: int = 150) -> list[dict]:
    if not 0 <= overlap < size:
        raise ValueError('Invalid chunk overlap')
    result = []
    for page, raw in pages:
        text = ' '.join(raw.split())
        for start in range(0, len(text), size - overlap):
            result.append({'page': page, 'text': text[start:start + size]})
            if start + size >= len(text):
                break
    return result
