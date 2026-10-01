from .base import EngineAdapter
from .sglang import SGLangAdapter
from .vllm import VLLMAdapter


def get_engine(name: str) -> EngineAdapter:
    normalized = name.lower()
    if normalized == "vllm":
        return VLLMAdapter()
    if normalized == "sglang":
        return SGLangAdapter()
    raise ValueError(f"unsupported engine {name!r}; expected vllm or sglang")


__all__ = ["EngineAdapter", "SGLangAdapter", "VLLMAdapter", "get_engine"]
