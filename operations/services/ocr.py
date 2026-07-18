from pathlib import Path

from paddleocr import PaddleOCR
from PIL import Image
from pdf2image import convert_from_path

from ..models import OCRStatus


# Create OCR engine once
ocr_engine = PaddleOCR(
    lang="fa",
    use_doc_orientation_classify=False,
    use_doc_unwarping=False,
    use_textline_orientation=False,
)


def image_to_text(image_path):

    result = ocr_engine.predict(str(image_path))

    text = []

    confidence = []

    for page in result:

        if "rec_texts" in page:

            text.extend(page["rec_texts"])

        if "rec_scores" in page:

            confidence.extend(page["rec_scores"])

    avg = 0

    if confidence:
        avg = sum(confidence) / len(confidence)

    return "\n".join(text), avg


def pdf_to_text(pdf_path):

    pages = convert_from_path(pdf_path)

    full_text = []

    scores = []

    for i, page in enumerate(pages):

        temp = Path(pdf_path).with_suffix(f".page{i}.jpg")

        page.save(temp)

        txt, score = image_to_text(temp)

        full_text.append(txt)

        scores.append(score)

        temp.unlink(missing_ok=True)

    avg = 0

    if scores:
        avg = sum(scores) / len(scores)

    return "\n".join(full_text), avg


def run_attachment_ocr(attachment):

    attachment.ocr_status = OCRStatus.RUNNING

    attachment.save(update_fields=["ocr_status"])

    try:

        path = attachment.file.path

        suffix = Path(path).suffix.lower()

        if suffix == ".pdf":

            text, confidence = pdf_to_text(path)

        else:

            text, confidence = image_to_text(path)

        attachment.extracted_text = text

        attachment.ocr_confidence = confidence * 100

        attachment.ocr_status = OCRStatus.COMPLETED

        attachment.save()

        return text, confidence

    except Exception as e:

        attachment.ocr_status = OCRStatus.FAILED

        attachment.extracted_text = str(e)

        attachment.save()

        return "", 0