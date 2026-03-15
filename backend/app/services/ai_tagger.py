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
        quality_info: Optional[Dict[str, Any]] = None,
        extracted_entities: Optional[Dict[str, List[str]]] = None
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
            extracted_entities: Entity summary from LangExtract (e.g. {"organization": [...], "program": [...]})

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
            max_derivable = max(num_tags * 3, content_words // 8) if content_words > 0 else num_tags * 3

            # Over-request 3x to absorb exclusion filter losses in one shot.
            # With ~60% exclusion rate, 3x gives ~40% survivors = enough for target.
            buffer = min(num_tags * 3, max_derivable)

            all_collected_tags: List[str] = []
            total_tokens_used = 0
            max_attempts = 2  # Second attempt is emergency fallback only

            for attempt in range(max_attempts):
                tags_still_needed = num_tags - len(all_collected_tags)
                if tags_still_needed <= 0:
                    break

                # First attempt gets full budget; retry asks for remainder + buffer
                requested_tags = buffer if attempt == 0 else min(tags_still_needed + 8, buffer)
                logger.info(
                    f"🎯 Attempt {attempt + 1}/{max_attempts}: need {tags_still_needed}, "
                    f"requesting {requested_tags} (content: {content_words} words, "
                    f"exclusions: {len(self.exclusion_words)})"
                )

                already = list(set(all_collected_tags)) if attempt > 0 else None
                prompt = self._build_prompt(
                    title, description, content, requested_tags,
                    detected_language, language_name, quality_info,
                    already_generated=already,
                    extracted_entities=extracted_entities,
                    tier_target=num_tags  # Tier distribution based on real target, not inflated request
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
                        quality_info,
                        extracted_entities=extracted_entities
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

    def _build_content_preview(self, content: str, max_chars: int = 15000) -> str:
        """
        Build representative context from extracted text. Passes full text when
        possible (up to 15K chars ≈ 3750 tokens). Only uses START/MIDDLE/END
        chunking as a fallback for very large documents.
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

        window = 4000
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

    def _build_prompt(
        self,
        title: str,
        description: str,
        content: str,
        num_tags: int,
        detected_language: Optional[str] = None,
        language_name: Optional[str] = None,
        quality_info: Optional[Dict[str, Any]] = None,
        already_generated: Optional[List[str]] = None,
        extracted_entities: Optional[Dict[str, List[str]]] = None,
        tier_target: Optional[int] = None
    ) -> str:
        """
        Build a tiered JSON prompt.

        Two paths:
        - Entity-enriched: when LangExtract provided real entities, the LLM selects
          from grounded facts instead of guessing from a short snippet.
        - Fallback: existing behavior when no entities are available.

        The LLM's ordering is trusted directly; no re-ranking is applied downstream.
        """
        title = self._sanitize_text_for_api(title)
        description = self._sanitize_text_for_api(description)
        content = self._sanitize_text_for_api(content)

        content_preview = self._build_content_preview(content)
        quality_hint = self._get_quality_adjusted_instruction(quality_info)

        # Tier size guidance based on real target, not inflated request count.
        # When over-requesting (e.g. 30 for target of 10), tiers stay at 5/3/2
        # so the LLM doesn't pad "names" with 15 state names.
        t = tier_target if tier_target else num_tags
        n_names    = max(1, round(t * 0.50))
        n_subjects = max(1, round(t * 0.30))
        n_action   = max(1, t - n_names - n_subjects)

        language_hint = ""
        if language_name and detected_language != 'en':
            language_hint = (
                f"\nDocument language: {language_name}. "
                "Translate all named entities and key terms to English in your output."
            )

        exclusion_hint = ""
        if self.exclusion_words:
            all_excluded = ', '.join(sorted(self.exclusion_words))
            exclusion_hint = (
                f"\nDo NOT generate tags that match or substantially overlap with these excluded terms:\n"
                f"{all_excluded}"
            )

        already_hint = ""
        if already_generated:
            already_hint = (
                f"\nAlready generated — skip these entirely: "
                f"{', '.join(already_generated[:15])}"
            )

        # Build entity context block when entities are available
        entity_block = ""
        if extracted_entities:
            entity_lines = []
            doc_types = extracted_entities.get("document_type", [])
            for cls, values in extracted_entities.items():
                if not values or cls == "document_type":
                    continue
                entity_lines.append(f"  {cls}: {', '.join(values[:10])}")
            if entity_lines:
                doc_type_instruction = ""
                if doc_types:
                    doc_type_instruction = (
                        f"\nThis document is a '{doc_types[0]}'. "
                        "Include the document type as one of the 'actions' tags."
                    )
                entity_block = (
                    "\n\nCONTEXT — entities found in this document:\n"
                    + "\n".join(entity_lines)
                    + "\n\nThese entities tell you what the document CONTAINS. "
                    "Your job is to identify what the document is ABOUT — its purpose and subject matter. "
                    "Do NOT copy entity lists into tags. "
                    "Condense long names (e.g. 'pradhan mantri anusuchit jaati abhyuday yojana' → 'pm ajay yojana')."
                    + doc_type_instruction
                )
                logger.info(f"🏷️ Entity context added to prompt: {len(entity_lines)} categories")

        prompt = f"""Analyze the document below and return exactly {num_tags} search tags as a JSON object.{language_hint}{quality_hint}

DOCUMENT:
Title: {title}
{f'Description: {description}' if description else ''}{entity_block}

{content_preview}

Return ONLY a valid JSON object — no prose, no markdown, no explanation:
{{
  "names":    [...],
  "subjects": [...],
  "actions":  [...]
}}

Tier rules (fill each tier; combined total = {num_tags}):
- "names"    → Scheme/program names, acts with year, specific organizations. ~{n_names} tags.
- "subjects" → What the document is ABOUT — its purpose, decision, or subject matter. NOT what it contains or lists. ~{n_subjects} tags.
- "actions"  → Document type + specific purpose. ~{n_action} tags.

A GOOD tag answers "what is this document about?" A BAD tag answers "what does this document mention?"

Tag format rules:
- 1–5 words, all lowercase, space-separated (no hyphens, no underscores).
- Every tag must come from actual text in the document — no invented terms.
- Years ARE allowed when paired with a name (e.g. "budget 2024-25", "act 2016"). Standalone years are NOT tags.
- NO bare section numbers, NO reference numbers, NO generic legal boilerplate (memorandum of association, articles of association).{exclusion_hint}{already_hint}"""

        return prompt

    def _select_best_tags(
        self,
        tags: List[str],
        num_tags: int,
        **kwargs
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

            # 7-word maximum (allows "department of animal husbandry and dairying" style govt names)
            if len(words) > 7:
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
