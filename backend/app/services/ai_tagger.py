import openai
from typing import List, Dict, Any, Optional, Set
import re
import logging

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
        num_tags: int = 8
    ) -> Dict[str, Any]:
        """
        Generate tags for document with exclusion filtering
        
        Args:
            title: Document title
            description: Document description
            content: Extracted text content
            num_tags: Number of tags to generate (exact number will be returned after filtering)
            
        Returns:
            dict with tags list and metadata
        """
        try:
            # Calculate buffer: request more tags than needed to account for exclusions
            # We request 2x the number to ensure we have enough after filtering
            buffer_multiplier = 2.5 if self.exclusion_words else 1.0
            requested_tags = int(num_tags * buffer_multiplier)
            
            logger.info(f"Requesting {requested_tags} tags (target: {num_tags}, exclusion list size: {len(self.exclusion_words)})")
            
            prompt = self._build_prompt(title, description, content, requested_tags)
            
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {
                        "role": "system", 
                        "content": "You are a multilingual document tagging expert for Indian government documents. You understand both English and Hindi (Devanagari script). ALWAYS generate tags in ENGLISH ONLY, even if the document is in Hindi or other languages. Translate concepts to English for universal searchability. Return ONLY comma-separated lowercase English tags, nothing else."
                    },
                    {"role": "user", "content": prompt}
                ],
                max_tokens=400,
                temperature=0.2
            )
            
            # Parse response
            tags_text = response.choices[0].message.content.strip()
            logger.info(f"Raw AI response: '{tags_text}'")
            
            # Parse with buffer amount
            tags = self._parse_tags(tags_text, requested_tags)
            logger.info(f"Parsed {len(tags)} tags before exclusion filtering: {tags}")
            
            # Apply exclusion filter if needed
            if self.exclusion_words:
                original_count = len(tags)
                tags = self._filter_excluded_tags(tags)
                logger.info(f"After exclusion filtering: {len(tags)} tags (removed {original_count - len(tags)})")
            
            # Trim to exact requested number
            tags = tags[:num_tags]
            logger.info(f"Final tags (trimmed to {num_tags}): {tags}")
            
            tokens_used = 0
            if response.usage:
                tokens_used = response.usage.total_tokens
            
            return {
                "success": True,
                "tags": tags,
                "raw_response": tags_text,
                "tokens_used": tokens_used
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
    
    def _build_prompt(
        self, 
        title: str, 
        description: str, 
        content: str, 
        num_tags: int
    ) -> str:
        """Build prompt for AI with exclusion guidance"""
        # Truncate content if too long
        content_preview = content[:1500] if len(content) > 1500 else content
        
        # Add exclusion guidance if we have an exclusion list
        exclusion_guidance = ""
        if self.exclusion_words:
            sample_excluded = list(self.exclusion_words)[:15]  # Show first 15 as examples
            exclusion_guidance = f"""
⚠️ EXCLUDED TERMS - DO NOT USE THESE IN YOUR TAGS:
The following common/generic terms should be AVOIDED:
{', '.join(sample_excluded)}
{f'... and {len(self.exclusion_words) - 15} more excluded terms' if len(self.exclusion_words) > 15 else ''}

Generate tags that are SPECIFIC and UNIQUE to this document, avoiding all these common terms.
"""
        
        prompt = f"""You are analyzing an Indian government/organizational document. Generate exactly {num_tags} highly SPECIFIC and DESCRIPTIVE meta-data tags in English.
{exclusion_guidance}

Document Title: {title}
Description: {description if description else 'N/A'}

Content Preview:
{content_preview}

TAGGING STRATEGY - Be SPECIFIC, not generic:

1. ORGANIZATION/MINISTRY (if mentioned):
   - Identify the specific ministry, department, or organization
   - Examples: "ministry of social justice", "dr ambedkar foundation", "ncsc"

2. DOCUMENT TYPE (be specific):
   - Don't just say "annual report" - add context
   - Examples: "annual report 2019-20", "quarterly newsletter", "policy document"

3. MAIN TOPICS/THEMES (specific subjects):
   - Identify actual topics discussed
   - Examples: "backward classes welfare", "legal aid services", "digital literacy programs"
   - NOT generic terms like "government policy"

4. KEY PEOPLE/FIGURES (if mentioned):
   - Examples: "dr br ambedkar", "sant ravidas", specific ministers

5. LOCATIONS/REGIONS (if relevant):
   - Specific states, regions, or areas mentioned

6. TIME PERIOD (specific dates/years):
   - Examples: "2019-20", "february 2016", "31st january"

7. PROGRAMS/SCHEMES (specific names):
   - Actual program names mentioned

8. TARGET GROUPS (if specified):
   - Examples: "scheduled castes", "obc communities", "divyang persons"

AVOID THESE GENERIC TAGS:
❌ "government policy", "organization details", "contact information", "document type", "legal system", "date 2016"

USE THESE SPECIFIC TAGS:
✅ "social justice ministry", "ravidas jayanti 2016", "sc welfare schemes", "legal aid for marginalized", "february 2016 newsletter"

Output Format:
- ONLY comma-separated tags
- ALL tags in lowercase English
- {num_tags} tags exactly
- NO explanations, NO numbering

Tags:"""
        
        return prompt
    
    def _parse_tags(self, tags_text: str, expected_count: int) -> List[str]:
        """Parse and clean tags from AI response (English only output)"""
        logger.info(f"Parsing tags from: '{tags_text}'")
        
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
            
            logger.info(f"Cleaned tag: '{original_tag}' -> '{tag}' (length: {len(tag)})")
            
            # Validate: must be ASCII/English only
            if tag and all(ord(c) < 128 for c in tag):
                if len(tag) >= 2 and len(tag) <= 100 and tag not in valid_tags:
                    valid_tags.append(tag)
                    logger.info(f"Tag accepted: '{tag}'")
                else:
                    logger.info(f"Tag rejected: '{tag}' (length: {len(tag)}, duplicate: {tag in valid_tags})")
            else:
                logger.info(f"Tag rejected (non-ASCII): '{tag}'")
        
        logger.info(f"Final valid tags ({len(valid_tags)}): {valid_tags}")
        
        # Limit to expected count
        result = valid_tags[:expected_count]
        logger.info(f"Returning {len(result)} tags: {result}")
        return result
    
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
