import openai
import json
from typing import List, Dict, Any, Optional, Set
import re
import logging
import unicodedata
import time

from app.config import settings

logger = logging.getLogger(__name__)


class AITagger:
    """Generate tags using OpenRouter API"""
    
    # Models that are known to NOT work for tagging
    UNSUPPORTED_MODELS = [
        'deepseek-r1',  # Reasoning models
        'deepseek-reasoner',
        'o1-',  # OpenAI reasoning models
        'qwen-vl',  # Vision-language models
        'qwen-2.5-vl',
    ]

    # Single-token tags that are too generic to help retrieval.
    GENERIC_SINGLE_TAGS = {
        'address', 'contact', 'data', 'department', 'details', 'development', 'document', 'email',
        'file', 'foundation', 'government', 'hindi', 'india', 'information', 'language', 'ministry',
        'newsletter', 'office', 'organization', 'pdf', 'phone', 'policy', 'program', 'publication',
        'report', 'scheme', 'services', 'status', 'welfare',
        # Procedural/structural terms
        'tender', 'bid', 'quotation', 'proposal', 'submission', 'opening', 'closing', 'deadline',
        'notice', 'circular', 'notification', 'order', 'memo', 'letter', 'form', 'application',
        # Amount/quantity terms
        'amount', 'crore', 'lakh', 'lakhs', 'rupees', 'rs', 'inr', 'budget', 'cost', 'price',
        # Generic time terms
        'date', 'period', 'year', 'month', 'day', 'time', 'duration',
        # Generic action terms
        'process', 'procedure', 'method', 'system', 'format', 'type', 'category', 'section',
    }

    # Generic components that should not form an entire tag by themselves.
    GENERIC_COMPONENT_TAGS = {
        'address', 'annual', 'board', 'budget', 'committee', 'contact', 'data', 'department',
        'details', 'development', 'document', 'email', 'file', 'financial', 'foundation',
        'government', 'india', 'information', 'language', 'legal', 'members', 'ministry',
        'newsletter', 'office', 'organization', 'pdf', 'phone', 'policy', 'program',
        'publication', 'reform', 'report', 'resources', 'roles', 'scheme', 'services',
        'social', 'status', 'welfare',
        # Procedural components
        'tender', 'bid', 'opening', 'closing', 'submission', 'notice', 'box', 'form',
        'quotation', 'proposal', 'invitation', 'enquiry', 'requirements', 'conditions',
        # Amount components  
        'amount', 'cost', 'price', 'value', 'total', 'deposit', 'fee', 'charges',
        # Generic descriptors
        'general', 'basic', 'standard', 'normal', 'regular', 'common', 'main', 'other',
    }
    
    # Roman numeral pattern — document structure artifacts (Chapter I, Section XXI etc.)
    # Full regex covering i–mmmcmxcix so roman-numeral-only tags are always rejected.
    _ROMAN_RE = re.compile(
        r'^m{0,4}(?:cm|cd|d?c{0,3})(?:xc|xl|l?x{0,3})(?:ix|iv|v?i{0,3})$',
        re.IGNORECASE
    )

    # Minimal universal noise set — only terms that are ALWAYS meaningless regardless
    # of document type. Keep this list as small as possible; the LLM prompt handles
    # the rest. Do NOT add domain-specific terms here.
    _MINIMAL_GENERIC_TERMS = frozenset({
        'contact', 'email', 'phone', 'address',
        'document', 'information', 'data', 'details', 'pdf', 'report',
        'government', 'india', 'language', 'publication',
        'contact details', 'contact information',
        'phone number', 'email address',
    })

    # Patterns that indicate low-value procedural tags (compiled for performance)
    LOW_VALUE_PATTERNS = [
        # Tender/bid procedural terms
        re.compile(r'^(?:tender|bid|quotation)[-\s]?(?:opening|closing|submission|notice|box|form|document|details|number|no|id)$', re.I),
        re.compile(r'^(?:opening|closing|submission)[-\s]?(?:date|time|deadline|period)$', re.I),
        # Generic deadline/date patterns without specific context
        re.compile(r'^deadline[-\s]?\d+$', re.I),  # deadline-22, deadline-15
        re.compile(r'^date[-\s]?\d+$', re.I),
        # Amount patterns without context
        re.compile(r'^\d+[-\s]?(?:crore|lakh|lakhs|rupees|rs)s?$', re.I),
        re.compile(r'^(?:crore|lakh|lakhs)s?[-\s]?\d*$', re.I),
        # Security/deposit generic terms
        re.compile(r'^(?:security|earnest|emd)[-\s]?(?:deposit|money|amount)$', re.I),
        # Generic document terms
        re.compile(r'^(?:annexure|appendix|attachment|enclosure)[-\s]?[a-z0-9]?$', re.I),
        # Investment/financial generic
        re.compile(r'^(?:investment|fixed)[-\s]?(?:tender|deposit|amount)$', re.I),
        # Generic notice types
        re.compile(r'^(?:tender|bid|public|general)[-\s]?notice$', re.I),
        # AI-INVENTED PLACEHOLDER PATTERNS (critical - AI outputs these)
        re.compile(r'^(?:unique|specific|generic|sample|example)[-\s]?(?:identifier|name|entity|tag|item)[-\s]?\d*$', re.I),
        re.compile(r'^(?:identifier|entity|item|tag)[-\s]?\d+$', re.I),  # identifier-001, entity-002
        re.compile(r'^(?:organization|scheme|program|policy|document)[-\s]?(?:name|type|id)$', re.I),
        re.compile(r'^(?:fiscal|financial|calendar)[-\s]?year$', re.I),
        re.compile(r'^(?:reference|ref|file)[-\s]?(?:number|no|id)$', re.I),
        re.compile(r'^(?:time|date)[-\s]?(?:period|range)$', re.I),
        re.compile(r'^(?:achievement|performance|specific)[-\s]?metrics?$', re.I),
        re.compile(r'^(?:legal|official|specific)[-\s]?notifications?$', re.I),
    ]

    # Minimal stopwords list for keyword extraction and overlap scoring.
    KEYWORD_STOPWORDS = {
        'a', 'an', 'and', 'are', 'as', 'at', 'be', 'by', 'for', 'from', 'in', 'into', 'is',
        'it', 'of', 'on', 'or', 'that', 'the', 'this', 'to', 'with', 'without',
        'about', 'after', 'before', 'between', 'during', 'under', 'over',
        'act', 'rule', 'rules', 'section', 'clause', 'article', 'document',
    }
    
    def __init__(self, api_key: str, model_name: str = "openai/gpt-4o-mini", exclusion_words: Optional[List[str]] = None):
        self.api_key = api_key
        self.model_name = model_name
        self.exclusion_words: Set[str] = set(word.lower().strip() for word in (exclusion_words or []))
        
        # Warn about unsupported models
        model_lower = model_name.lower()
        for unsupported in self.UNSUPPORTED_MODELS:
            if unsupported in model_lower:
                logger.warning(
                    f"⚠️ WARNING: Model '{model_name}' is likely incompatible for tagging tasks. "
                    f"Reasoning/vision models often return empty responses. "
                    f"Recommended: google/gemini-flash-1.5, openai/gpt-4o-mini, anthropic/claude-3-haiku"
                )
                break
        
        # Initialize OpenAI client with timeout and retry configuration
        # Use httpx.Timeout with all four parameters (timeout applies to read)
        import httpx
        
        self.client = openai.OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
            timeout=httpx.Timeout(
                timeout=settings.api_read_timeout,
                connect=settings.api_connect_timeout,
            ),
            max_retries=settings.api_max_retries,
        )
        
        # Adaptive rate limit state
        self._rate_limit_delay = settings.api_retry_delay
        self._last_rate_limit_time = 0
        self._rate_limit_hit_count = 0
        self._consecutive_successes = 0  # Track successes for delay decay
        
        # Track if model doesn't support system messages
        self._no_system_message = False
    
    def generate_tags(
        self,
        title: str,
        description: str,
        content: str,
        num_tags: int = 8,
        detected_language: Optional[str] = None,
        language_name: Optional[str] = None,
        quality_info: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Generate tags for document with exclusion filtering and language awareness

        Args:
            title: Document title
            description: Document description
            content: Extracted text content
            num_tags: Number of tags to generate (exact number will be returned after filtering)
            detected_language: Language code (e.g., 'hi', 'en', 'kn', 'ta')
            language_name: Full language name (e.g., 'Hindi', 'English', 'Kannada')
            quality_info: Document quality metrics from PDF extractor

        Returns:
            dict with tags list and metadata
        """
        try:
            # Skip API call if content is empty
            if not content or len(content.strip()) < 50:
                logger.warning("Content too short or empty, skipping API call")
                return {
                    "success": False,
                    "error": "Insufficient text content for tag generation",
                    "tags": []
                }

            if language_name:
                logger.info(f"🌐 Document language: {language_name} ({detected_language})")
            if quality_info:
                logger.info(f"📊 Document quality: {quality_info.get('quality_tier', 'unknown')} ({quality_info.get('type', 'unknown')})")

            # Cap how many tags we ask for based on content length.
            # One tag per ~8 words is generous; prevents hallucination on short content.
            content_words = len(content.split()) if content else 0
            max_derivable = max(num_tags, content_words // 8) if content_words > 0 else num_tags * 2

            # Small buffer: ask for a bit more than needed to absorb exclusion filtering,
            # but never so many that the LLM has to hallucinate to fill the quota.
            buffer = min(num_tags + 6, max_derivable)

            all_collected_tags: List[str] = []
            total_tokens_used = 0
            max_attempts = 2  # Tiered JSON is high quality; rarely needs a retry

            for attempt in range(max_attempts):
                tags_still_needed = num_tags - len(all_collected_tags)
                if tags_still_needed <= 0:
                    break

                requested_tags = min(tags_still_needed + 6, buffer)
                logger.info(
                    f"🎯 Attempt {attempt + 1}/{max_attempts}: need {tags_still_needed}, "
                    f"requesting {requested_tags} (content: {content_words} words, "
                    f"exclusions: {len(self.exclusion_words)})"
                )

                already = list(set(all_collected_tags)) if attempt > 0 else None
                prompt = self._build_prompt(
                    title, description, content, requested_tags,
                    detected_language, language_name, quality_info,
                    already_generated=already
                )

                # Rate-limit backoff
                current_time = time.time()
                if current_time - self._last_rate_limit_time < self._rate_limit_delay:
                    wait_time = self._rate_limit_delay - (current_time - self._last_rate_limit_time)
                    logger.info(f"⏳ Rate limit backoff: waiting {wait_time:.2f}s")
                    time.sleep(wait_time)

                system_content = (
                    "You are a document search-tagging expert. "
                    "Your job is to identify the most specific, identifying terms in a document "
                    "so that a user can find it via search. "
                    "Always respond with valid JSON only — no prose, no markdown fences."
                )
                
                try:
                    # Build messages - skip system message if model doesn't support it
                    if self._no_system_message:
                        # Merge system instructions into user prompt
                        user_prompt = f"""{system_content}

{prompt}"""
                        messages = [{"role": "user", "content": user_prompt}]
                    else:
                        messages = [
                            {"role": "system", "content": system_content},
                            {"role": "user", "content": prompt}
                        ]
                    
                    response = self.client.chat.completions.create(
                        model=self.model_name,
                        messages=messages,
                        max_tokens=700,
                        temperature=0.2 + (attempt * 0.1)
                    )
                    last_response = response
                except openai.BadRequestError as e:
                    # Check if it's the "developer instruction" error (system messages not supported)
                    error_str = str(e).lower()
                    if ("developer instruction" in error_str or "system" in error_str) and not self._no_system_message:
                        logger.warning(f"⚠️ Model {self.model_name} doesn't support system messages. Retrying without system message...")
                        self._no_system_message = True
                        # Retry without system message - merge instructions into user message
                        user_prompt = f"""{system_content}

{prompt}"""
                        try:
                            response = self.client.chat.completions.create(
                                model=self.model_name,
                                messages=[{"role": "user", "content": user_prompt}],
                                max_tokens=500,
                                temperature=0.3 + (attempt * 0.1)
                            )
                            last_response = response
                        except Exception as retry_error:
                            logger.error(f"Error retrying without system message: {str(retry_error)}")
                            if attempt == max_attempts - 1:
                                return {
                                    "success": False,
                                    "error": f"Model compatibility error: {str(e)}",
                                    "tags": []
                                }
                            continue
                    else:
                        # Different BadRequestError, re-raise
                        raise
                except UnicodeEncodeError as e:
                    logger.error(f"❌ Unicode encoding error in API call: {e}")
                    
                    # Safer fallback strategy: Remove only problematic characters, keep Indic content
                    logger.info("🔄 Retrying with safer Unicode cleanup...")

                    # Clean by removing ONLY control characters, not all non-ASCII
                    def safe_clean(text):
                        cleaned = ''
                        for char in text:
                            cat = unicodedata.category(char)
                            if cat[0] != 'C' or char in '\n\t\r ':
                                cleaned += char
                        return cleaned

                    content_safe = safe_clean(content)
                    title_safe = safe_clean(title)
                    description_safe = safe_clean(description)

                    if not content_safe.strip():
                        logger.error("❌ Document content is empty after safe cleanup.")
                        return {
                            "success": False,
                            "error": "Document encoding issue: Unable to process document due to encoding limitations.",
                            "tags": []
                        }
                    
                    prompt_safe = self._build_prompt(
                        title_safe,
                        description_safe,
                        content_safe,
                        requested_tags,
                        detected_language,
                        language_name,
                        quality_info
                    )

                    response = self.client.chat.completions.create(
                        model=self.model_name,
                        messages=[
                            {
                                "role": "system",
                                "content": "You are a document tagging expert. Generate ENGLISH tags only. Return valid JSON: {\"names\":[...],\"subjects\":[...],\"context\":[...]}"
                            },
                            {"role": "user", "content": prompt_safe}
                        ],
                        max_tokens=700,
                        temperature=0.2
                    )
                    last_response = response
                
                # Parse response
                tags_text = response.choices[0].message.content.strip()
                logger.info(f"Raw AI response (attempt {attempt + 1}): '{tags_text[:200]}...'")
                
                if response.usage:
                    total_tokens_used += response.usage.total_tokens
                
                # Parse with buffer amount
                tags_parsed = self._parse_tags(tags_text, requested_tags)
                logger.info(f"📊 Parsed {len(tags_parsed)} tags before filtering")
                
                # Apply exclusion filter if needed
                tags_after_exclusion = tags_parsed
                if self.exclusion_words:
                    tags_after_exclusion = self._filter_excluded_tags(tags_parsed)
                    rejected_count = len(tags_parsed) - len(tags_after_exclusion)
                    if rejected_count > 0:
                        logger.info(f"🚫 Exclusion filter removed {rejected_count} tags")
                
                # Add new unique tags to our collection
                existing_tags_lower = {t.lower() for t in all_collected_tags}
                for tag in tags_after_exclusion:
                    if tag.lower() not in existing_tags_lower:
                        all_collected_tags.append(tag)
                        existing_tags_lower.add(tag.lower())
                
                logger.info(f"📊 After attempt {attempt + 1}: {len(all_collected_tags)} total unique tags collected (need {num_tags})")
                
                # Check if we have enough
                if len(all_collected_tags) >= num_tags:
                    logger.info(f"✅ Collected enough tags ({len(all_collected_tags)}) after {attempt + 1} attempt(s)")
                    break
                elif attempt < max_attempts - 1:
                    logger.warning(f"⚠️ Only {len(all_collected_tags)} tags after attempt {attempt + 1}, will retry...")
            
            # END OF RETRY LOOP

            # Deduplicate and take the first num_tags in priority order.
            # The LLM already ordered them: names → subjects → context.
            final_tags = self._select_best_tags(
                tags=all_collected_tags,
                num_tags=num_tags
            )
            
            # Final check - log if still short
            if len(final_tags) < num_tags:
                shortage = num_tags - len(final_tags)
                logger.warning(f"⚠️ SHORT {shortage} tags after {max_attempts} attempts! Returning {len(final_tags)} instead of {num_tags}")
            
            logger.info(f"✅ Final: {len(final_tags)}/{num_tags} tags: {final_tags}")

            # Decay rate limit delay after successful generation
            self._consecutive_successes += 1
            if self._consecutive_successes >= 3 and self._rate_limit_delay > settings.api_retry_delay:
                self._rate_limit_delay = max(
                    settings.api_retry_delay,
                    self._rate_limit_delay * 0.8
                )
                self._consecutive_successes = 0
                logger.info(f"📉 Rate limit delay decayed to {self._rate_limit_delay:.2f}s after consecutive successes")

            return {
                "success": True,
                "tags": final_tags,
                "raw_response": tags_text if 'tags_text' in locals() else "",
                "tokens_used": total_tokens_used,
                "tags_requested": num_tags,
                "tags_returned": len(final_tags),
                "tags_parsed": len(all_collected_tags),
                "filtering_stats": {
                    "attempts": attempt + 1 if 'attempt' in locals() else 1,
                    "total_collected": len(all_collected_tags),
                    "final": len(final_tags),
                    "target_met": len(final_tags) >= num_tags
                }
            }
            
        except openai.AuthenticationError:
            return {
                "success": False,
                "error": "Invalid API key. Please check your OpenRouter API key.",
                "tags": []
            }
        except openai.RateLimitError as e:
            # Reset success counter and track rate limit hits
            self._consecutive_successes = 0
            self._rate_limit_hit_count += 1
            
            # Exponential backoff for rate limits (capped at 2 minutes for free tier)
            new_delay = min(
                self._rate_limit_delay * settings.batch_retry_delay_multiplier,
                settings.batch_max_delay_between_requests
            )
            self._rate_limit_delay = new_delay
            self._last_rate_limit_time = time.time()
            
            error_msg = str(e)
            logger.error(f"🚫 RATE LIMITED (Hit #{self._rate_limit_hit_count}): Provider rejected request. Delay: {self._rate_limit_delay:.0f}s")
            logger.error(f"   Hint: You're using free tier. Add credits to OpenRouter for higher limits.")
            logger.error(f"   URL: https://openrouter.ai/account/billing/overview")
            
            if "429" in error_msg:
                return {
                    "success": False,
                    "error": f"RATE_LIMITED: OpenRouter free tier limit hit (attempt #{self._rate_limit_hit_count}). Adding {self._rate_limit_delay:.0f}s delay before next attempt.",
                    "tags": [],
                    "rate_limited": True
                }
            return {
                "success": False,
                "error": f"RATE_LIMITED: {error_msg}",
                "tags": [],
                "rate_limited": True
            }
        except Exception as e:
            logger.error(f"Error in generate_tags: {str(e)}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "tags": []
            }
    
    def _detect_indian_scripts(self, text: str) -> Dict[str, int]:
        """
        Detect which Indian scripts are present in the text
        
        Unicode ranges for Indian scripts:
        - Devanagari (Hindi, Marathi, Sanskrit): U+0900 - U+097F
        - Bengali/Assamese: U+0980 - U+09FF
        - Gurmukhi (Punjabi): U+0A00 - U+0A7F
        - Gujarati: U+0A80 - U+0AFF
        - Oriya (Odia): U+0B00 - U+0B7F
        - Tamil: U+0B80 - U+0BFF
        - Telugu: U+0C00 - U+0C7F
        - Kannada: U+0C80 - U+0CFF
        - Malayalam: U+0D00 - U+0D7F
        - Sinhala: U+0D80 - U+0DFF
        - Thai: U+0E00 - U+0E7F
        - Lao: U+0E80 - U+0EFF
        - Tibetan: U+0F00 - U+0FFF
        - Myanmar: U+1000 - U+109F
        """
        scripts = {
            'Devanagari (Hindi/Marathi/Sanskrit)': 0,
            'Bengali/Assamese': 0,
            'Gurmukhi (Punjabi)': 0,
            'Gujarati': 0,
            'Oriya (Odia)': 0,
            'Tamil': 0,
            'Telugu': 0,
            'Kannada': 0,
            'Malayalam': 0,
            'Other Indian scripts': 0
        }
        
        for char in text:
            code_point = ord(char)
            if 0x0900 <= code_point <= 0x097F:
                scripts['Devanagari (Hindi/Marathi/Sanskrit)'] += 1
            elif 0x0980 <= code_point <= 0x09FF:
                scripts['Bengali/Assamese'] += 1
            elif 0x0A00 <= code_point <= 0x0A7F:
                scripts['Gurmukhi (Punjabi)'] += 1
            elif 0x0A80 <= code_point <= 0x0AFF:
                scripts['Gujarati'] += 1
            elif 0x0B00 <= code_point <= 0x0B7F:
                scripts['Oriya (Odia)'] += 1
            elif 0x0B80 <= code_point <= 0x0BFF:
                scripts['Tamil'] += 1
            elif 0x0C00 <= code_point <= 0x0C7F:
                scripts['Telugu'] += 1
            elif 0x0C80 <= code_point <= 0x0CFF:
                scripts['Kannada'] += 1
            elif 0x0D00 <= code_point <= 0x0D7F:
                scripts['Malayalam'] += 1
            elif code_point > 127 and code_point < 0x0900:
                scripts['Other Indian scripts'] += 1
        
        # Return only scripts that were detected
        return {script: count for script, count in scripts.items() if count > 0}
    
    def _sanitize_text_for_api(self, text: str) -> str:
        """
        Sanitize text to handle ALL Unicode characters safely for ALL Indian languages
        
        This function ensures compatibility with:
        - All 22 official Indian languages
        - Mixed language documents (English + Indian languages)
        - Special symbols and currency signs
        - Proper UTF-8 encoding throughout
        
        CRITICAL: We preserve ALL Indian language content - the AI needs it to understand context
        """
        if not text:
            return text
        
        replacements_made = []
        
        # Replace only truly problematic characters that break API calls
        # Keep ALL Indian language scripts intact
        replacements = {
            # Currency symbols that might cause issues
            '\u20b9': 'Rs.',  # ₹ (Indian Rupee)
            '\u20ac': 'EUR',  # €
            '\u00a3': 'GBP',  # £
            '\u00a5': 'YEN',  # ¥
            '\u0024': '$',    # $ (sometimes causes issues)
            
            # Quotation marks
            '\u2018': "'",    # '
            '\u2019': "'",    # '
            '\u201c': '"',    # "
            '\u201d': '"',    # "
            '\u201e': '"',    # „
            '\u201f': '"',    # ‟
            
            # Dashes and special punctuation
            '\u2013': '-',    # –
            '\u2014': '-',    # —
            '\u2026': '...',  # …
            '\u2022': '*',    # •
            '\u2023': '>',    # ‣
            
            # Zero-width and invisible characters
            # CRITICAL: Preserve ZWJ/ZWNJ for proper Indic script rendering
            '\u200b': '',     # Zero-width space (remove - causes issues)
            # '\u200c': '',   # Zero-width non-joiner (PRESERVE for Indic)
            # '\u200d': '',   # Zero-width joiner (PRESERVE for Indic)
            '\ufeff': '',     # Zero-width no-break space (BOM - remove)
            
            # Other problematic characters
            '\u00a0': ' ',    # Non-breaking space
            '\u202f': ' ',    # Narrow no-break space
        }
        
        for unicode_char, ascii_replacement in replacements.items():
            if unicode_char in text:
                count = text.count(unicode_char)
                text = text.replace(unicode_char, ascii_replacement)
                replacements_made.append(f"{repr(unicode_char)}→'{ascii_replacement}' ({count}x)")
        
        if replacements_made:
            logger.info(f"🔄 Sanitized symbols: {', '.join(replacements_made)}")
        
        # Detect which Indian scripts are present
        scripts_found = self._detect_indian_scripts(text)
        if scripts_found:
            scripts_summary = ', '.join([f"{script}: {count} chars" for script, count in scripts_found.items()])
            logger.info(f"🌐 Multilingual document detected: {scripts_summary}")
        
        # Ensure clean UTF-8 encoding
        # CRITICAL: Preserve ALL Indian language content - never fall back to ASCII
        try:
            # Normalize to NFC (Canonical Composition) for consistency
            text = unicodedata.normalize('NFC', text)

            # Ensure proper UTF-8 encoding
            text = text.encode('utf-8', errors='replace').decode('utf-8', errors='replace')
        except Exception as e:
            logger.error(f"❌ Text encoding error: {e}")
            # Safer fallback: Remove ONLY control characters, keep all valid Unicode
            import re
            # Remove control characters (category 'C') except whitespace
            cleaned = ''
            for char in text:
                cat = unicodedata.category(char)
                if cat[0] != 'C' or char in '\n\t\r ':
                    cleaned += char
            text = cleaned
            logger.warning("⚠️ Applied safe encoding cleanup - Indic scripts preserved")

        return text
    
    def _detect_document_type(self, title: str, description: str, content: str) -> str:
        """
        Detect document type from content for specialized prompting
        
        Returns document type: annual_report, budget, scheme, newsletter, legal, tender, policy, or general
        """
        combined = f"{title} {description} {content[:800]}".lower()
        
        # Check for specific document types (order matters - more specific first)
        type_patterns = {
            'annual_report': ['annual report', 'yearly report', 'financial year', 'fy 20', 'year in review', 'वार्षिक रिपोर्ट'],
            'budget': ['budget', 'allocation', 'expenditure', 'appropriation', 'बजट', 'आवंटन'],
            'scheme': ['scheme', 'yojana', 'eligibility', 'application process', 'benefits', 'योजना'],
            'newsletter': ['newsletter', 'monthly', 'quarterly', 'bulletin', 'समाचार पत्र'],
            'legal': ['act', 'rules', 'notification', 'gazette', 'section', 'clause', 'अधिनियम'],
            'tender': ['tender', 'bid', 'procurement', 'quotation', 'निविदा'],
            'policy': ['policy', 'framework', 'guidelines', 'norms', 'नीति']
        }
        
        for doc_type, keywords in type_patterns.items():
            if any(kw in combined for kw in keywords):
                logger.info(f"📄 Detected document type: {doc_type}")
                return doc_type
        
        logger.info(f"📄 Document type: general (no specific pattern matched)")
        return 'general'
    
    def _get_document_type_guidance(self, doc_type: str) -> str:
        """Return focused tagging guidance based on document type"""
        guidance = {
            'annual_report': 'Look for: org name, year like 2023-24, program names, people names.',
            'budget': 'Look for: ministry name, fiscal year, scheme names, department names.',
            'scheme': 'Look for: scheme name/acronym, implementing agency, beneficiary group names.',
            'newsletter': 'Look for: org name, month/quarter, event names, program names.',
            'legal': 'Look for: act name with year, notification numbers, section numbers.',
            'tender': 'Look for: tender reference number, issuing organization, item being procured.',
            'policy': 'Look for: policy name, ministry name, implementation year.',
            'general': 'Look for: organization names, program names, dates, reference numbers, place names.'
        }
        return guidance.get(doc_type, guidance['general'])
    
    def _get_quality_adjusted_instruction(self, quality_info: Optional[Dict[str, Any]]) -> str:
        """Adjust extraction instructions based on document quality"""
        if not quality_info:
            return ""
        
        quality_tier = quality_info.get('quality_tier', 'medium')
        doc_type = quality_info.get('type', 'unknown')
        
        if quality_tier == 'low':
            return "\n⚠️ LOW QUALITY SCAN - Extract only clearly readable terms and obvious entities. Prioritize unambiguous words."
        elif quality_tier == 'medium' and doc_type == 'scanned':
            return "\n📄 SCANNED DOCUMENT - Focus on clearly extracted text. Verify entities and dates are accurate."
        else:
            return ""  # High quality - no special instruction needed

    def _normalize_phrase_to_tag(self, phrase: str) -> str:
        """Normalize arbitrary phrase into lowercase space-separated tag format."""
        if not phrase:
            return ""

        normalized = phrase.lower()
        normalized = re.sub(r'[^a-z0-9\s\-\/]', ' ', normalized)
        normalized = normalized.replace('/', ' ')
        normalized = normalized.replace('-', ' ')
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        return normalized

    def _tokenize_keywords(self, text: str) -> List[str]:
        """Extract lightweight keyword tokens for relevance scoring."""
        if not text:
            return []
        tokens = re.findall(r'[a-z0-9]{3,}', text.lower())
        return [t for t in tokens if t not in self.KEYWORD_STOPWORDS]

    def _extract_anchor_terms(
        self,
        title: str,
        description: str,
        content: str,
        max_terms: int = 24
    ) -> List[str]:
        """
        Extract high-signal anchor terms generically (years, identifiers, acronyms, title phrases).
        These anchors are used both in prompting and post-generation re-ranking.
        """
        source = f"{title}\n{description}\n{content[:8000]}"
        anchors: List[str] = []

        # Years and year ranges like 2015, 2024-25, 2023/24.
        for match in re.findall(r'\b(?:19|20)\d{2}(?:\s*[-/]\s*(?:\d{2,4}))?\b', source):
            anchors.append(self._normalize_phrase_to_tag(match))

        # Identifier-like phrases common across many document classes.
        id_pattern = re.compile(
            r'\b(?:section|sec|rule|article|clause|notification|circular|order|memo|'
            r'tender|bid|reference|ref|file)\s*[-.:]?\s*[a-z0-9\/\.-]{1,24}\b',
            flags=re.IGNORECASE
        )
        for match in id_pattern.findall(source):
            anchors.append(self._normalize_phrase_to_tag(match))

        # Acronyms / alphanumeric codes.
        for match in re.findall(r'\b[A-Z]{2,}(?:[-/][A-Z0-9]{2,})*\b', source):
            anchors.append(self._normalize_phrase_to_tag(match))

        # Short phrases from title/description tend to be context-defining.
        for text in [title, description]:
            words = [w for w in re.findall(r'[a-z0-9]{3,}', text.lower()) if w not in self.KEYWORD_STOPWORDS]
            for n in (3, 2):
                for i in range(0, max(0, len(words) - n + 1)):
                    phrase = "-".join(words[i:i + n])
                    if 5 <= len(phrase) <= 45:
                        anchors.append(phrase)

        # Deduplicate while preserving order and dropping low-value artifacts.
        deduped: List[str] = []
        seen: Set[str] = set()
        for term in anchors:
            if not term or len(term) < 3 or term in seen:
                continue
            if term in self.GENERIC_SINGLE_TAGS:
                continue
            if term.isdigit() and len(term) < 4:
                continue
            seen.add(term)
            deduped.append(term)
            if len(deduped) >= max_terms:
                break

        return deduped

    def _build_content_preview(self, content: str, max_chars: int = 5000) -> str:
        """
        Build representative context with start/middle/end snippets, subject lines,
        and high-signal lines. Larger window to capture more substantive content.
        """
        if not content:
            return ""

        text = content.strip()
        if len(text) <= max_chars:
            return text

        # Extract subject/heading lines first - these are highest-signal in govt docs
        subject_lines: List[str] = []
        heading_regex = re.compile(
            r'(?i)(?:^|\n)\s*(?:subject|sub|re|ref|regarding|विषय)\s*[:.\-]\s*(.+)',
        )
        for match in heading_regex.finditer(text[:5000]):
            line = re.sub(r'\s+', ' ', match.group(0)).strip()
            if 10 < len(line) < 300:
                subject_lines.append(line)

        window = 1200
        start_chunk = text[:window]
        middle_start = max(0, (len(text) // 2) - (window // 2))
        middle_chunk = text[middle_start:middle_start + window]
        end_chunk = text[-window:]

        signal_regex = re.compile(
            r'(?i)(?:'
            r'\b(?:19|20)\d{2}(?:[-/]\d{2,4})?\b|'
            r'\b(?:section|rule|article|clause|notification|circular|order|memo|'
            r'tender|bid|budget|scheme|policy|act)\b|'
            r'\b[A-Z]{2,}(?:[-/][A-Z0-9]{2,})*\b'
            r')'
        )
        signal_lines: List[str] = []
        for line in text.splitlines():
            clean = re.sub(r'\s+', ' ', line).strip()
            if not clean:
                continue
            if len(clean) < 35 or len(clean) > 220:
                continue
            if signal_regex.search(clean):
                signal_lines.append(clean)
            if len(signal_lines) >= 10:
                break

        preview = ""
        if subject_lines:
            preview += "[SUBJECT/HEADING]\n" + "\n".join(subject_lines[:3]) + "\n\n"
        preview += (
            "[START]\n" + start_chunk +
            "\n\n[MIDDLE]\n" + middle_chunk +
            "\n\n[END]\n" + end_chunk
        )
        if signal_lines:
            preview += "\n\n[KEY LINES]\n- " + "\n- ".join(signal_lines)

        if len(preview) > max_chars:
            preview = preview[:max_chars].rstrip() + "\n...[truncated]"
        return preview

    def _build_composition_instruction(self, num_tags: int) -> str:
        """Create soft tag-composition targets that improve distinctiveness."""
        entity_min = max(2, round(num_tags * 0.35))
        broad_max = max(1, round(num_tags * 0.25))
        include_time = "yes" if num_tags >= 5 else "if available"
        return (
            f"- Aim for at least {entity_min} entity/program/institution tags.\n"
            f"- Include a time/version tag ({include_time}) when years or periods exist.\n"
            f"- Include legal/procedural identifier tags when present (section/rule/notification/tender no.).\n"
            f"- Keep broad thematic tags to at most {broad_max}."
        )
    
    def _build_prompt(
        self,
        title: str,
        description: str,
        content: str,
        num_tags: int,
        detected_language: Optional[str] = None,
        language_name: Optional[str] = None,
        quality_info: Optional[Dict[str, Any]] = None,
        anchor_terms: Optional[List[str]] = None,
        already_generated: Optional[List[str]] = None
    ) -> str:
        """
        Build a tiered JSON prompt.

        Asks the LLM to categorise tags into three priority tiers:
          names    — specific named things (programs, schemes, acts + year, orgs)
          subjects — what the document is about (topic, beneficiary, purpose)
          context  — supporting identifiers (year, portal, reference number)

        The LLM's ordering is trusted directly; no re-ranking is applied downstream.
        """
        title = self._sanitize_text_for_api(title)
        description = self._sanitize_text_for_api(description)
        content = self._sanitize_text_for_api(content)

        content_preview = self._build_content_preview(content)
        quality_hint = self._get_quality_adjusted_instruction(quality_info)

        # Tier size guidance (soft targets, not hard limits)
        n_names    = max(1, round(num_tags * 0.50))
        n_subjects = max(1, round(num_tags * 0.30))
        n_action   = max(1, num_tags - n_names - n_subjects)

        language_hint = ""
        if language_name and detected_language != 'en':
            language_hint = (
                f"\nDocument language: {language_name}. "
                "Translate all named entities and key terms to English in your output."
            )

        exclusion_hint = ""
        if self.exclusion_words:
            sample = list(self.exclusion_words)[:15]
            exclusion_hint = (
                f"\nDo NOT generate tags containing any of these excluded terms: "
                f"{', '.join(sample)} (and similar)."
            )

        already_hint = ""
        if already_generated:
            already_hint = (
                f"\nAlready generated — skip these entirely: "
                f"{', '.join(already_generated[:15])}"
            )

        prompt = f"""Analyze the document below and return exactly {num_tags} search tags as a JSON object.{language_hint}{quality_hint}

DOCUMENT:
Title: {title}
{f'Description: {description}' if description else ''}

{content_preview}

Return ONLY a valid JSON object — no prose, no markdown, no explanation:
{{
  "names":    [...],
  "subjects": [...],
  "actions":  [...]
}}

Tier rules (fill each tier; combined total = {num_tags}):
- "names"    → Specific NAMED things: program/scheme/initiative names, acts (abbreviated, e.g. "rights act 2019"), specific organisations by their actual name. ~{n_names} tags. HIGHEST priority.
- "subjects" → What the document is about: beneficiary groups, domain, core topic. ~{n_subjects} tags.
- "actions"  → What the document does: purpose like "expression of interest", "recruitment", "guidelines", "circular". ~{n_action} tags.

Tag format rules:
- 1–4 words, all lowercase, space-separated (no hyphens, no underscores).
- Every tag must come from actual text in the document — no invented terms.
- NO dates, years, or reference numbers — these are not search tags.
- NO bare section numbers, NO generic legal boilerplate (memorandum of association, articles of association).{exclusion_hint}{already_hint}"""

        return prompt

    def _is_overly_generic_without_qualifier(self, tag: str) -> bool:
        """
        Generic-quality gate:
        - reject standalone generic tags
        - reject multi-part tags where all components are generic and no numeric qualifier exists
        - reject tags matching low-value procedural patterns
        """
        normalized = self._normalize_phrase_to_tag(tag)
        if not normalized:
            return True

        # Check against low-value patterns FIRST (these are always generic regardless of numbers)
        for pattern in self.LOW_VALUE_PATTERNS:
            if pattern.match(normalized):
                logger.debug(f"Tag '{normalized}' matched low-value pattern")
                return True

        # Numbers alone don't make a tag valuable if it's fundamentally procedural
        # Only allow numbers to "save" a tag if the base isn't purely procedural
        parts = [p for p in normalized.split('-') if p]
        if not parts:
            return True

        # Check single-word tags
        if len(parts) == 1:
            return parts[0] in self.GENERIC_SINGLE_TAGS

        # For multi-part tags: check if ALL non-numeric parts are generic
        non_numeric_parts = [p for p in parts if not p.isdigit()]
        
        # If all non-numeric parts are generic components, it's too generic
        # UNLESS it contains a specific identifier pattern (like tender number, section number)
        if all(part in self.GENERIC_COMPONENT_TAGS for part in non_numeric_parts):
            # Check if it has a meaningful identifier pattern
            has_identifier = bool(re.search(r'(?:no|number|ref|id)[-\s]?[a-z0-9]+', normalized, re.I))
            if not has_identifier:
                return True

        return False

    def _jaccard_similarity(self, left: str, right: str) -> float:
        """Simple token-level similarity used for diversity-aware selection."""
        left_tokens = set(left.split('-'))
        right_tokens = set(right.split('-'))
        if not left_tokens or not right_tokens:
            return 0.0
        union = left_tokens | right_tokens
        if not union:
            return 0.0
        return len(left_tokens & right_tokens) / len(union)

    def _score_tag(
        self,
        tag: str,
        anchor_terms: Set[str],
        context_tokens: Set[str]
    ) -> float:
        """
        Score a candidate tag for distinctiveness and retrieval utility.
        Higher is better. Heavily penalizes generic/procedural terms.
        """
        score = 0.0
        normalized = self._normalize_phrase_to_tag(tag)
        parts = [p for p in normalized.split('-') if p]

        # Mild reward for alphanumeric identifiers (reduced - was +2.5)
        # This no longer lets salary figures and addresses dominate
        if re.search(r'[a-z].*\d.*[a-z]|[a-z]{2,}\d{4}|\d{4}[a-z]{2,}', normalized):
            score += 0.8

        # Reward years in context (fiscal years, report years)
        if re.search(r'(?:fy[-\s]?)?\d{4}(?:[-/]\d{2,4})?', normalized):
            score += 1.5

        # Reward multi-part tags that aren't all generic
        if len(parts) >= 2:
            non_generic_parts = [p for p in parts if p not in self.GENERIC_COMPONENT_TAGS]
            if non_generic_parts:
                score += 0.6 * len(non_generic_parts)

        # Reward overlap with extracted anchors (highest-signal terms)
        if normalized in anchor_terms:
            score += 4.0  # Exact anchor matches are very valuable
        elif any(normalized in anchor or anchor in normalized for anchor in anchor_terms if len(anchor) >= 4):
            score += 2.5

        # Reward overlap with title/description keywords (but not generic ones)
        non_generic_context = context_tokens - self.GENERIC_COMPONENT_TAGS - self.GENERIC_SINGLE_TAGS
        overlap = sum(1 for p in parts if p in non_generic_context)
        score += min(overlap, 3) * 0.8

        # Reward acronym-style tags (often organization/scheme identifiers)
        if re.match(r'^[a-z]{2,6}$', normalized) and normalized.upper() == normalized.upper():
            score += 1.2

        # Reward named entity patterns (programs, schemes, missions)
        if re.search(r'(?:foundation|mission|scheme|yojana|abhiyan|portal|programme|program)', normalized):
            score += 1.0

        # Reward specific identifier patterns WITH reference numbers
        if re.search(r'\b(?:no|ref|id)[-\s]?[a-z0-9]+', normalized):
            score += 1.5

        # --- PENALTIES ---

        # Penalize incidental metadata (salary, address, experience, post counts)
        # These appear in every govt document and have zero search utility
        if re.search(r'^rs[-\s]?\d+', normalized):
            score -= 4.0  # salary amounts
        if re.search(r'^(?:sector|plot|block|floor|wing|building)[-\s](?:no[-\s]?)?[a-z0-9-]{1,10}$', normalized):
            score -= 4.0  # address fragments
        if re.search(r'(?:experience|age)[-\s](?:more[-\s]than[-\s]|less[-\s]than[-\s]|limit[-\s]|upto[-\s])?\d', normalized):
            score -= 3.5  # experience/age requirements
        if re.search(r'^no[-\s]of[-\s](?:post|posts|vacancy|vacancies)', normalized):
            score -= 3.0  # post count labels
        if re.search(r'^(?:date|dated|last[-\s]date)[-\s]', normalized):
            score -= 2.5  # pure date labels
        if re.search(r'(?:^|\b)\d{5,6}(?:$|\b)', normalized):
            score -= 2.5  # pin codes

        # Generic/procedural tag penalties
        if self._is_overly_generic_without_qualifier(normalized):
            score -= 4.0

        procedural_starters = {'tender', 'bid', 'quotation', 'opening', 'closing', 'deadline', 'submission', 'security'}
        if parts and parts[0] in procedural_starters:
            score -= 2.5

        if parts and all(p in self.GENERIC_COMPONENT_TAGS for p in parts):
            score -= 3.0

        if len(parts) == 1 and parts[0] in self.GENERIC_SINGLE_TAGS:
            score -= 3.5

        return score

    def _select_best_tags(
        self,
        tags: List[str],
        num_tags: int,
        **kwargs  # absorb legacy keyword arguments (anchor_terms, title, description)
    ) -> List[str]:
        """
        Deduplicate and return the first num_tags in the order they arrived.

        Tags come out of _parse_tags in tier-priority order (names → subjects → context)
        because the LLM JSON response is flattened in that order. No re-ranking needed —
        the model already put the most identifying tags first.
        """
        if not tags or num_tags <= 0:
            return []

        seen: Set[str] = set()
        deduped: List[str] = []
        for tag in tags:
            key = tag.lower().strip()
            if key and key not in seen:
                seen.add(key)
                deduped.append(tag)

        result = deduped[:num_tags]
        logger.info(f"✅ Final {len(result)}/{num_tags} tags: {result}")
        return result
    
    def _is_gibberish_tag(self, tag: str) -> bool:
        """
        Detect if a tag is gibberish/nonsensical OCR output.

        Checks each hyphen-separated part independently so acronyms
        (nsfdc, gsr, crm) don't get concatenated with adjacent words.
        Parts with fewer than 7 letters are too short to reliably
        distinguish acronyms from gibberish, so they skip vowel checks.
        """
        if len(tag) < 3:
            return False

        for part in tag.replace('-', ' ').split():
            if not part:
                continue

            letters = re.sub(r'[^a-zA-Z]', '', part)

            # Too few letters to analyse reliably — skip
            if len(letters) < 7:
                continue

            # Vowel ratio check
            vowels = sum(1 for c in letters.lower() if c in 'aeiouy')
            if vowels / len(letters) < 0.08:
                logger.warning(f"🚫 Tag '{tag}' rejected: too few vowels in '{part}'")
                return True

            # Extreme consonant cluster
            if re.findall(r'[bcdfghjklmnpqrstvwxz]{6,}', letters.lower()):
                logger.warning(f"🚫 Tag '{tag}' rejected: consonant cluster in '{part}'")
                return True

            # Unpronounceable segment
            for cp in re.split(r'[aeiouy]+', letters.lower()):
                if len(cp) >= 7 and cp.isalpha():
                    logger.warning(f"🚫 Tag '{tag}' rejected: unpronounceable '{cp}'")
                    return True

        return False
    
    def _parse_tags(self, tags_text: str, expected_count: int) -> List[str]:
        """
        Parse tags from LLM response.

        Primary path: expects a JSON object with keys "names", "subjects", "context".
        Tiers are flattened in that order so the most identifying tags come first.

        Fallback: if the model returned plain comma-separated text (older models,
        no-system-message path, etc.) we split on commas and treat everything equally.

        Filtering is intentionally minimal — the prompt handles quality.
        We only reject: >3 word tags, roman numerals, gibberish OCR noise,
        non-ASCII, and the tiny universal-noise set in _MINIMAL_GENERIC_TERMS.
        """
        logger.info(f"Raw AI response: '{tags_text[:300]}...'")

        # ── 1. Attempt JSON parse ──────────────────────────────────────────────
        raw_ordered: List[str] = []
        parsed_as_json = False

        cleaned = re.sub(r'```(?:json)?\s*', '', tags_text).replace('```', '').strip()
        json_match = re.search(r'\{.*\}', cleaned, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(0))
                for tier in ('names', 'subjects', 'actions', 'context'):
                    for item in data.get(tier, []):
                        if isinstance(item, str) and item.strip():
                            raw_ordered.append(item.strip())
                parsed_as_json = bool(raw_ordered)
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"JSON parse failed ({e}), falling back to text split")

        # ── 2. Text fallback ───────────────────────────────────────────────────
        if not parsed_as_json:
            if ',' in tags_text:
                raw_ordered = [t.strip() for t in tags_text.split(',')]
            elif ';' in tags_text:
                raw_ordered = [t.strip() for t in tags_text.split(';')]
            else:
                raw_ordered = [t.strip() for t in tags_text.split('\n')]

        logger.info(
            f"Parsed {'JSON' if parsed_as_json else 'text'}: "
            f"{len(raw_ordered)} raw candidates"
        )

        # ── 3. Clean and filter ────────────────────────────────────────────────
        _MONTH_RE = re.compile(
            r'^(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?'
            r'|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?'
            r'|dec(?:ember)?)$',
            re.IGNORECASE
        )

        valid_tags: List[str] = []
        rejected: List[str] = []

        for raw in raw_ordered:
            if not raw:
                continue

            tag = raw.lower().strip()
            tag = re.sub(r'^[\d\.\-\)\]\s]+', '', tag)    # strip leading bullets/numbers
            tag = re.sub(r'^(st|nd|rd|th)\b\s*', '', tag) # strip orphaned ordinal suffixes
            tag = re.sub(r'[^\w\s\-]', '', tag)            # remove special chars
            tag = tag.replace('-', ' ')                     # de-hyphenate
            tag = re.sub(r'\s+', ' ', tag).strip()

            if not tag or len(tag) < 2 or len(tag) > 80:
                continue

            # Must be ASCII (English output only)
            if not all(ord(c) < 128 for c in tag):
                continue

            # Reject pure date/number tags — dates don't help retrieve document content
            words = tag.split()
            all_date_words = all(
                re.match(r'^\d+$', w) or _MONTH_RE.match(w)
                for w in words
            )
            if all_date_words:
                logger.debug(f"Rejected (date-only tag): '{tag}'")
                rejected.append(tag)
                continue

            # 4-word maximum (allows "rights act 2019" style act names)
            if len(words) > 4:
                logger.debug(f"Rejected (too long): '{tag}'")
                rejected.append(tag)
                continue

            # Pure roman numerals are document structure, not content
            if self._ROMAN_RE.match(tag):
                logger.debug(f"Rejected (roman numeral): '{tag}'")
                rejected.append(tag)
                continue

            # OCR gibberish
            if self._is_gibberish_tag(tag):
                logger.debug(f"Rejected (gibberish): '{tag}'")
                rejected.append(tag)
                continue

            # Universal noise (tiny set — see _MINIMAL_GENERIC_TERMS)
            if tag in self._MINIMAL_GENERIC_TERMS:
                logger.debug(f"Rejected (universal noise): '{tag}'")
                rejected.append(tag)
                continue

            if tag not in valid_tags:
                valid_tags.append(tag)

        if rejected:
            logger.info(f"Rejected {len(rejected)}: {rejected[:8]}")
        logger.info(f"Valid tags after filtering: {len(valid_tags)}")
        return valid_tags
    
    def _filter_excluded_tags(self, tags: List[str]) -> List[str]:
        """
        Filter out tags that match exclusion words using coverage-based matching.

        Strategy: an exclusion term only removes a tag if it covers a
        significant fraction (>=50%) of the tag's hyphen-parts.

        This means:
        - "act" (1 part) in "official-languages-act-1963" (4 parts) = 25% → KEEP
        - "social-justice" (2 parts) in "social-justice-ministry" (3 parts) = 67% → EXCLUDE
        - Exact matches always exclude regardless of coverage.
        """
        filtered_tags = []

        # Pre-process exclusion terms once
        exclusion_entries = []
        for excluded_word in self.exclusion_words:
            normalized = excluded_word.lower().strip().replace(' ', '-')
            if not normalized:
                continue
            parts_count = len([p for p in normalized.split('-') if p])
            escaped = re.escape(normalized).replace(r'\-', r'[\s\-]')
            pattern = re.compile(rf'(?:^|-)({escaped})(?:-|$)', re.IGNORECASE)
            exclusion_entries.append((pattern, excluded_word, normalized, parts_count))

        for tag in tags:
            tag_normalized = tag.lower().strip().replace(' ', '-')
            tag_parts_count = len([p for p in tag_normalized.split('-') if p])

            excluded = False
            for pattern, excluded_word, excl_normalized, excl_parts_count in exclusion_entries:
                # Exact match always excludes
                if tag_normalized == excl_normalized:
                    logger.info(f"Excluding tag '{tag}' (exact match with '{excluded_word}')")
                    excluded = True
                    break

                # Containment match — only exclude if exclusion term covers
                # >=50% of the tag's parts (prevents "act" from killing
                # "official-languages-act-1963")
                if tag_parts_count > 0 and pattern.search(tag_normalized):
                    coverage = excl_parts_count / tag_parts_count
                    if coverage >= 0.5:
                        logger.info(f"Excluding tag '{tag}' ('{excluded_word}' covers {coverage:.0%})")
                        excluded = True
                        break

            if not excluded:
                filtered_tags.append(tag)

        return filtered_tags
    
    def test_connection(self) -> Dict[str, Any]:
        """Test API connection"""
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": "Say 'ok'"}],
                max_tokens=5
            )
            return {"success": True, "message": "Connection successful"}
        except Exception as e:
            return {"success": False, "error": str(e)}
