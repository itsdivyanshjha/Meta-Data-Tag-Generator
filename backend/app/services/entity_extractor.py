"""
Entity Extractor — LLM-based structured entity extraction

Pre-processing step that extracts grounded, real entities from document text
before sending to the AI tagger. This gives the tagger LLM real facts to work
with instead of guessing tags from a short text snippet.

Key difference from the tagger: this sees up to 15,000 chars of the document
(3x more than the tagger's 5,000 char preview), so it captures entities from
the full body — not just headers and boilerplate.

Uses the existing OpenRouter/openai SDK — no extra dependencies.
Uses the user's chosen model — no hardcoded model defaults.
"""

import json
import logging
import re
import time
from typing import Dict, Any, List, Optional

import openai

from app.config import settings

logger = logging.getLogger(__name__)


class EntityExtractor:
    """
    Extract structured entities from document text using an LLM call.

    Makes a single focused API call to extract named entities, then returns
    them grouped by category. Designed as a best-effort pre-processing step —
    failures are silent and never break the tagging pipeline.
    """

    SYSTEM_PROMPT = (
        "You are a document entity extraction expert. "
        "Extract all named entities and key identifiers from the given text. "
        "Always respond with valid JSON only — no prose, no markdown fences."
    )

    EXTRACTION_PROMPT = """Extract all named entities from this document text. Return a JSON object with these categories:

{{
  "document_type": ["what kind of document this is — e.g. question paper, sanction order, notification, circular, office memorandum, gazette, tender, report, minutes, letter"],
  "organization": ["government bodies, ministries, departments, commissions, corporations, agencies"],
  "program": ["schemes, yojanas, missions, initiatives, projects, campaigns"],
  "legislation": ["acts, rules, regulations, orders, notifications — include year if mentioned"],
  "person": ["named individuals with designation if mentioned"],
  "location": ["states, districts, cities specifically relevant to the document"],
  "topic": ["core subject areas, beneficiary groups, sectors, paper subjects"],
  "temporal": ["financial years, plan periods, specific dates tied to events"]
}}

Rules:
- "document_type" is REQUIRED — always identify what the document is.
- Use EXACT text from the document — do not paraphrase or invent.
- Include abbreviations when both full name and abbreviation appear (e.g. "Pradhan Mantri Anusuchit Jaati Abhyuday Yojana (PM-AJAY)").
- Omit empty categories (except document_type which is always required).
- If the document is in a non-English language, provide English translations of entity names.

EXAMPLE INPUT:
Government of India
Ministry of Social Justice and Empowerment
Department of Social Justice and Empowerment
(PM-AJAY Section)
Subject: Release of Central Assistance under Pradhan Mantri Anusuchit Jaati Abhyuday Yojana to Government of Telangana for Adarsh Gram Component during 2024-25.

EXAMPLE OUTPUT:
{{
  "document_type": ["sanction order", "grants-in-aid release"],
  "organization": ["Ministry of Social Justice and Empowerment", "Department of Social Justice and Empowerment", "Government of Telangana"],
  "program": ["Pradhan Mantri Anusuchit Jaati Abhyuday Yojana (PM-AJAY)", "Adarsh Gram Component"],
  "location": ["Telangana"],
  "topic": ["central assistance", "grants-in-aid"],
  "temporal": ["2024-25"]
}}

EXAMPLE INPUT:
NOTIFICATION
New Delhi, the 14th March, 2023
G.S.R. 192(E).—In exercise of the powers conferred by section 23 of the Rights of Persons with Disabilities Act, 2016, the Central Government hereby makes the following rules:
The National Commission for Scheduled Castes shall monitor the implementation of the Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Act, 1989.

EXAMPLE OUTPUT:
{{
  "document_type": ["gazette notification", "rules notification"],
  "organization": ["National Commission for Scheduled Castes"],
  "legislation": ["Rights of Persons with Disabilities Act, 2016", "Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Act, 1989"],
  "location": ["New Delhi"],
  "temporal": ["14th March, 2023"]
}}

EXAMPLE INPUT:
Civil Services (Main) Examination 2024
ODIA (Paper I) (LITERATURE)
Time Allowed: Three Hours
Maximum Marks: 250
Candidates should attempt questions from both Section A and Section B.

EXAMPLE OUTPUT:
{{
  "document_type": ["question paper", "examination paper"],
  "program": ["Civil Services (Main) Examination 2024"],
  "topic": ["odia literature", "paper I"],
  "temporal": ["2024"]
}}

---

DOCUMENT TEXT:
{text}"""

    def __init__(self, api_key: str, model_name: str):
        """
        Args:
            api_key: OpenRouter API key (from user's TaggingConfig)
            model_name: OpenRouter model ID (e.g. 'openai/gpt-4o-mini')
        """
        self.api_key = api_key
        self.model_name = model_name
        self.client = openai.OpenAI(
            base_url=settings.openrouter_base_url,
            api_key=api_key,
            timeout=openai.Timeout(
                timeout=settings.api_read_timeout,
                connect=settings.api_connect_timeout,
            ),
        )

    def extract_entities(
        self,
        text: str,
        max_chars: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Extract structured entities from document text.

        Args:
            text: Full extracted text from the document
            max_chars: Maximum characters to process (default from config)

        Returns:
            {
                "success": bool,
                "entities": [{"class": str, "text": str}, ...],
                "entity_summary": {"organization": [...], "program": [...], ...},
                "error": str | None
            }
        """
        empty_result = {
            "success": False,
            "entities": [],
            "entity_summary": {},
            "error": None
        }

        if not text or len(text.strip()) < 50:
            empty_result["error"] = "Text too short for entity extraction"
            return empty_result

        try:
            if max_chars is None:
                max_chars = settings.entity_extraction_max_chars

            # Send MORE text than the tagger sees — this is the key benefit.
            # The tagger gets ~5000 chars; entity extraction gets up to 15000.
            input_text = text[:max_chars]

            logger.info(
                f"Entity extraction: {len(input_text)} chars with {self.model_name}"
            )

            start_time = time.time()

            prompt = self.EXTRACTION_PROMPT.format(text=input_text)

            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=1000,
                temperature=0.1,  # Low temp for factual extraction
            )

            raw_response = response.choices[0].message.content.strip()
            elapsed = time.time() - start_time

            # Parse JSON from response (handle markdown fences if present)
            json_str = raw_response
            if "```" in json_str:
                match = re.search(r'```(?:json)?\s*(.*?)\s*```', json_str, re.DOTALL)
                if match:
                    json_str = match.group(1)

            entity_summary = json.loads(json_str)

            if not isinstance(entity_summary, dict):
                raise ValueError(f"Expected dict, got {type(entity_summary)}")

            # Clean: remove empty categories, deduplicate, build flat entity list
            cleaned_summary: Dict[str, List[str]] = {}
            entities: List[Dict[str, str]] = []

            for category, values in entity_summary.items():
                if not isinstance(values, list) or not values:
                    continue
                seen = set()
                clean_values = []
                for v in values:
                    if isinstance(v, str) and v.strip():
                        normalized = v.strip()
                        if normalized.lower() not in seen:
                            seen.add(normalized.lower())
                            clean_values.append(normalized)
                            entities.append({
                                "class": category,
                                "text": normalized
                            })
                if clean_values:
                    cleaned_summary[category] = clean_values

            tokens_used = response.usage.total_tokens if response.usage else 0

            logger.info(
                f"Entity extraction complete: {len(entities)} entities in "
                f"{elapsed:.1f}s ({tokens_used} tokens) - "
                + ", ".join(f"{k}={len(v)}" for k, v in cleaned_summary.items())
            )

            return {
                "success": True,
                "entities": entities,
                "entity_summary": cleaned_summary,
                "error": None
            }

        except json.JSONDecodeError as e:
            logger.warning(f"Entity extraction JSON parse failed: {e}")
            empty_result["error"] = f"JSON parse error: {e}"
            return empty_result
        except Exception as e:
            logger.warning(f"Entity extraction failed (non-fatal): {e}")
            empty_result["error"] = str(e)
            return empty_result
