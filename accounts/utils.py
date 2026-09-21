import cv2
import numpy as np
from PIL import Image
from io import BytesIO

def extract_signature_ink(image_file):

    image_file.open("rb")
    try:
        data = np.frombuffer(image_file.read(), np.uint8)
    finally:
        image_file.close()

    img = cv2.imdecode(data, cv2.IMREAD_COLOR)

    if img is None:
        raise ValueError("Could not decode signature image — file may be corrupted or empty.")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    mask = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, 31, 15,
    )

    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    rgba = np.dstack((rgb, mask))

    output = BytesIO()
    Image.fromarray(rgba).save(output, format="PNG")
    output.seek(0)
    return output