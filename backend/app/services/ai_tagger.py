import openai
from typing import List, Dict, Any, Optional, Set
import re
import logging
import unicodedata

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
        
        self.client = openai.OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key
        )
    
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
            # CRITICAL: Always request MORE tags than needed to account for filtering
            # Filters that can reject tags:
            # 1. Gibberish detection (new)
            # 2. Generic terms filter
            # 3. Exclusion list filter
            # 4. ASCII validation
            # 5. Length validation
            # 
            # Strategy: Request 3x the amount to ensure we always have enough after filtering
            buffer_multiplier = 3.0  # Always use buffer, not just for exclusions
            requested_tags = int(num_tags * buffer_multiplier)
            
            logger.info(f"🎯 Target: {num_tags} tags | Requesting: {requested_tags} tags (3x buffer for filters)")
            logger.info(f"   Active filters: gibberish detection, generic terms, exclusion list ({len(self.exclusion_words)} words)")
            if language_name:
                logger.info(f"🌐 Document language: {language_name} ({detected_language})")
            if quality_info:
                logger.info(f"📊 Document quality: {quality_info.get('quality_tier', 'unknown')} ({quality_info.get('type', 'unknown')})")

            prompt = self._build_prompt(
                title,
                description,
                content,
                requested_tags,
                detected_language,
                language_name,
                quality_info
            )
            
            try:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {
                            "role": "system", 
                            "content": """You are a multilingual document tagging expert for Indian government documents.

LANGUAGE SUPPORT: You understand ALL Indian languages including:
- Devanagari script: Hindi, Marathi, Sanskrit
- Bengali/Assamese script
- Gurmukhi script: Punjabi
- Gujarati script
- Oriya (Odia) script
- Tamil script
- Telugu script
- Kannada script
- Malayalam script
- English and mixed-language documents

YOUR TASK: 
1. Read and understand the document in its native language(s)
2. Extract key concepts, topics, and themes
3. Generate CONCISE TAGS (1-3 words each, hyphenated if needed)
4. Tags should be KEYWORDS, not sentences or long phrases
5. Generate the EXACT number of tags requested (this is critical!)
6. ALWAYS generate tags in ENGLISH ONLY (translate concepts from any language to English)
7. Return ONLY comma-separated lowercase English tags for universal searchability

TAG FORMAT RULES:
✓ Single concept tags: "scholarship", "employment", "census"
✓ Multi-word tags: Use hyphens: "sc-welfare", "annual-report", "skill-training"
✓ Maximum 3 words per tag (prefer 1-2 words)
✓ Think KEYWORDS not PHRASES
✗ NO long phrases: "dr ambedkar foundation annual report 2015" is TOO LONG

OUTPUT FORMAT: comma-separated tags only, nothing else"""
                        },
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=400,
                    temperature=0.2
                )
            except UnicodeEncodeError as e:
                logger.error(f"❌ Unicode encoding error in API call: {e}")
                logger.warning(f"⚠️ Error at position {e.start if hasattr(e, 'start') else 'unknown'}")
                
                # Log the problematic character if possible
                if hasattr(e, 'object') and hasattr(e, 'start'):
                    try:
                        problematic_char = e.object[e.start:e.start+10]
                        logger.error(f"Problematic text: {repr(problematic_char)}")
                    except:
                        pass
                
                # Safer fallback strategy: Remove only problematic characters, keep Indic content
                logger.info("🔄 Retrying with safer Unicode cleanup...")
                logger.warning("⚠️ Applying additional sanitization while preserving Indic scripts")

                # Clean by removing ONLY control characters, not all non-ASCII
                def safe_clean(text):
                    cleaned = ''
                    for char in text:
                        cat = unicodedata.category(char)
                        # Keep everything except control characters (except whitespace)
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
                            "content": "You are a document tagging expert. Generate ENGLISH tags only. Return comma-separated lowercase tags."
                        },
                        {"role": "user", "content": prompt_safe}
                    ],
                    max_tokens=400,
                    temperature=0.2
                )
            
            # Parse response
            tags_text = response.choices[0].message.content.strip()
            logger.info(f"Raw AI response: '{tags_text}'")
            
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
            
            # Check if we have enough tags
            if len(tags_after_exclusion) < num_tags:
                logger.warning(f"⚠️ INSUFFICIENT TAGS: Got {len(tags_after_exclusion)}, need {num_tags}")
                logger.warning(f"   Requested: {requested_tags} → Parsed: {len(tags_parsed)} → After filters: {len(tags_after_exclusion)}")
                logger.warning(f"   Rejection rate: {((requested_tags - len(tags_after_exclusion)) / requested_tags * 100):.1f}%")
            
                # If we have at least 50% of requested, use what we have
                # Otherwise, this indicates a serious problem
                if len(tags_after_exclusion) < num_tags * 0.5:
                    logger.error(f"❌ CRITICAL: Less than 50% of requested tags survived filtering!")
                    logger.error(f"   This indicates overly aggressive filtering or poor AI output quality")
            
            # Take exactly the number requested (or all we have if less)
            final_tags = tags_after_exclusion[:num_tags]
            
            # Pad with best remaining tags if we're short
            if len(final_tags) < num_tags and len(tags_after_exclusion) < num_tags:
                shortage = num_tags - len(final_tags)
                logger.warning(f"⚠️ SHORT {shortage} tags! Returning {len(final_tags)} instead of {num_tags}")
            
            logger.info(f"✅ Final: {len(final_tags)}/{num_tags} tags: {final_tags}")
            
            tokens_used = 0
            if response.usage:
                tokens_used = response.usage.total_tokens
            
            return {
                "success": True,
                "tags": final_tags,
                "raw_response": tags_text,
                "tokens_used": tokens_used,
                "tags_requested": num_tags,
                "tags_returned": len(final_tags),
                "tags_parsed": len(tags_parsed),
                "filtering_stats": {
                    "requested_from_ai": requested_tags,
                    "parsed": len(tags_parsed),
                    "after_exclusions": len(tags_after_exclusion),
                    "final": len(final_tags),
                    "rejection_rate": f"{((requested_tags - len(final_tags)) / requested_tags * 100):.1f}%"
                }
            }
            
        except openai.AuthenticationError:
            return {
                "success": False,
                "error": "Invalid API key. Please check your OpenRouter API key.",
                "tags": []
            }
        except openai.RateLimitError as e:
            error_msg = str(e)
            if "429" in error_msg:
                return {
                    "success": False,
                    "error": "Rate limit exceeded. Free models have request limits. Try: 1) Wait a minute and retry, 2) Use a different model, or 3) Add credits to your OpenRouter account.",
                    "tags": []
                }
            return {
                "success": False,
                "error": f"Rate limit exceeded: {error_msg}",
                "tags": []
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
            'annual_report': 'FOCUS: organization name, year/period, key programs, achievements, beneficiary counts, schemes implemented',
            'budget': 'FOCUS: budget heads, ministry/department, financial year, major schemes, allocation categories, expenditure types',
            'scheme': 'FOCUS: scheme name/acronym, beneficiary type, eligibility criteria, benefits offered, implementing agency',
            'newsletter': 'FOCUS: period (month/quarter), events covered, announcements, activities, celebrations',
            'legal': 'FOCUS: act name, notification number, sections, amendment year, jurisdiction',
            'tender': 'FOCUS: tender number, procurement type, department, deadline date, item/service category',
            'policy': 'FOCUS: policy name, ministry, implementation date, target beneficiaries, key provisions',
            'general': 'FOCUS: main entities, key topics, time periods, specific programs/initiatives mentioned'
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
    
    def _build_prompt(
        self,
        title: str,
        description: str,
        content: str,
        num_tags: int,
        detected_language: Optional[str] = None,
        language_name: Optional[str] = None,
        quality_info: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Build optimized prompt - 60% shorter, more effective, document-type aware
        
        Key improvements:
        - Document type detection for specialized prompting
        - Quality-aware instructions
        - Positive framing (show good examples, not bad)
        - Clear hierarchy (TASK → RULES → EXAMPLES)
        - Removed repetition
        """
        # Sanitize inputs
        title = self._sanitize_text_for_api(title)
        description = self._sanitize_text_for_api(description)
        content = self._sanitize_text_for_api(content)
        
        # Detect document type for targeted prompting
        doc_type = self._detect_document_type(title, description, content)
        type_guidance = self._get_document_type_guidance(doc_type)
        
        # Truncate content intelligently
        content_preview = content[:1800] if len(content) > 1800 else content
        
        # Build language context (concise)
        language_hint = ""
        if language_name and detected_language != 'en':
            language_hint = f" [Document in {language_name} - translate key terms to English]"
        
        # Quality-based adjustments
        quality_hint = self._get_quality_adjusted_instruction(quality_info)
        
        # Exclusion list (show first 10, not 15 - save tokens)
        exclusion_hint = ""
        if self.exclusion_words:
            sample_excluded = list(self.exclusion_words)[:10]
            exclusion_hint = f"\n❌ AVOID: {', '.join(sample_excluded)}" + \
                           (f" + {len(self.exclusion_words) - 10} more" if len(self.exclusion_words) > 10 else "")
        
        # BUILD OPTIMIZED PROMPT (60% shorter)
        prompt = f"""Generate {num_tags} precise English metadata tags for this document.{language_hint}{quality_hint}

DOCUMENT:
Title: {title}
{f'Description: {description}' if description else ''}

Content:
{content_preview}

TAGGING STRATEGY:
{type_guidance}{exclusion_hint}

RULES:
1. LENGTH: 1-3 words max, hyphenated (e.g., "annual-report-2015", "sc-welfare")
2. SPECIFICITY: Extract entities, programs, dates, locations - NOT generic descriptors
3. SEARCHABLE: Each tag = a keyword someone would search
4. ENGLISH ONLY: Translate non-English concepts

GOOD EXAMPLES by category:
• Entities: "ambedkar-foundation", "ncsc", "ministry-social-justice"
• Programs: "pmkvy", "post-matric-scholarship", "skill-training" 
• Doc type: "annual-report-2015", "budget-2024-25", "newsletter-q4"
• Beneficiaries: "sc-students", "obc-artisans", "divyang-persons"
• Topics: "legal-aid", "employment-generation", "grievance-redressal"
• Events: "ravidas-jayanti-2016", "awareness-campaign-march"

NEVER USE:
• Generic terms: "government", "ministry", "document", "contact"
• Metadata: "hindi-document", "pdf", "publication"
• Long phrases: "dr ambedkar foundation annual report" → SPLIT to ["ambedkar-foundation", "annual-report-2015"]

OUTPUT: Exactly {num_tags} comma-separated lowercase tags. No explanations."""
        
        return prompt
    
    def _is_gibberish_tag(self, tag: str) -> bool:
        """
        Detect if a tag is gibberish/nonsensical
        
        Returns True if tag appears to be garbage OCR output
        Uses CONSERVATIVE thresholds to avoid rejecting valid tags
        """
        if len(tag) < 3:
            return False
        
        # Count vowels (including 'y' which can act as vowel)
        vowels = sum(1 for c in tag if c in 'aeiouy')
        letters = sum(1 for c in tag if c.isalpha())
        
        if letters < 3:
            return False
        
        vowel_ratio = vowels / letters
        
        # Check for EXTREMELY low vowel ratio (likely gibberish)
        # Made more conservative: was 0.15, now 0.10 (10%)
        if vowel_ratio < 0.10:
            logger.warning(f"🚫 Tag '{tag}' rejected: too few vowels ({vowel_ratio:.2%})")
            return True
        
        # Check for excessive consonant clusters
        # Made more conservative: was 4+, now 5+ consonants in a row
        consonant_clusters = re.findall(r'[bcdfghjklmnpqrstvwxz]{5,}', tag)
        if consonant_clusters:
            logger.warning(f"🚫 Tag '{tag}' rejected: extreme consonant cluster {consonant_clusters}")
            return True
        
        # Check for completely unpronounceable patterns
        # Made more conservative: was 4, now 6 consonants
        parts = re.split(r'[aeiouy]+', tag)
        for part in parts:
            if len(part) > 6:
                logger.warning(f"🚫 Tag '{tag}' rejected: unpronounceable ({part})")
                return True
        
        return False
    
    def _parse_tags(self, tags_text: str, expected_count: int) -> List[str]:
        """Parse and clean tags from AI response (English only output)"""
        logger.info(f"Parsing tags from: '{tags_text}'")
        
        # Generic/useless terms to automatically filter out (both spaced and hyphenated versions)
        GENERIC_TERMS = {
            'contact details', 'contact-details', 'contact information', 'contact-information', 'contact info', 'contact-info',
            'delhi address', 'delhi-address', 'address', 'office address', 'office-address', 'phone number', 'phone-number', 'email',
            'hindi document', 'hindi-document', 'hindi language', 'hindi-language', 'english document', 'english-document', 'language',
            'publication', 'document', 'report', 'information',
            'government organization', 'government-organization', 'organization', 'ministry', 'department', 'foundation',
            'social welfare', 'social-welfare', 'empowerment', 'development',
            'details', 'information', 'data',
            'office location', 'office-location', 'headquarters', 'contact',
            'annual report', 'annual-report', 'newsletter',  # Too generic without year
            'government', 'india', 'organization details', 'organization-details',
            'publication date', 'publication-date', 'published', 'pdf', 'document type', 'document-type'
        }
        
        # Remove any markdown formatting
        tags_text = tags_text.replace('```', '').replace('*', '').replace('`', '').replace('"', '').strip()
        
        # Remove common prefixes that AI might add
        prefixes_to_remove = ['tags:', 'here are', 'the tags are:', 'generated tags:', 'output:']
        tags_text_lower = tags_text.lower()
        for prefix in prefixes_to_remove:
            if tags_text_lower.startswith(prefix):
                tags_text = tags_text[len(prefix):].strip()
                logger.info(f"Removed prefix '{prefix}', remaining: '{tags_text}'")
        
        # Split by comma, semicolon, or newline
        if ',' in tags_text:
            tags = [tag.strip() for tag in tags_text.split(',')]
        elif ';' in tags_text:
            tags = [tag.strip() for tag in tags_text.split(';')]
        else:
            tags = [tag.strip() for tag in tags_text.split('\n')]
        
        logger.info(f"Split into {len(tags)} tags: {tags}")
        
        # Clean and validate tags (English only)
        valid_tags = []
        rejected_generic = []
        
        for tag in tags:
            if not tag:
                continue
                
            # Clean the tag
            original_tag = tag
            tag = tag.lower().strip()
            
            # Remove leading numbers/bullets
            tag = re.sub(r'^[\d\.\-\)\]\s]+', '', tag)
            
            # Keep only English alphanumeric, spaces, and hyphens
            tag = re.sub(r'[^\w\s\-]', '', tag)
            
            # Normalize whitespace
            tag = re.sub(r'\s+', ' ', tag).strip()
            
            # Only log if tag changed significantly during cleaning
            if original_tag != tag:
                logger.debug(f"Cleaned tag: '{original_tag}' -> '{tag}'")
            
            # Check word count - reject tags with 4+ words (too phrase-like)
            words = tag.split()
            if len(words) > 3:
                logger.warning(f"🚫 Tag rejected (too long - {len(words)} words): '{tag}'")
                logger.info(f"   💡 Suggestion: Split into separate tags")
                rejected_generic.append(tag)
                continue
            
            # Auto-hyphenate multi-word tags (2-3 words) if not already hyphenated
            if len(words) >= 2 and '-' not in tag:
                original_unhyphenated = tag
                tag = '-'.join(words)
                logger.debug(f"Auto-hyphenated: '{original_unhyphenated}' → '{tag}'")
            
            # Check if tag is gibberish
            if self._is_gibberish_tag(tag):
                rejected_generic.append(tag)
                continue
            
            # Check if tag is too generic
            if tag in GENERIC_TERMS:
                logger.warning(f"Tag rejected (too generic): '{tag}'")
                rejected_generic.append(tag)
                continue
            
            # Check if tag contains only generic terms (single words)
            tag_words = tag.replace('-', ' ').split()  # Split by hyphen or space for checking
            if len(tag_words) == 1 and tag in ['hindi', 'english', 'contact', 'address', 'document', 
                                                'report', 'publication', 'information', 'details',
                                                'government', 'organization', 'ministry', 'foundation',
                                                'pdf', 'file', 'office', 'email', 'phone']:
                logger.warning(f"🚫 Tag rejected (single generic word): '{tag}'")
                rejected_generic.append(tag)
                continue
            
            # Validate: must be ASCII/English only
            if tag and all(ord(c) < 128 for c in tag):
                if len(tag) >= 2 and len(tag) <= 100 and tag not in valid_tags:
                    valid_tags.append(tag)
                    logger.debug(f"✓ '{tag}'")
                else:
                    if len(tag) < 2:
                        logger.debug(f"✗ '{tag}' (too short)")
                    elif len(tag) > 100:
                        logger.debug(f"✗ '{tag}' (too long)")
                    elif tag in valid_tags:
                        logger.debug(f"✗ '{tag}' (duplicate)")
            else:
                logger.debug(f"✗ '{tag}' (non-ASCII)")
        
        if rejected_generic:
            logger.info(f"🚫 Rejected {len(rejected_generic)} filtered tags: {rejected_generic[:5]}{'...' if len(rejected_generic) > 5 else ''}")
        
        logger.info(f"📊 Parsed result: {len(valid_tags)} valid tags from {len(tags)} candidates")
        
        # Return ALL valid tags (don't limit here - let caller decide)
        # This ensures we have maximum tags available for the final selection
        return valid_tags
    
    def _filter_excluded_tags(self, tags: List[str]) -> List[str]:
        """
        Filter out tags that match exclusion words
        Uses substring matching to catch variations
        
        For example, if "social-justice" is excluded:
        - "social-justice" (exact) -> excluded
        - "ministry-of-social-justice" (contains) -> excluded
        - "social justice programs" (contains) -> excluded
        
        Args:
            tags: List of tags to filter
            
        Returns:
            Filtered list of tags with exclusions removed
        """
        filtered_tags = []
        
        for tag in tags:
            tag_lower = tag.lower().strip()
            # Normalize: replace spaces with hyphens for comparison
            tag_normalized = tag_lower.replace(' ', '-')
            
            # Check if tag should be excluded
            excluded = False
            for excluded_word in self.exclusion_words:
                excluded_normalized = excluded_word.replace(' ', '-')
                
                # Check both directions for substring match
                if excluded_normalized in tag_normalized or tag_normalized in excluded_normalized:
                    logger.info(f"Excluding tag '{tag}' (matches exclusion term '{excluded_word}')")
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
