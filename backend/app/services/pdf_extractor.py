from io import BytesIO
from typing import Dict, Any, Optional, List
import re
import logging
import multiprocessing
import gc

# Language detection
try:
    from langdetect import detect, DetectorFactory
    # Set seed for consistent results
    DetectorFactory.seed = 0
    LANGDETECT_AVAILABLE = True
except ImportError:
    LANGDETECT_AVAILABLE = False
    print("⚠️ langdetect not available. Install with: pip install langdetect")

# OCR imports with graceful fallback
try:
    import pytesseract
    from pdf2image import convert_from_bytes
    from PIL import Image, ImageEnhance
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

# EasyOCR import with graceful fallback
try:
    import easyocr
    import numpy as np
    EASYOCR_AVAILABLE = True
except ImportError as e:
    EASYOCR_AVAILABLE = False
    print(f"⚠️ EasyOCR not available: {e}")

# PyMuPDF import with graceful fallback.
# Handles PDF image formats that pdf2image/poppler silently fails on
# (JBIG2, CCITT, unusual XObject structures, eOffice-style embedded images).
try:
    import fitz  # PyMuPDF
    import io as _io
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False
    print("⚠️ PyMuPDF not available. Install with: pip install pymupdf")

logger = logging.getLogger(__name__)

# Log availability status on module load
logger.info(f"📦 OCR Availability: Tesseract={OCR_AVAILABLE}, EasyOCR={EASYOCR_AVAILABLE}, PyMuPDF={PYMUPDF_AVAILABLE}")

# Maximum image dimension (pixels) for EasyOCR to prevent OOM during inference
EASYOCR_MAX_DIMENSION = 1500


def _easyocr_subprocess_worker(
    pdf_bytes: bytes,
    num_pages: int,
    languages: list,
    dpi: int,
    max_dimension: int,
    result_queue: multiprocessing.Queue
):
    """
    Run EasyOCR in an isolated subprocess.
    If this process gets OOM-killed, the main server survives.
    """
    try:
        import easyocr
        import numpy as np
        from pdf2image import convert_from_bytes
        from PIL import Image as PILImage, ImageEnhance

        reader = easyocr.Reader(languages, gpu=False, verbose=False)

        extracted_text = ""
        confidence_scores = []

        # Process one page at a time to limit memory
        for page_idx in range(num_pages):
            image = None
            try:
                page_images = convert_from_bytes(
                    pdf_bytes,
                    first_page=page_idx + 1,
                    last_page=page_idx + 1,
                    dpi=dpi
                )
                if not page_images:
                    continue
                image = page_images[0]
                del page_images

                # Convert to grayscale + enhance contrast
                image = image.convert('L')
                enhancer = ImageEnhance.Contrast(image)
                image = enhancer.enhance(2.0)

                # Resize to limit memory during inference
                w, h = image.size
                max_dim = max(w, h)
                if max_dim > max_dimension:
                    scale = max_dimension / max_dim
                    new_w = int(w * scale)
                    new_h = int(h * scale)
                    image = image.resize((new_w, new_h), PILImage.LANCZOS)

                img_array = np.array(image)

                results = reader.readtext(img_array, detail=1)

                page_text_parts = []
                page_confidences = []
                for (bbox, text, conf) in results:
                    if text.strip():
                        page_text_parts.append(text)
                        page_confidences.append(conf * 100)

                page_text = ' '.join(page_text_parts)
                extracted_text += page_text + "\n"

                if page_confidences:
                    avg_conf = sum(page_confidences) / len(page_confidences)
                    confidence_scores.append(avg_conf)

                del img_array
            except Exception as page_err:
                import traceback
                traceback.print_exc()
            finally:
                del image
                gc.collect()

        overall_confidence = (
            sum(confidence_scores) / len(confidence_scores)
            if confidence_scores else 0
        )

        result_queue.put({
            "success": True,
            "extracted_text": extracted_text,
            "page_count": len(images),
            "pages_extracted": len(images),
            "ocr_confidence": round(overall_confidence, 2)
        })
    except Exception as e:
        result_queue.put({
            "success": False,
            "error": str(e)
        })


