import logging
import re

logger = logging.getLogger(__name__)

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB


def extract_text_from_pdf(file_source) -> tuple[str, int]:
    """
    Extract text from a PDF using pdfplumber.
    Returns (text, page_count).

    ``file_source`` can be:
      - a file path (str / os.PathLike)
      - any file-like object with a .read() method (e.g. FieldFile.open(), BytesIO)

    Handles encrypted PDFs and image-only PDFs gracefully.
    """
    try:
        import pdfplumber
    except ImportError:
        logger.error('pdfplumber not installed. Cannot extract PDF text.')
        return '', 0

    text_parts = []
    page_count = 0
    source_label = file_source if isinstance(file_source, str) else repr(file_source)

    try:
        with pdfplumber.open(file_source) as pdf:
            page_count = len(pdf.pages)
            for i, page in enumerate(pdf.pages):
                try:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)
                    else:
                        logger.debug('Page %d appears to be image-only or empty.', i + 1)
                except Exception as page_err:
                    logger.warning('Error extracting page %d: %s', i + 1, page_err)
                    continue
    except Exception as e:
        error_msg = str(e).lower()
        if 'encrypted' in error_msg or 'password' in error_msg:
            logger.warning('PDF is encrypted: %s', source_label)
            return '[ENCRYPTED PDF: text extraction not possible]', 0
        logger.exception('Failed to extract PDF text from %s: %s', source_label, e)
        raise

    full_text = '\n\n'.join(text_parts)
    cleaned = clean_text(full_text)

    if not cleaned and page_count > 0:
        cleaned = '[IMAGE-ONLY PDF: no extractable text found]'

    return cleaned, page_count


def validate_pdf(file) -> tuple[bool, str]:
    """
    Validate that a file is a real PDF, within size limits.
    Returns (is_valid, error_message).
    """
    if hasattr(file, 'size') and file.size > MAX_FILE_SIZE:
        return False, f'File too large. Maximum size is 20 MB.'

    # Check PDF magic bytes
    try:
        file.seek(0)
        header = file.read(5)
        file.seek(0)
        if header != b'%PDF-':
            return False, 'File does not appear to be a valid PDF.'
    except Exception:
        return False, 'Cannot read file header.'

    return True, ''


def clean_text(text: str) -> str:
    """
    Clean extracted PDF text:
    - Remove excessive whitespace
    - Fix common encoding artifacts
    - Remove page headers/footers patterns
    - Normalize line endings
    """
    if not text:
        return ''

    # Fix common PDF encoding artifacts
    replacements = {
        '\x00': '',
        '\ufffd': '',
        '\u2019': "'",
        '\u2018': "'",
        '\u201c': '"',
        '\u201d': '"',
        '\u2013': '-',
        '\u2014': '--',
        '\u2026': '...',
    }
    for old, new in replacements.items():
        text = text.replace(old, new)

    # Normalize line endings
    text = text.replace('\r\n', '\n').replace('\r', '\n')

    # Remove lines that are just page numbers
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        stripped = line.strip()
        # Skip lines that are just numbers (page numbers)
        if re.match(r'^\d+$', stripped) and len(stripped) <= 4:
            continue
        cleaned_lines.append(line)

    text = '\n'.join(cleaned_lines)

    # Collapse 3+ consecutive newlines to 2
    text = re.sub(r'\n{3,}', '\n\n', text)

    # Remove trailing whitespace from each line
    text = '\n'.join(line.rstrip() for line in text.split('\n'))

    return text.strip()


def validate_pdf_file(file) -> tuple[bool, str]:
    """Alias for validate_pdf — validates file is a real PDF within size limits."""
    return validate_pdf(file)
