import json
import os
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

def load_json_file(file_path: str, default: Dict = None) -> Dict:
    """Loads a JSON file, creating it with default content if it doesn't exist or is invalid."""
    if default is None:
        default = {}
    if not os.path.exists(file_path):
        logger.warning("%s does not exist. Creating with default content.", file_path)
        save_json_file(default, file_path)
        return default
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                logger.warning("%s is empty. Using default content.", file_path)
                return default
            data = json.loads(content)
        # Ensure top-level keys are strings, as JSON requires
        return {str(k): v for k, v in data.items()} if isinstance(data, dict) else default
    except (json.JSONDecodeError, PermissionError, OSError) as e:
        logger.error("Failed to load %s: %s. Using default.", file_path, e)
        return default

def save_json_file(data: Dict[str, Any], file_path: str) -> None:
    """Saves a dictionary to a JSON file."""
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        logger.debug("%s saved successfully.", file_path)
    except (PermissionError, OSError) as e:
        logger.error("Failed to save %s: %s", file_path, e)