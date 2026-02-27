# Services module
from . import pdf_extractor, ai_tagger, file_handler, csv_processor

try:
    from . import redis_client
except ImportError:
    pass  # redis not installed (optional dependency)

