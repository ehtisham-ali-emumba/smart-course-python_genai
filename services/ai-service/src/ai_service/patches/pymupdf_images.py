"""Fix for langchain-community 0.4.1 BytesIO bug in PyMuPDFParser.

Bug: _extract_images_from_page checks BytesIO size BEFORE writing image data.
Issue: https://github.com/langchain-ai/langchain/issues/34400
Fix PR: https://github.com/langchain-ai/langchain-community/pull/193 (merged, not released)

TODO: Remove this patch once langchain-community releases a version with the fix.
"""

import io

import numpy as np
import pymupdf
import structlog
from langchain_community.document_loaders.parsers.pdf import PyMuPDFParser
from langchain_core.document_loaders import Blob

logger = structlog.get_logger(__name__)


def _patched_extract_images_from_page(self, doc, page):
    """Fixed: numpy.save() BEFORE BytesIO size check."""
    if not self.images_parser:
        return ""

    from langchain_community.document_loaders.parsers.pdf import (
        _FORMAT_IMAGE_STR,
        _JOIN_IMAGES,
        _format_inner_image,
    )

    img_list = page.get_images()
    images = []
    for img in img_list:
        xref = img[0]
        pix = pymupdf.Pixmap(doc, xref)
        image = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, -1)
        image_bytes = io.BytesIO()
        np.save(image_bytes, image)
        if image_bytes.getbuffer().nbytes == 0:
            continue
        blob = Blob.from_data(image_bytes.getvalue(), mime_type="application/x-npy")
        image_text = next(self.images_parser.lazy_parse(blob)).page_content
        images.append(_format_inner_image(blob, image_text, self.images_inner_format))
    return _FORMAT_IMAGE_STR.format(image_text=_JOIN_IMAGES.join(filter(None, images)))


def apply():
    """Apply the monkey-patch."""
    PyMuPDFParser._extract_images_from_page = _patched_extract_images_from_page
    logger.info("[PATCH] Applied fix for langchain-community 0.4.1 PyMuPDF image extraction bug")
