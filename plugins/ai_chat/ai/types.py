"""AI Chat 通用类型（UTF-8）\n\n用于模块间传递轻量的多模态结果容器。\n"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class ChatResult:
    """Represents a multimodal chat result.

    - text: plain text reply
    - images: list of image paths or URLs
    - audios: list of audio paths or URLs
    - extras: additional metadata
    """

    text: str = ""
    images: List[str] = field(default_factory=list)
    audios: List[str] = field(default_factory=list)
    extras: Dict[str, object] = field(default_factory=dict)

    @classmethod
    def from_text(cls, text: str) -> "ChatResult":
        return cls(text=text or "")


