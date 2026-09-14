import json
import logging
import re
from typing import Any, Dict, List, Union

logger = logging.getLogger("vetra.utils.json_utils")


def safe_json_loads(text: Union[str, bytes, None]) -> Union[Dict[str, Any], List[Any]]:
    """Safely parse JSON from LLM output, handling:
    1. Markdown code blocks (```json ... ``` or ``` ...)
    2. Leading/trailing commentary, conversational filler, or whitespace
    3. Common JSON formatting anomalies
    """
    if not text:
        raise ValueError("Cannot parse empty or None JSON string.")

    if isinstance(text, bytes):
        text = text.decode("utf-8", errors="replace")

    cleaned = text.strip()

    # 1. Strip Markdown code fences: ```json ... ``` or ``` ... ```
    if cleaned.startswith("```"):
        match = re.search(r"^```(?:json)?\s*\n?(.*?)\n?```$", cleaned, re.DOTALL | re.IGNORECASE)
        if match:
            cleaned = match.group(1).strip()
        else:
            lines = cleaned.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()

    # 2. Try standard json.loads
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # 3. Extract JSON object {...} or array [...] if surrounded by text/thought
    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")
    first_bracket = cleaned.find("[")
    last_bracket = cleaned.rfind("]")

    if first_brace != -1 and (first_bracket == -1 or first_brace < first_bracket):
        if last_brace != -1 and last_brace > first_brace:
            candidate = cleaned[first_brace : last_brace + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass

    if first_bracket != -1 and (first_brace == -1 or first_bracket < first_brace):
        if last_bracket != -1 and last_bracket > first_bracket:
            candidate = cleaned[first_bracket : last_bracket + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass

    # 4. Remove trailing commas before closing braces/brackets and retry
    subbed = re.sub(r",\s*([}\]])", r"\1", cleaned)
    try:
        return json.loads(subbed)
    except json.JSONDecodeError as err:
        logger.error(f"Failed to safe_json_loads text. Length: {len(text)}. Error: {err}")
        raise
