
from django.core.exceptions import ValidationError
from pathlib import Path
# =====================================================
# Validators
# =====================================================

def validate_attachment(file):
    max_size = 1 * 1024 * 1024  # 1 MB

    if file.size > max_size:
        raise ValidationError(
            "File size must not exceed 1 MB."
        )

    allowed_extensions = {
        '.pdf',
        '.jpg',
        '.jpeg',
        '.png',
        '.doc',
        '.docx',
        '.xlsx',
    }

    ext = Path(file.name).suffix.lower()

    if ext not in allowed_extensions:
        raise ValidationError(
            "Unsupported file type."
        )
