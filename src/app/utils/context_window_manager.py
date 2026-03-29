"""
Context Window Manager for TurboQuant Architecture
Handles large-scale subgraph context injection and token length estimation.
"""

from typing import List, Dict, Any, Optional
import json

class ContextWindowManager:
    """
    Manages the LLM context window to prevent exceeding max_model_len
    while maximizing the amount of injected graph context.
    
    Optimized for Phase 2 (vLLM / TurboQuant hybrid mode: 115K tokens)
    """
    
    def __init__(self, max_tokens: int = 115000, safety_margin: int = 4000):
        """
        Args:
            max_tokens: The absolute limit of tokens the model can handle (e.g. 115K for TurboQuant 3090)
            safety_margin: Tokens reserved for system prompts and user queries
        """
        self.max_tokens = max_tokens
        self.safety_margin = safety_margin
        self.available_tokens = self.max_tokens - self.safety_margin
        
    def estimate_tokens(self, text: str) -> int:
        """
        Rough token estimation without loading huge tokenizers.
        Rule of thumb: 1 token ≈ 4 characters in English, slightly different for Korean/JSON.
        We'll use a conservative factor: 1 token ≈ 2.5 chars on average for mixed text.
        """
        if not text:
            return 0
        return len(text) // 2
        
    def pack_context(self, items: List[Any], format_fn=str) -> str:
        """
        Packs as many items as possible into the available token limit.
        Returns the concatenated string of injected items.
        
        Args:
            items: List of graph nodes/edges/facts
            format_fn: Function to convert an item to text
        """
        packed_text = ""
        current_tokens = 0
        
        for item in items:
            item_text = format_fn(item) + "\n\n"
            estimated = self.estimate_tokens(item_text)
            
            if current_tokens + estimated > self.available_tokens:
                break
                
            packed_text += item_text
            current_tokens += estimated
            
        return packed_text.strip()
