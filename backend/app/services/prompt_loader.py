"""Prompt loader for meeting analysis."""
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Directory containing prompt files
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

# Prompt files in order of assembly
PROMPT_FILES = [
    "base_system.txt",
    "overall_score.txt",
    "sentiment.txt",
    "topics.txt",
    "action_items.txt",
    "engagement.txt",
    "effectiveness.txt",
    "summary.txt",
    "insights.txt",
    "recommendations.txt",
]

# JSON schema instruction appended to the end
JSON_SCHEMA = """
OUTPUT JSON STRUCTURE:
{
    "overall_score": <float 1.0-10.0>,
    "sentiment": "<positive|negative|neutral>",
    "key_topics": ["<topic1>", "<topic2>", ...],
    "action_items": ["<item1>", "<item2>", ...],
    "participants": ["<speaker1>", "<speaker2>", ...],
    "engagement_score": <float 1.0-10.0>,
    "meeting_effectiveness": <float 1.0-10.0>,
    "summary": "<2-4 sentence summary>",
    "insights": ["<insight1>", "<insight2>", ...],
    "recommendations": ["<rec1>", "<rec2>", ...]
}

Remember: Return ONLY the JSON object. No markdown, no explanations.
"""


def load_analysis_prompts() -> str:
    """Load and concatenate all prompt files into a single system prompt.

    Returns:
        Combined prompt string with all analysis instructions.
    """
    parts = []

    for filename in PROMPT_FILES:
        filepath = PROMPTS_DIR / filename
        try:
            content = filepath.read_text().strip()
            parts.append(content)
        except FileNotFoundError:
            logger.warning(f"Prompt file not found: {filepath}")
        except Exception as e:
            logger.error(f"Error reading prompt file {filepath}: {e}")

    # Combine all prompts with double newlines
    combined = "\n\n".join(parts)

    # Append JSON schema instruction
    combined += "\n\n" + JSON_SCHEMA.strip()

    return combined


def load_single_prompt(filename: str) -> str:
    """Load a single prompt file.

    Args:
        filename: Name of the prompt file (e.g., 'summary.txt')

    Returns:
        Content of the prompt file.
    """
    filepath = PROMPTS_DIR / filename
    try:
        return filepath.read_text().strip()
    except FileNotFoundError:
        logger.error(f"Prompt file not found: {filepath}")
        raise
    except Exception as e:
        logger.error(f"Error reading prompt file {filepath}: {e}")
        raise
