"""Import bridge for the hyphenated ai-engine source directory."""
import importlib.util
from pathlib import Path
_path = Path(__file__).parent / "ai-engine" / "provider.py"
_spec = importlib.util.spec_from_file_location("natqai_ai_provider", _path)
_module = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(_module)
OpenAICompatibleProvider = _module.OpenAICompatibleProvider
AIProviderError = _module.AIProviderError
