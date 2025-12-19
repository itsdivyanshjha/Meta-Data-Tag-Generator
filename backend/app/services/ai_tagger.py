import openai
from typing import List, Dict, Any
import re


class AITagger:
    """Generate tags using OpenRouter API"""
    
    def __init__(self, api_key: str, model_name: str = "openai/gpt-4o-mini"):
        self.api_key = api_key
        self.model_name = model_name
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
        Generate tags for document
        
        Args:
            title: Document title
            description: Document description
            content: Extracted text content
            num_tags: Number of tags to generate
            
        Returns:
            dict with tags list and metadata
        """
        try:
            prompt = self._build_prompt(title, description, content, num_tags)
            
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {
                        "role": "system", 
                        "content": "You are a document tagging expert. Generate relevant, searchable tags for documents. Return ONLY comma-separated tags, nothing else."
                    },
                    {"role": "user", "content": prompt}
                ],
                max_tokens=200,
                temperature=0.3
            )
            
            # Parse response
            tags_text = response.choices[0].message.content.strip()
            tags = self._parse_tags(tags_text, num_tags)
            
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
        except openai.RateLimitError:
            return {
                "success": False,
                "error": "Rate limit exceeded. Please try again later.",
                "tags": []
            }
        except Exception as e:
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
        """Build prompt for AI"""
        # Truncate content if too long
        content_preview = content[:1500] if len(content) > 1500 else content
        
        prompt = f"""Generate exactly {num_tags} relevant meta-data tags for this document.

Document Title: {title}
Description: {description if description else 'N/A'}

Content Preview:
{content_preview}

Requirements:
- Generate exactly {num_tags} tags
- Tags should be lowercase
- Use single words or short 2-3 word phrases
- Focus on: document type, main topics, key themes, organizations mentioned, relevant dates/years
- Make tags useful for search and categorization
- Avoid generic tags like "document", "file", "pdf", "text"
- No special characters, only alphanumeric and spaces/hyphens

Return ONLY comma-separated tags, nothing else.
Example format: machine learning, data science, 2024, neural networks, python, tensorflow"""
        
        return prompt
    
    def _parse_tags(self, tags_text: str, expected_count: int) -> List[str]:
        """Parse and clean tags from AI response"""
        # Remove any markdown formatting
        tags_text = tags_text.replace('```', '').replace('*', '').replace('`', '').strip()
        
        # Remove common prefixes that AI might add
        prefixes_to_remove = ['tags:', 'here are', 'the tags are:', 'generated tags:']
        tags_text_lower = tags_text.lower()
        for prefix in prefixes_to_remove:
            if tags_text_lower.startswith(prefix):
                tags_text = tags_text[len(prefix):].strip()
        
        # Split by comma or newline
        if ',' in tags_text:
            tags = [tag.strip() for tag in tags_text.split(',')]
        else:
            tags = [tag.strip() for tag in tags_text.split('\n')]
        
        # Clean and validate tags
        valid_tags = []
        for tag in tags:
            # Clean the tag
            tag = tag.lower().strip()
            tag = re.sub(r'^[\d\.\-\)\]\s]+', '', tag)  # Remove leading numbers/bullets
            tag = re.sub(r'[^\w\s\-]', '', tag)  # Keep only alphanumeric, spaces, hyphens
            tag = re.sub(r'\s+', ' ', tag).strip()  # Normalize whitespace
            
            # Validate tag length and content
            if 2 <= len(tag) <= 50 and tag not in valid_tags:
                valid_tags.append(tag)
        
        # Limit to expected count
        return valid_tags[:expected_count]
    
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