class PDFExtractor:
    """
    Hybrid PDF text extractor with automatic OCR fallback for scanned documents

    Features:
    - Primary: PyMuPDF for text-based PDFs (fastest, best font/layout handling)
    - Fallback 1: Tesseract OCR for scanned PDFs (fast, good for Hindi)
    - Fallback 2: EasyOCR for complex Indian languages (slower but more accurate)
    - Auto-detection: Determines if PDF is scanned based on text extraction results
    - Multi-language: Supports 80+ languages including all Indian languages
    - Language detection: Auto-detects document language for optimal OCR
    - Quality detection: Analyzes document quality to route to best OCR engine
    """

    # Threshold: if we extract less than this many chars per page, consider it scanned
    SCANNED_THRESHOLD_CHARS_PER_PAGE = 150

    # Confidence threshold to try EasyOCR after Tesseract
    TESSERACT_CONFIDENCE_THRESHOLD = 60

    # Minimum total extracted text (chars) to consider content sufficient.
    # Below this, OCR is always attempted regardless of chars/page.
    MINIMUM_CONTENT_CHARS = 500

    # Minimum words per page for content to be considered substantive.
    MINIMUM_WORDS_PER_PAGE = 50

    # EasyOCR reader instance (loaded once, reused)
    _easyocr_reader = None
    _easyocr_languages = None  # Track which languages the reader was loaded with

    # Language code mapping for OCR engines
    # Maps langdetect codes to Tesseract and EasyOCR language configurations
    OCR_LANGUAGE_MAP = {
        'hi': {
            'name': 'Hindi',
            'tesseract': 'hin+eng',
            'easyocr': ['hi', 'en'],
            'script': 'Devanagari'
        },
        'kn': {
            'name': 'Kannada',
            'tesseract': 'kan+eng',
            'easyocr': ['kn', 'en'],
            'script': 'Kannada'
        },
        'ta': {
            'name': 'Tamil',
            'tesseract': 'tam+eng',
            'easyocr': ['ta', 'en'],
            'script': 'Tamil'
        },
        'te': {
            'name': 'Telugu',
            'tesseract': 'tel+eng',
            'easyocr': ['te', 'en'],
            'script': 'Telugu'
        },
        'bn': {
            'name': 'Bengali',
            'tesseract': 'ben+eng',
            'easyocr': ['bn', 'en'],
            'script': 'Bengali'
        },
        'gu': {
            'name': 'Gujarati',
            'tesseract': 'guj+eng',
            'easyocr': ['gu', 'en'],
            'script': 'Gujarati'
        },
        'ml': {
            'name': 'Malayalam',
            'tesseract': 'mal+eng',
            'easyocr': ['ml', 'en'],
            'script': 'Malayalam'
        },
        'mr': {
            'name': 'Marathi',
            'tesseract': 'mar+eng',
            'easyocr': ['mr', 'en'],
            'script': 'Devanagari'
        },
        'pa': {
            'name': 'Punjabi',
            'tesseract': 'pan+eng',
            'easyocr': ['pa', 'en'],
            'script': 'Gurmukhi'
        },
        'or': {
            'name': 'Odia',
            'tesseract': 'ori+eng',
            'easyocr': ['bn', 'en'],  # EasyOCR doesn't have Odia, use Bengali (similar script)
            'script': 'Odia'
        },
        'as': {
            'name': 'Assamese',
            'tesseract': 'asm+eng',
            'easyocr': ['as', 'en'],
            'script': 'Bengali'
        },
        'ur': {
            'name': 'Urdu',
            'tesseract': 'urd+eng',
            'easyocr': ['ur', 'en'],
            'script': 'Arabic'
        },
        'sa': {
            'name': 'Sanskrit',
            'tesseract': 'san+eng',
            'easyocr': ['hi', 'en'],  # EasyOCR doesn't have Sanskrit, use Hindi (same Devanagari script)
            'script': 'Devanagari'
        },
        'ne': {
            'name': 'Nepali',
            'tesseract': 'nep+eng',
            'easyocr': ['ne', 'en'],
            'script': 'Devanagari'
        },
        'en': {
            'name': 'English',
            'tesseract': 'eng',
            'easyocr': ['en'],
            'script': 'Latin'
        }
    }

    # Script-to-Language mapping for fallback
    # When language detection fails, use script detection to choose best OCR
    SCRIPT_TO_LANGUAGE_MAP = {
        'Devanagari (Hindi/Marathi/Sanskrit)': 'hi',  # Hindi has best Devanagari support
        'Bengali/Assamese': 'bn',                      # Bengali OCR works for Assamese
        'Kannada': 'kn',
        'Tamil': 'ta',
        'Telugu': 'te',
        'Gujarati': 'gu',
        'Malayalam': 'ml',
        'Gurmukhi (Punjabi)': 'pa',
        'Odia': 'or',
        'Other Indian scripts': 'hi'  # Default to Hindi for unknown scripts
    }

    # Default fallback if language not detected
    DEFAULT_LANGUAGE = 'hi'  # Hindi as default for Indian documents
    
    @classmethod
    def get_easyocr_reader(cls, languages=['hi', 'en']):
        """
        Lazy load EasyOCR reader (loads model into memory once)

        Args:
            languages: List of language codes (e.g., ['hi', 'en'] for Hindi + English)

        Returns:
            EasyOCR Reader instance or None if not available
        """
        if not EASYOCR_AVAILABLE:
            logger.warning("EasyOCR not available. Install: pip install easyocr torch torchvision")
            return None

        # Reload if languages changed
        sorted_langs = sorted(languages)
        if cls._easyocr_reader is not None and cls._easyocr_languages != sorted_langs:
            logger.info(f"EasyOCR language change: {cls._easyocr_languages} -> {sorted_langs}. Reloading...")
            cls._easyocr_reader = None
            import gc
            gc.collect()

        if cls._easyocr_reader is None:
            try:
                logger.info(f"Loading EasyOCR with languages: {languages}")
                # gpu=False for compatibility, set to True if GPU available
                cls._easyocr_reader = easyocr.Reader(languages, gpu=False, verbose=False)
                cls._easyocr_languages = sorted_langs
                logger.info("EasyOCR loaded successfully")
            except Exception as e:
                logger.error(f"Failed to load EasyOCR: {str(e)}")
                return None

        return cls._easyocr_reader

    @staticmethod
    def detect_language(text: str) -> str:
        """
        Detect the primary language of the text using langdetect

        Args:
            text: Text to analyze (should have at least 50 chars for accurate detection)

        Returns:
            Language code (e.g., 'hi', 'en', 'kn', 'ta') or DEFAULT_LANGUAGE if detection fails
        """
        if not LANGDETECT_AVAILABLE:
            logger.warning("langdetect not available, using default language: Hindi")
            return PDFExtractor.DEFAULT_LANGUAGE

        if not text or len(text.strip()) < 20:
            logger.warning(f"Text too short for language detection ({len(text)} chars), using default: Hindi")
            return PDFExtractor.DEFAULT_LANGUAGE

        try:
            # Use first 1000 chars for faster detection
            sample = text[:1000]
            detected_lang = detect(sample)

            # Return the detected language (even if not in our map)
            # Caller will decide whether to use script fallback
            if detected_lang in PDFExtractor.OCR_LANGUAGE_MAP:
                lang_info = PDFExtractor.OCR_LANGUAGE_MAP[detected_lang]
                logger.info(f"🌐 Detected language: {lang_info['name']} ({detected_lang}), Script: {lang_info['script']}")
            else:
                logger.info(f"🌐 Detected language: '{detected_lang}' (not in OCR map, will attempt script fallback)")

            return detected_lang

        except Exception as e:
            logger.warning(f"Language detection failed: {e}, will try script-based detection")
            return PDFExtractor.DEFAULT_LANGUAGE

    @staticmethod
    def detect_language_by_script(text: str) -> str:
        """
        Fallback language detection using script analysis
        When language detection fails or returns unsupported language,
        detect the script and map to best-supported language for that script

        Args:
            text: Text to analyze

        Returns:
            Language code based on detected script
        """
        if not text or len(text.strip()) < 20:
            logger.warning("Text too short for script detection, using default: Hindi")
            return PDFExtractor.DEFAULT_LANGUAGE

        # Use the script detection from ai_tagger
        from app.services.ai_tagger import AITagger
        tagger = AITagger.__new__(AITagger)  # Create instance without __init__
        scripts_found = tagger._detect_indian_scripts(text)

        if not scripts_found:
            logger.info("No Indian scripts detected, using default: Hindi")
            return PDFExtractor.DEFAULT_LANGUAGE

        # Get the most prominent script (highest character count)
        primary_script = max(scripts_found.items(), key=lambda x: x[1])[0]
        char_count = scripts_found[primary_script]

        # Map script to best language
        fallback_lang = PDFExtractor.SCRIPT_TO_LANGUAGE_MAP.get(primary_script, PDFExtractor.DEFAULT_LANGUAGE)

        lang_info = PDFExtractor.OCR_LANGUAGE_MAP.get(fallback_lang)
        logger.info(
            f"📝 Script-based detection: {primary_script} ({char_count} chars) → "
            f"Using {lang_info['name']} OCR"
        )

        return fallback_lang

    # Tesseract OSD script names → our OCR language codes
    OSD_SCRIPT_TO_LANGUAGE = {
        'Devanagari': 'hi',
        'Kannada': 'kn',
        'Tamil': 'ta',
        'Telugu': 'te',
        'Bengali': 'bn',
        'Gujarati': 'gu',
        'Malayalam': 'ml',
        'Gurmukhi': 'pa',
        'Oriya': 'or',    # Tesseract OSD uses "Oriya" not "Odia"
        'Arabic': 'ur',
        'Latin': 'en',
    }

    @staticmethod
    def detect_script_from_image(pdf_bytes: bytes) -> str:
        """
        Detect the script of an image-only PDF by rendering the first page
        and running Tesseract's OSD (Orientation and Script Detection).

        This is used when PyMuPDF extracts 0 text (image-only scanned docs)
        and langdetect has nothing to work with.

        Returns:
            Language code (e.g. 'kn', 'hi', 'ta') or DEFAULT_LANGUAGE on failure
        """
        if not OCR_AVAILABLE or not PYMUPDF_AVAILABLE:
            logger.warning("Cannot detect script from image: OCR or PyMuPDF not available")
            return PDFExtractor.DEFAULT_LANGUAGE

        try:
            # Render just the first page at low DPI for speed
            image = PDFExtractor._render_pdf_page_pymupdf(pdf_bytes, page_num=0, dpi=150)
            if image is None:
                logger.warning("Could not render page for script detection")
                return PDFExtractor.DEFAULT_LANGUAGE

            # Run Tesseract OSD — detects script without needing the right language pack
            osd_output = pytesseract.image_to_osd(image, timeout=30)
            del image
            gc.collect()
            logger.info(f"Tesseract OSD output: {osd_output}")

            # Parse "Script: Kannada" from OSD output
            script_match = re.search(r'Script:\s*(\w+)', osd_output)
            if not script_match:
                logger.warning("Could not parse script from OSD output")
                return PDFExtractor.DEFAULT_LANGUAGE

            detected_script = script_match.group(1)
            confidence_match = re.search(r'Script confidence:\s*([\d.]+)', osd_output)
            script_confidence = float(confidence_match.group(1)) if confidence_match else 0

            # Map OSD script name to our language code
            detected_lang = PDFExtractor.OSD_SCRIPT_TO_LANGUAGE.get(
                detected_script, PDFExtractor.DEFAULT_LANGUAGE
            )

            lang_info = PDFExtractor.OCR_LANGUAGE_MAP.get(detected_lang, {})
            logger.info(
                f"Image script detection: {detected_script} (confidence: {script_confidence}) "
                f"→ {lang_info.get('name', detected_lang)} OCR"
            )

            return detected_lang

        except Exception as e:
            logger.warning(f"Image-based script detection failed: {e}")
            return PDFExtractor.DEFAULT_LANGUAGE

    @staticmethod
    def assess_document_quality(
        text: str,
        page_count: int,
        ocr_confidence: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Assess document quality to determine optimal OCR strategy

        Args:
            text: Extracted text
            page_count: Number of pages in document
            ocr_confidence: OCR confidence score if available

        Returns:
            dict with quality metrics and recommendations
        """
        text_length = len(text.strip())
        chars_per_page = text_length / page_count if page_count > 0 else 0

        # Determine document type
        is_scanned = chars_per_page < PDFExtractor.SCANNED_THRESHOLD_CHARS_PER_PAGE

        # Determine quality tier based on multiple factors
        if not is_scanned:
            # Digital document - high quality
            quality_tier = 'high'
            recommended_engine = 'pymupdf'
        elif ocr_confidence is not None:
            # Scanned document with confidence score
            if ocr_confidence >= 80:
                quality_tier = 'high'
                recommended_engine = 'tesseract'
            elif ocr_confidence >= 60:
                quality_tier = 'medium'
                recommended_engine = 'tesseract'
            else:
                quality_tier = 'low'
                recommended_engine = 'easyocr'
        else:
            # Scanned document without confidence - assume medium
            quality_tier = 'medium'
            recommended_engine = 'tesseract'

        quality_info = {
            'type': 'digital' if not is_scanned else 'scanned',
            'text_density': round(chars_per_page, 2),
            'ocr_confidence': round(ocr_confidence, 2) if ocr_confidence else None,
            'quality_tier': quality_tier,
            'recommended_engine': recommended_engine,
            'is_scanned': is_scanned
        }

        logger.info(
            f"📊 Quality Assessment: Type={quality_info['type']}, "
            f"Density={quality_info['text_density']} chars/page, "
            f"Tier={quality_tier}, Engine={recommended_engine}"
        )

        return quality_info

    @staticmethod
    def _should_attempt_ocr(text: str, pages_extracted: int) -> tuple:
        """
        Determine whether OCR should be attempted based on content quality analysis.

        Goes beyond simple chars-per-page by checking absolute text volume,
        word density, the ratio of substantive lines, and whether the extracted
        text appears to be garbled due to legacy font encoding.

        Legacy Indian PDFs (Krutidev, ISM, etc.) map Devanagari glyphs to
        positions in the Latin Extended Unicode range (U+00A0–U+024F).
        Text extractors read those raw code points as accented Latin characters,
        producing strings like "ºÉÚSÉxÉÉ" instead of real text.
        langdetect then guesses "fr" or "de" from the accented characters,
        and the LLM hallucinates when given the garbage as input.
        Detecting a high ratio of Latin Extended characters is a reliable
        signal that the PDF used a custom font encoding and OCR is needed.

        Returns:
            (should_ocr: bool, reason: str)
        """
        stripped = text.strip()
        text_length = len(stripped)

        if text_length < 200:
            return True, f"very little text ({text_length} chars)"

        # ── Garbled encoding detection ─────────────────────────────────────────
        # Latin Extended range U+00A0–U+024F is almost exclusively used by
        # legacy Indian font encodings when misread by text extractors. A high ratio
        # means the "text" is actually font-mapping garbage, not real content.
        if text_length > 0:
            garbled_chars = sum(
                1 for c in stripped if '\u00a0' <= c <= '\u024f'
            )
            garbled_ratio = garbled_chars / text_length
            if garbled_ratio > 0.25:
                return True, (
                    f"garbled encoding detected "
                    f"({garbled_ratio:.0%} Latin-Extended chars — likely legacy Indian font)"
                )

        avg_chars = text_length / pages_extracted if pages_extracted > 0 else 0
        if avg_chars < PDFExtractor.SCANNED_THRESHOLD_CHARS_PER_PAGE:
            return True, f"low density ({avg_chars:.0f} chars/page)"

        if text_length < PDFExtractor.MINIMUM_CONTENT_CHARS:
            return True, f"below content minimum ({text_length} < {PDFExtractor.MINIMUM_CONTENT_CHARS} chars)"

        lines = [line.strip() for line in stripped.split('\n') if line.strip()]
        if not lines:
            return True, "no text lines found"

        substantive = [l for l in lines if len(l) >= 40]
        substantive_ratio = len(substantive) / len(lines)

        words = stripped.split()
        words_per_page = len(words) / pages_extracted if pages_extracted > 0 else 0

        if words_per_page < PDFExtractor.MINIMUM_WORDS_PER_PAGE and substantive_ratio < 0.3:
            return True, (
                f"sparse content ({words_per_page:.0f} words/page, "
                f"{substantive_ratio:.0%} substantive lines)"
            )

        if words_per_page < 30:
            return True, f"very low word density ({words_per_page:.0f} words/page)"

        return False, "content appears sufficient"

    @staticmethod
    def _finalize_result(
        result: Dict[str, Any],
        primary_title: Optional[str],
        detected_language: str,
        language_name: str,
        detection_method: str,
        page_count: int,
        ocr_confidence: Optional[float] = None
    ):
        """Set common metadata fields on an extraction result."""
        if primary_title and primary_title != "Untitled Document":
            result["title"] = primary_title
        result["detected_language"] = detected_language
        result["language_name"] = language_name
        result["detection_method"] = detection_method
        result["quality_info"] = PDFExtractor.assess_document_quality(
            result.get("extracted_text", ""),
            page_count,
            ocr_confidence
        )

    @staticmethod
    def _render_pdf_page_pymupdf(pdf_bytes: bytes, page_num: int, dpi: int = 300):
        """
        Render a SINGLE PDF page to a PIL Image using PyMuPDF (fitz).

        Processes one page at a time to keep memory usage constant regardless
        of document length. The caller is responsible for freeing the image
        after use.
        """
        if not PYMUPDF_AVAILABLE:
            return None
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            if page_num >= len(doc):
                doc.close()
                return None
            zoom = dpi / 72.0
            mat = fitz.Matrix(zoom, zoom)
            page = doc[page_num]
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img = Image.open(_io.BytesIO(pix.tobytes("png"))).copy()
            pix = None  # Free pixmap immediately
            doc.close()
            return img
        except Exception as e:
            logger.error(f"PyMuPDF rendering page {page_num + 1} failed: {e}")
            return None

    @staticmethod
    def _get_pdf_page_count_pymupdf(pdf_bytes: bytes) -> int:
        """Get total page count using PyMuPDF."""
        if not PYMUPDF_AVAILABLE:
            return 0
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            count = len(doc)
            doc.close()
            return count
        except Exception:
            return 0

    @staticmethod
    def _extract_with_pymupdf_tesseract(
        pdf_bytes: bytes,
        num_pages: int,
        languages: str = "eng",
        detected_language: str = "en",
        dpi: int = 300
    ) -> Dict[str, Any]:
        """
        Extract text using PyMuPDF for page rendering + Tesseract for OCR.

        Used as a last-resort fallback when pdf2image-based paths return 0 chars,
        which happens with eOffice PDFs and other documents that embed images
        using compression formats poppler cannot render.
        """
        fail_result: Dict[str, Any] = {
            "success": False, "error": "",
            "extracted_text": "", "page_count": 0,
            "pages_extracted": 0, "title": "Untitled Document",
            "is_scanned": True, "extraction_method": "pymupdf_tesseract_failed",
            "ocr_confidence": None,
        }

        if not PYMUPDF_AVAILABLE:
            fail_result["error"] = "PyMuPDF not installed"
            return fail_result
        if not OCR_AVAILABLE:
            fail_result["error"] = "Tesseract not installed"
            return fail_result

        lang_name = PDFExtractor.OCR_LANGUAGE_MAP.get(detected_language, {}).get("name", "Unknown")
        logger.info(
            f"🔍 PyMuPDF+Tesseract fallback for {lang_name} "
            f"({languages}) at {dpi} DPI"
        )

        total_pages = PDFExtractor._get_pdf_page_count_pymupdf(pdf_bytes)
        if total_pages == 0:
            fail_result["error"] = "PyMuPDF produced no renderable pages"
            return fail_result

        pages_to_process = min(num_pages, total_pages)
        extracted_text = ""
        confidence_scores = []
        pages_done = 0

        # Process ONE page at a time — never hold more than 1 image in memory
        for idx in range(pages_to_process):
            image = None
            try:
                image = PDFExtractor._render_pdf_page_pymupdf(pdf_bytes, idx, dpi)
                if image is None:
                    logger.warning(f"PyMuPDF+Tesseract page {idx + 1}: render failed, skipping")
                    continue
                image = image.convert("L")
                image = ImageEnhance.Contrast(image).enhance(2.0)
                page_text = pytesseract.image_to_string(
                    image, lang=languages, config="--psm 3 --oem 1",
                    timeout=60
                )
                ocr_data = pytesseract.image_to_data(
                    image, lang=languages, output_type=pytesseract.Output.DICT,
                    timeout=60
                )
                valid_confs = [c for c in ocr_data["conf"] if c > 0]
                if valid_confs:
                    confidence_scores.append(sum(valid_confs) / len(valid_confs))
                extracted_text += page_text + "\n"
                pages_done += 1
                logger.info(
                    f"PyMuPDF+Tesseract page {idx + 1}: "
                    f"{len(page_text)} chars"
                )
            except RuntimeError as timeout_err:
                logger.warning(f"PyMuPDF+Tesseract page {idx + 1} timed out: {timeout_err}")
            except Exception as page_err:
                logger.error(f"PyMuPDF+Tesseract page {idx + 1} error: {page_err}")
            finally:
                del image
                gc.collect()

        extracted_text = PDFExtractor._clean_text_unicode_safe(extracted_text)
        overall_confidence = (
            sum(confidence_scores) / len(confidence_scores)
            if confidence_scores else 0
        )
        title = PDFExtractor._extract_title_from_text(extracted_text)
        logger.info(
            f"✅ PyMuPDF+Tesseract complete: {len(extracted_text)} chars, "
            f"{overall_confidence:.1f}% confidence"
        )
        return {
            "success": True,
            "extracted_text": extracted_text,
            "page_count": pages_to_process,
            "pages_extracted": pages_done,
            "title": title,
            "is_scanned": True,
            "extraction_method": "pymupdf_tesseract",
            "ocr_confidence": round(overall_confidence, 2),
        }

    @staticmethod
    def get_ocr_config(detected_language: str) -> Dict[str, Any]:
        """
        Get optimal OCR configuration for detected language

        Args:
            detected_language: Language code from detect_language()

        Returns:
            dict with tesseract and easyocr configurations
        """
        lang_config = PDFExtractor.OCR_LANGUAGE_MAP.get(
            detected_language,
            PDFExtractor.OCR_LANGUAGE_MAP[PDFExtractor.DEFAULT_LANGUAGE]
        )

        logger.info(
            f"🔧 OCR Config for {lang_config['name']}: "
            f"Tesseract='{lang_config['tesseract']}', "
            f"EasyOCR={lang_config['easyocr']}"
        )

        return lang_config

    @staticmethod
    def extract_text(
        pdf_bytes: bytes,
        num_pages: int = 3,
        ocr_languages: str = None,  # Auto-detected if None
        ocr_dpi: int = 300  # DPI for OCR image conversion (lower = less memory)
    ) -> Dict[str, Any]:
        """
        Extract text from PDF with automatic OCR fallback and language detection

        Args:
            pdf_bytes: PDF file as bytes
            num_pages: Number of pages to extract (default 3)
            ocr_languages: Tesseract language codes (auto-detected if None)

        Returns:
            dict with extracted_text, page_count, title, OCR metadata, detected_language, and quality_info
        """
        try:
            # Step 1: Try PyMuPDF first (fast path, best text extraction)
            primary_result = PDFExtractor._extract_with_pymupdf_text(pdf_bytes, num_pages)

            if not primary_result["success"]:
                logger.warning(f"PyMuPDF extraction failed: {primary_result.get('error')}. No fallback text extractor available.")
                return primary_result

            # Step 2: Analyze extracted content to decide if OCR is needed
            text_length = len(primary_result["extracted_text"].strip())
            pages_extracted = primary_result["pages_extracted"]
            page_count = primary_result["page_count"]
            avg_chars_per_page = text_length / pages_extracted if pages_extracted > 0 else 0

            # PyMuPDF can tell us directly if pages are image-only
            image_only_pages = primary_result.get("image_only_pages", 0)
            if image_only_pages > 0 and pages_extracted > 0:
                image_ratio = image_only_pages / pages_extracted
                if image_ratio > 0.5:
                    logger.info(
                        f"PyMuPDF detected {image_only_pages}/{pages_extracted} image-only pages "
                        f"({image_ratio:.0%}) — OCR likely needed"
                    )

            is_scanned, ocr_trigger_reason = PDFExtractor._should_attempt_ocr(
                primary_result["extracted_text"], pages_extracted
            )

            logger.info(
                f"PyMuPDF extracted {text_length} chars from {pages_extracted} pages "
                f"(avg: {avg_chars_per_page:.1f} chars/page). "
                f"OCR needed: {is_scanned} ({ocr_trigger_reason})"
            )

            # Step 2.5: Intelligent language detection with script-based fallback
            detected_language = PDFExtractor.DEFAULT_LANGUAGE
            detection_method = "default"

            if text_length > 20:
                # First attempt: Language detection
                detected_language = PDFExtractor.detect_language(primary_result["extracted_text"])
                detection_method = "language_detection"

                # If language not in our map, try script-based fallback
                if detected_language not in PDFExtractor.OCR_LANGUAGE_MAP:
                    logger.warning(
                        f"⚠️ Language '{detected_language}' not fully supported. "
                        f"Using script-based fallback..."
                    )
                    detected_language = PDFExtractor.detect_language_by_script(
                        primary_result["extracted_text"]
                    )
                    detection_method = "script_fallback"
            else:
                # No text to detect language from — use image-based script detection
                logger.info(
                    "Text too short for language detection. "
                    "Attempting image-based script detection..."
                )
                detected_language = PDFExtractor.detect_script_from_image(pdf_bytes)
                detection_method = "image_script_detection"

            # Get OCR configuration for detected language
            ocr_config = PDFExtractor.get_ocr_config(detected_language)
            logger.info(f"🎯 Final language choice: {ocr_config['name']} (method: {detection_method})")

            # Override with user-specified languages if provided
            if ocr_languages is None:
                ocr_languages = ocr_config['tesseract']
            else:
                logger.info(f"Using user-specified OCR languages: {ocr_languages}")
            
            # Step 3: If content is sufficient, return PyMuPDF results directly
            if not is_scanned:
                primary_result["is_scanned"] = False
                primary_result["extraction_method"] = "pymupdf"
                primary_result["ocr_confidence"] = None
                PDFExtractor._finalize_result(
                    primary_result, None, detected_language,
                    ocr_config['name'], detection_method, page_count
                )
                return primary_result
            
            # Step 4: OCR fallback — content was insufficient
            logger.info(f"OCR needed ({ocr_trigger_reason}). Attempting OCR extraction...")

            if not OCR_AVAILABLE:
                logger.warning("OCR libraries not available. Install pytesseract, pdf2image, Pillow")
                primary_result["is_scanned"] = True
                primary_result["extraction_method"] = "pymupdf_no_ocr"
                primary_result["ocr_confidence"] = None
                primary_result["error"] = "Document needs OCR but OCR libraries not installed"
                PDFExtractor._finalize_result(
                    primary_result, None, detected_language,
                    ocr_config['name'], detection_method, page_count
                )
                return primary_result

            primary_title = primary_result.get("title", "Untitled Document")
            best_ocr_result = None
            best_ocr_text_len = 0
            tesseract_accepted = False

            # 4a: Tesseract (faster)
            tesseract_result = PDFExtractor._extract_with_ocr(
                pdf_bytes, num_pages, ocr_languages,
                detected_language, dpi=ocr_dpi
            )

            t_conf = 0
            t_len = 0
            tesseract_quality_ok = True
            is_non_latin = ocr_config.get('script', 'Latin') != 'Latin'

            if tesseract_result["success"]:
                t_conf = tesseract_result.get("ocr_confidence", 0)
                t_len = len(tesseract_result.get("extracted_text", "").strip())
                logger.info(f"Tesseract: {t_len} chars, {t_conf}% confidence")

                # Content quality check — high confidence doesn't mean good text
                if t_len > 100:
                    tesseract_quality_ok = not PDFExtractor._is_gibberish(
                        tesseract_result["extracted_text"]
                    )
                    if not tesseract_quality_ok:
                        logger.warning(
                            f"⚠️ Tesseract confidence is {t_conf}% but text "
                            f"quality is poor (gibberish detected). Will try EasyOCR."
                        )

                # Accept Tesseract ONLY if both confidence AND quality pass
                if (t_conf >= PDFExtractor.TESSERACT_CONFIDENCE_THRESHOLD
                        and t_len > 100 and tesseract_quality_ok):
                    best_ocr_result = tesseract_result
                    best_ocr_text_len = t_len
                    tesseract_accepted = True
                    logger.info(f"✅ Tesseract accepted (good confidence: {t_conf}%, quality OK)")
                else:
                    logger.info(
                        f"🔄 Tesseract insufficient (confidence: {t_conf}%, "
                        f"text: {t_len} chars, quality_ok: {tesseract_quality_ok}). "
                        f"Trying EasyOCR..."
                    )
            else:
                logger.warning("🔄 Tesseract failed. Trying EasyOCR...")

            # 4b: EasyOCR — run if Tesseract wasn't good enough, OR if
            # language is non-Latin and Tesseract quality is poor (even if
            # confidence was high). EasyOCR's neural models often handle
            # Devanagari, Bengali, Tamil etc. better than Tesseract.
            run_easyocr = (
                not tesseract_accepted
                or (is_non_latin and not tesseract_quality_ok)
            )
            if run_easyocr and EASYOCR_AVAILABLE:
                easyocr_result = PDFExtractor._extract_with_easyocr(
                    pdf_bytes, num_pages, ocr_config['easyocr'],
                    detected_language, dpi=ocr_dpi
                )

                if easyocr_result["success"]:
                    e_len = len(easyocr_result.get("extracted_text", "").strip())
                    e_conf = easyocr_result.get("ocr_confidence", 0)
                    logger.info(f"EasyOCR: {e_len} chars, {e_conf}% confidence")

                    if not tesseract_result["success"]:
                        best_ocr_result = easyocr_result
                        best_ocr_text_len = e_len
                    elif not tesseract_quality_ok:
                        # Tesseract produced gibberish — strongly prefer EasyOCR
                        # as long as it has any reasonable output
                        easyocr_quality_ok = not PDFExtractor._is_gibberish(
                            easyocr_result["extracted_text"]
                        )
                        if easyocr_quality_ok or e_len > t_len:
                            best_ocr_result = easyocr_result
                            best_ocr_text_len = e_len
                            logger.info(
                                f"EasyOCR chosen over gibberish Tesseract "
                                f"(EasyOCR: {e_len} chars, quality_ok: {easyocr_quality_ok})"
                            )
                        else:
                            best_ocr_result = tesseract_result
                            best_ocr_text_len = t_len
                            logger.warning(
                                f"Both OCR engines produced poor quality. "
                                f"Using Tesseract ({t_len} chars) as fallback."
                            )
                    else:
                        # Both ran, Tesseract quality is OK — pick by volume.
                        # Lower bar for EasyOCR when Tesseract confidence is weak.
                        min_ratio = 0.5 if t_conf < PDFExtractor.TESSERACT_CONFIDENCE_THRESHOLD else 0.8
                        if e_len >= t_len * min_ratio:
                            best_ocr_result = easyocr_result
                            best_ocr_text_len = e_len
                            logger.info(
                                f"EasyOCR chosen ({e_len} chars >= "
                                f"{t_len * min_ratio:.0f} threshold)"
                            )
                        else:
                            best_ocr_result = tesseract_result
                            best_ocr_text_len = t_len
                            logger.info(
                                f"Tesseract chosen despite low confidence "
                                f"({t_len} > {e_len} chars)"
                            )
                else:
                    logger.warning(f"EasyOCR extraction failed: {easyocr_result.get('error', 'unknown error')}")
            elif run_easyocr:
                logger.warning(
                    "❌ EasyOCR not available — needed for "
                    + ("non-Latin script quality comparison" if is_non_latin else "low Tesseract confidence")
                )

            # 4c: Last-resort — use Tesseract even if below threshold
            if best_ocr_result is None and tesseract_result["success"] and t_len > 0:
                best_ocr_result = tesseract_result
                best_ocr_text_len = t_len
                logger.info(f"Using Tesseract as last-resort fallback ({t_len} chars)")

            # 4d: PyMuPDF fallback — fires when pdf2image-based paths all returned 0 chars.
            # This catches PDFs where poppler silently produces blank frames
            # (eOffice embedded images, JBIG2/CCITT compression, unusual XObjects).
            if best_ocr_text_len == 0:
                logger.info(
                    "⚠️ All pdf2image-based OCR paths returned 0 chars. "
                    "Trying PyMuPDF renderer as fallback..."
                )
                pymupdf_result = PDFExtractor._extract_with_pymupdf_tesseract(
                    pdf_bytes, num_pages, ocr_languages,
                    detected_language, dpi=ocr_dpi
                )
                if pymupdf_result["success"]:
                    pm_len = len(pymupdf_result.get("extracted_text", "").strip())
                    logger.info(f"PyMuPDF+Tesseract extracted {pm_len} chars")
                    if pm_len > 0:
                        best_ocr_result = pymupdf_result
                        best_ocr_text_len = pm_len
                else:
                    logger.warning(f"PyMuPDF fallback failed: {pymupdf_result.get('error')}")

            # Step 5: Pick whichever result extracted more content
            if best_ocr_result and best_ocr_text_len >= text_length:
                best_ocr_result["is_scanned"] = True
                PDFExtractor._finalize_result(
                    best_ocr_result, primary_title, detected_language,
                    ocr_config['name'], detection_method, page_count,
                    best_ocr_result.get("ocr_confidence")
                )
                logger.info(
                    f"✅ Using OCR ({best_ocr_text_len} chars, "
                    f"method: {best_ocr_result.get('extraction_method', '?')}) "
                    f"over PyMuPDF ({text_length} chars)"
                )
                return best_ocr_result

            # OCR didn't improve on PyMuPDF — fall back to digital extraction
            if best_ocr_result:
                logger.warning(
                    f"⚠️ OCR ({best_ocr_text_len} chars) didn't surpass "
                    f"PyMuPDF ({text_length} chars), preferring PyMuPDF"
                )
            else:
                logger.warning("All OCR methods failed, falling back to PyMuPDF")

            primary_result["is_scanned"] = True
            primary_result["extraction_method"] = "pymupdf_ocr_insufficient"
            primary_result["ocr_confidence"] = None
            PDFExtractor._finalize_result(
                primary_result, None, detected_language,
                ocr_config['name'], detection_method, page_count
            )
            return primary_result
            
        except Exception as e:
            logger.error(f"Error in extract_text: {str(e)}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "extracted_text": "",
                "page_count": 0,
                "pages_extracted": 0,
                "title": "Untitled Document",
                "is_scanned": None,
                "extraction_method": "failed",
                "ocr_confidence": None
            }
    
    @staticmethod
    def _extract_with_pymupdf_text(pdf_bytes: bytes, num_pages: int) -> Dict[str, Any]:
        """
        Primary text extractor using PyMuPDF (fitz).

        Advantages over PyPDF2:
        - Superior font handling (CID, embedded, ligatures, Unicode)
        - Preserves reading order and layout structure
        - Handles encrypted/damaged PDFs more gracefully
        - Extracts richer metadata (TOC, bookmarks)
        - 3-5x faster in benchmarks
        - Can detect image-only pages natively
        """
        if not PYMUPDF_AVAILABLE:
            return {
                "success": False,
                "error": "PyMuPDF not installed",
                "extracted_text": "",
                "page_count": 0,
                "pages_extracted": 0,
                "title": "Untitled Document"
            }

        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            page_count = len(doc)
            pages_to_extract = min(num_pages, page_count)

            extracted_text = ""
            image_only_pages = 0

            for i in range(pages_to_extract):
                page = doc[i]

                # Extract text preserving layout and reading order
                page_text = page.get_text("text")

                if page_text and page_text.strip():
                    extracted_text += page_text + "\n"
                else:
                    # Page has no extractable text — likely scanned/image-only
                    image_only_pages += 1

            # Check if text looks corrupted (legacy Indian font encodings)
            is_likely_corrupted = PDFExtractor._is_text_corrupted(extracted_text)

            if is_likely_corrupted:
                logger.warning("Detected corrupted/wrong encoding in PyMuPDF extraction")
                doc.close()
                return {
                    "success": True,
                    "extracted_text": "",  # Empty to trigger OCR
                    "page_count": page_count,
                    "pages_extracted": 0,  # Zero to trigger OCR fallback
                    "title": "Untitled Document",
                    "image_only_pages": pages_to_extract
                }

            # Extract metadata — PyMuPDF provides richer metadata than PyPDF2
            title = PDFExtractor._extract_title_from_pymupdf(doc, extracted_text)

            # Extract table of contents if available (useful for structure understanding)
            toc = doc.get_toc(simple=True)  # [[level, title, page_num], ...]
            toc_entries = [entry[1] for entry in toc[:20]] if toc else []

            doc.close()

            return {
                "success": True,
                "extracted_text": extracted_text,
                "page_count": page_count,
                "pages_extracted": pages_to_extract,
                "title": title,
                "image_only_pages": image_only_pages,
                "toc_entries": toc_entries
            }

        except Exception as e:
            logger.error(f"PyMuPDF text extraction failed: {str(e)}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "extracted_text": "",
                "page_count": 0,
                "pages_extracted": 0,
                "title": "Untitled Document"
            }

    @staticmethod
    def _extract_title_from_pymupdf(doc, extracted_text: str) -> str:
        """
        Extract document title using PyMuPDF's rich metadata.
        Falls back to text-based extraction if metadata is empty.
        """
        # Try PDF metadata first
        metadata = doc.metadata
        if metadata:
            meta_title = metadata.get("title", "")
            if meta_title and meta_title.strip():
                title = meta_title.strip()
                if title.lower() not in ('untitled', 'document', 'untitled document', 'microsoft word'):
                    return title

        # Try first TOC entry as title
        toc = doc.get_toc(simple=True)
        if toc and toc[0][1].strip():
            first_entry = toc[0][1].strip()
            if 10 <= len(first_entry) <= 100:
                return first_entry

        # Fall back to text-based extraction
        return PDFExtractor._extract_title_from_text(extracted_text)
    
    @staticmethod
    def _extract_with_ocr(
        pdf_bytes: bytes,
        num_pages: int,
        languages: str = "hin+eng",
        detected_language: str = "hi",
        dpi: int = 300
    ) -> Dict[str, Any]:
        """
        Extract text using Tesseract OCR (slower, for scanned PDFs)

        Args:
            pdf_bytes: PDF file as bytes
            num_pages: Number of pages to extract
            languages: Tesseract language codes
            detected_language: Detected language code for logging
            dpi: DPI for image conversion (lower = less memory)

        Returns:
            dict with extracted_text and OCR metadata
        """
        try:
            lang_name = PDFExtractor.OCR_LANGUAGE_MAP.get(detected_language, {}).get('name', 'Unknown')
            logger.info(f"Starting Tesseract OCR for {lang_name} with languages: {languages} at {dpi} DPI")

            # OCR one page at a time — constant memory regardless of page count
            extracted_text = ""
            confidence_scores = []
            pages_done = 0

            for page_idx in range(num_pages):
                image = None
                try:
                    # Convert single page to image
                    page_images = convert_from_bytes(
                        pdf_bytes,
                        first_page=page_idx + 1,
                        last_page=page_idx + 1,
                        dpi=dpi
                    )
                    if not page_images:
                        continue
                    image = page_images[0]
                    del page_images

                    logger.info(f"Processing page {page_idx + 1}/{num_pages} with OCR...")

                    # Preprocess: grayscale + contrast
                    try:
                        image = image.convert('L')
                        image = ImageEnhance.Contrast(image).enhance(2.0)
                    except Exception as prep_error:
                        logger.warning(f"Image preprocessing failed: {prep_error}, using original")

                    # OCR
                    page_text = pytesseract.image_to_string(
                        image,
                        lang=languages,
                        config='--psm 3 --oem 1',
                        timeout=60
                    )

                    ocr_data = pytesseract.image_to_data(
                        image,
                        lang=languages,
                        output_type=pytesseract.Output.DICT,
                        timeout=60
                    )

                    valid_confidences = [c for c in ocr_data['conf'] if c > 0]
                    if valid_confidences:
                        avg_confidence = sum(valid_confidences) / len(valid_confidences)
                        confidence_scores.append(avg_confidence)

                    extracted_text += page_text + "\n"
                    pages_done += 1
                    logger.info(f"OCR page {page_idx + 1}: {len(page_text)} chars")

                except RuntimeError as timeout_err:
                    logger.warning(f"OCR page {page_idx + 1} timed out (60s): {timeout_err}")
                except Exception as page_error:
                    logger.error(f"Error OCR'ing page {page_idx + 1}: {str(page_error)}")
                finally:
                    del image
                    gc.collect()

            # Light cleaning - preserve Hindi characters
            extracted_text = PDFExtractor._clean_text_unicode_safe(extracted_text)

            # Check for gibberish in OCR output
            if PDFExtractor._is_gibberish(extracted_text):
                logger.warning("⚠️ Detected gibberish in Tesseract OCR output. Quality may be poor.")

            overall_confidence = (
                sum(confidence_scores) / len(confidence_scores)
                if confidence_scores else 0
            )

            title = PDFExtractor._extract_title_from_text(extracted_text)

            logger.info(f"OCR extraction complete. Confidence: {overall_confidence:.1f}%")
            logger.info(f"Extracted text length: {len(extracted_text)} chars")

            return {
                "success": True,
                "extracted_text": extracted_text,
                "page_count": num_pages,
                "pages_extracted": pages_done,
                "title": title,
                "is_scanned": True,
                "extraction_method": "tesseract_ocr",
                "ocr_confidence": round(overall_confidence, 2)
            }
            
        except Exception as e:
            logger.error(f"OCR extraction failed: {str(e)}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "extracted_text": "",
                "page_count": 0,
                "pages_extracted": 0,
                "title": "Untitled Document",
                "is_scanned": True,
                "extraction_method": "ocr_failed",
                "ocr_confidence": None
            }
    
    @staticmethod
    def _extract_with_easyocr(
        pdf_bytes: bytes,
        num_pages: int,
        languages: list = None,
        detected_language: str = "hi",
        dpi: int = 300
    ) -> Dict[str, Any]:
        """
        Extract text using EasyOCR in an isolated subprocess.

        Runs in a separate process so that if EasyOCR/PyTorch causes an OOM,
        only the subprocess dies — the main server and batch job survive.

        Args:
            pdf_bytes: PDF file as bytes
            num_pages: Number of pages to extract
            languages: List of language codes for EasyOCR (e.g., ['hi', 'en'])
            detected_language: Detected language code for logging
            dpi: DPI for image conversion (lower = less memory)

        Returns:
            dict with extracted_text and OCR metadata
        """
        fail_result = {
            "success": False,
            "error": "",
            "extracted_text": "",
            "page_count": 0,
            "pages_extracted": 0,
            "title": "Untitled Document",
            "is_scanned": True,
            "extraction_method": "easyocr_failed",
            "ocr_confidence": None
        }

        if not EASYOCR_AVAILABLE:
            fail_result["error"] = "EasyOCR not available"
            return fail_result

        try:
            if languages is None:
                languages = ['hi', 'en']

            lang_name = PDFExtractor.OCR_LANGUAGE_MAP.get(detected_language, {}).get('name', 'Unknown')
            logger.info(
                f"Starting EasyOCR extraction for {lang_name} with languages: {languages} "
                f"at {dpi} DPI (subprocess-isolated, max {EASYOCR_MAX_DIMENSION}px)"
            )

            # Run EasyOCR in a subprocess to isolate OOM risk
            result_queue = multiprocessing.Queue()
            process = multiprocessing.Process(
                target=_easyocr_subprocess_worker,
                args=(pdf_bytes, num_pages, languages, dpi, EASYOCR_MAX_DIMENSION, result_queue),
                daemon=True
            )
            process.start()

            # Wait up to 120 seconds for EasyOCR to finish
            process.join(timeout=120)

            if process.is_alive():
                # Timed out — kill the subprocess
                logger.warning("EasyOCR subprocess timed out after 120s. Killing it.")
                process.kill()
                process.join(timeout=5)
                fail_result["error"] = "EasyOCR timed out (120s limit)"
                return fail_result

            if process.exitcode != 0:
                # Subprocess was killed (OOM = signal 9 → exitcode -9 or 137)
                exit_reason = "OOM killed" if process.exitcode in (-9, 137, -137) else f"exit code {process.exitcode}"
                logger.warning(f"EasyOCR subprocess died ({exit_reason}). Skipping this document.")
                fail_result["error"] = f"EasyOCR subprocess crashed ({exit_reason}). Document too large for OCR."
                return fail_result

            # Get result from subprocess
            try:
                sub_result = result_queue.get_nowait()
            except Exception:
                fail_result["error"] = "EasyOCR subprocess returned no result"
                return fail_result

            if not sub_result.get("success"):
                fail_result["error"] = sub_result.get("error", "Unknown EasyOCR error")
                return fail_result

            # Process the successful result
            extracted_text = sub_result.get("extracted_text", "")

            # Clean text (preserve Unicode for Indian languages)
            extracted_text = PDFExtractor._clean_text_unicode_safe(extracted_text)

            # Check for gibberish
            if PDFExtractor._is_gibberish(extracted_text):
                logger.warning("Detected gibberish in EasyOCR output. Document may have very poor scan quality.")

            title = PDFExtractor._extract_title_from_text(extracted_text)
            overall_confidence = sub_result.get("ocr_confidence", 0)

            logger.info(
                f"EasyOCR extraction complete. Extracted {len(extracted_text)} chars, "
                f"confidence: {overall_confidence:.1f}%"
            )

            return {
                "success": True,
                "extracted_text": extracted_text,
                "page_count": sub_result.get("page_count", 0),
                "pages_extracted": sub_result.get("pages_extracted", 0),
                "title": title,
                "is_scanned": True,
                "extraction_method": "easyocr",
                "ocr_confidence": overall_confidence
            }

        except Exception as e:
            logger.error(f"EasyOCR extraction failed: {str(e)}", exc_info=True)
            fail_result["error"] = str(e)
            return fail_result
    
    @staticmethod
    def _extract_title(doc_or_metadata, extracted_text: str) -> str:
        """Extract title from metadata or content. Works with PyMuPDF doc or metadata dict."""
        metadata = None
        if hasattr(doc_or_metadata, 'metadata'):
            metadata = doc_or_metadata.metadata
        elif isinstance(doc_or_metadata, dict):
            metadata = doc_or_metadata

        if metadata:
            # PyMuPDF uses lowercase keys; handle both styles
            meta_title = metadata.get('title') or metadata.get('/Title')
            if meta_title and str(meta_title).strip():
                title = str(meta_title).strip()
                if title.lower() not in ('untitled', 'document', 'untitled document', 'microsoft word'):
                    return title

        return PDFExtractor._extract_title_from_text(extracted_text)
    
    @staticmethod
    def _extract_title_from_text(text: str) -> str:
        """Extract title from first few lines of text"""
        if text:
            lines = [line.strip() for line in text.split('\n') if line.strip()]
            for line in lines[:5]:  # Check first 5 non-empty lines
                # Look for lines that might be titles (length between 10-100 chars)
                if 10 <= len(line) <= 100:
                    return line
        
        return "Untitled Document"
    
    @staticmethod
    def _clean_text_unicode_safe(text: str) -> str:
        """
        Clean extracted text while preserving Unicode characters (Hindi/Devanagari)
        """
        # Normalize whitespace
        text = re.sub(r'[ \t]+', ' ', text)  # Multiple spaces/tabs to single space
        text = re.sub(r'\n\n+', '\n', text)  # Multiple newlines to single
        
        # Remove only truly problematic characters, keep Devanagari (U+0900-U+097F)
        # Keep: Latin, Devanagari, numbers, basic punctuation
        # Remove: Control characters, weird symbols
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
        
        # Limit length (keep first 2500 words for better context)
        words = text.split()
        if len(words) > 2500:
            text = ' '.join(words[:2500])
        
        return text.strip()
    
    @staticmethod
    def _is_gibberish(text: str) -> bool:
        """
        Detect if extracted text is gibberish/nonsensical.

        Language-aware: skips Latin-only heuristics (vowel ratio, consonant
        clusters) when the text is primarily non-Latin (Devanagari, Bengali,
        Tamil, etc.) and uses a script-appropriate quality check instead.
        """
        if not text or len(text) < 20:
            return False

        sample = text[:1000]

        # --- Detect dominant script ---
        non_latin_alpha = sum(1 for c in sample if ord(c) > 0x024F and c.isalpha())
        latin_alpha = sum(1 for c in sample if c.isascii() and c.isalpha())

        if non_latin_alpha > latin_alpha:
            # Text is primarily non-Latin — Latin vowel/consonant checks
            # are meaningless here.  Instead check whether the text has a
            # reasonable ratio of actual script characters vs noise
            # (digits, punctuation, control chars, replacement chars).
            alpha_chars = sum(1 for c in sample if c.isalpha())
            total_non_space = sum(1 for c in sample if not c.isspace())
            if total_non_space > 50:
                alpha_ratio = alpha_chars / total_non_space
                if alpha_ratio < 0.30:
                    logger.warning(
                        f"Non-Latin gibberish: only {alpha_ratio:.0%} alphabetic "
                        f"chars (non-Latin={non_latin_alpha}, latin={latin_alpha})"
                    )
                    return True
            # Non-Latin text that passes the alpha-ratio check is accepted
            return False

        # --- Latin-dominant text: original English-centric checks ---
        sample_lower = sample.lower()

        # 1. Vowel ratio — English text is ~35-45% vowels
        vowels = sum(1 for c in sample_lower if c in 'aeiou')
        letters = sum(1 for c in sample_lower if c.isalpha())
        if letters > 50:
            vowel_ratio = vowels / letters
            if vowel_ratio < 0.20:
                logger.warning(f"Detected gibberish: vowel ratio too low ({vowel_ratio:.2%})")
                return True

        # 2. Excessive consonant clusters (4+ Latin consonants in a row)
        # Note: 3-letter clusters like "str", "rnm", "nts" are common in
        # English (ministry, government, instruments). Only flag 4+ which
        # are rare in real words but common in OCR garbage.
        consonant_clusters = re.findall(r'[bcdfghjklmnpqrstvwxyz]{4,}', sample_lower)
        words_in_sample = len(sample_lower.split())
        if words_in_sample > 20 and len(consonant_clusters) / words_in_sample > 0.15:
            logger.warning(
                f"Detected gibberish: {len(consonant_clusters)} long consonant "
                f"clusters in {words_in_sample} words ({len(consonant_clusters)/words_in_sample:.0%}): "
                f"{consonant_clusters[:5]}"
            )
            return True

        # 3. Pronounceability — most English words contain a vowel
        words = re.findall(r'\b[a-z]{3,}\b', sample_lower)
        if len(words) > 20:
            pronounceable = sum(1 for word in words if any(v in word for v in 'aeiou'))
            pronounceable_ratio = pronounceable / len(words)
            if pronounceable_ratio < 0.60:
                logger.warning(f"Detected gibberish: only {pronounceable_ratio:.2%} pronounceable words")
                return True

        return False
    
    @staticmethod
    def _is_text_corrupted(text: str) -> bool:
        """
        Detect if extracted text is corrupted/wrong encoding
        
        Specifically detects:
        1. Krutidev/legacy Hindi fonts (common in government docs)
        2. Wrong character encoding
        3. Mixed garbage characters
        """
        if not text or len(text) < 50:
            return False
        
        # Sample first 1000 chars for better detection
        sample = text[:1000]
        
        # KRUTIDEV DETECTION - This is the main issue!
        # Krutidev fonts use specific ASCII patterns for Hindi
        # Common Krutidev characters: k, [k, jk, ns, esa, ds, etc.
        krutidev_patterns = [
            'lkekftd',  # सामाजिक in Krutidev
            'iQjojh',   # फरवरी in Krutidev  
            'lans\'k',  # संदेश in Krutidev
            'jfonkl',   # रविदास in Krutidev
            'U;k;',     # न्याय in Krutidev
            'lar',      # संत in Krutidev
            'xka/kh',   # गांधी in Krutidev
            'Hkkjr',    # भारत in Krutidev
            'ea=ky;',   # मंत्रालय in Krutidev
        ]
        
        # If we find ANY Krutidev pattern, it's corrupted
        for pattern in krutidev_patterns:
            if pattern in sample:
                logger.warning(f"Detected Krutidev encoding pattern: '{pattern}'")
                return True
        
        # Additional check: lots of special chars like @ {} [] 
        special_char_count = sum(1 for c in sample if c in '@#$%^&*~`|\\{}[]')
        if len(sample) > 0 and (special_char_count / len(sample)) > 0.05:
            logger.info(f"Detected high special character ratio: {special_char_count}/{len(sample)}")
            return True
        
        # Check for patterns of lowercase consonants with diacritics (Krutidev style)
        # Krutidev uses patterns like: dk, dks, dh, nh, etc.
        krutidev_style_patterns = 0
        for i in range(len(sample) - 1):
            if sample[i:i+2] in ['dk', 'dh', 'ds', 'nh', 'fk', 'jk', 'uk', 'vk', 'lk']:
                krutidev_style_patterns += 1
        
        if len(sample) > 0 and (krutidev_style_patterns / len(sample)) > 0.02:
            logger.warning(f"Detected Krutidev-style patterns: {krutidev_style_patterns}")
            return True
        
        return False
    
    @staticmethod
    def get_pdf_info(pdf_bytes: bytes) -> Dict[str, Any]:
        """
        Get PDF metadata without extracting full text using PyMuPDF.

        Returns richer metadata than PyPDF2 including TOC/bookmarks.

        Args:
            pdf_bytes: PDF file as bytes

        Returns:
            dict with PDF metadata
        """
        if not PYMUPDF_AVAILABLE:
            return {"success": False, "error": "PyMuPDF not installed"}

        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")

            metadata = {}
            if doc.metadata:
                for key, value in doc.metadata.items():
                    if value:
                        metadata[key] = str(value)

            # Extract TOC if available
            toc = doc.get_toc(simple=True)
            toc_entries = [{"level": e[0], "title": e[1], "page": e[2]} for e in toc[:30]] if toc else []

            page_count = len(doc)
            doc.close()

            return {
                "success": True,
                "page_count": page_count,
                "metadata": metadata,
                "toc": toc_entries
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
