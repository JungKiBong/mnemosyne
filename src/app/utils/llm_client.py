"""
LLM Client Wrapper
Unified OpenAI format API calls
Supports Ollama num_ctx parameter to prevent prompt truncation
"""

import json
import os
import re
import threading
from typing import Optional, Dict, Any, List
from openai import OpenAI

from ..config import Config


class LLMClient:
    """LLM Client"""

    _clients: Dict[str, OpenAI] = {}
    _lock = threading.Lock()

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 300.0
    ):
        self.api_key = api_key or Config.LLM_API_KEY
        self.base_url = base_url or Config.LLM_BASE_URL
        self.model = model or Config.LLM_MODEL_NAME

        if not self.api_key:
            raise ValueError("LLM_API_KEY not configured")

        client_key = f"{self.base_url}_{self.api_key}_{timeout}"
        
        with self._lock:
            if client_key not in self._clients:
                self._clients[client_key] = OpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url,
                    timeout=timeout,
                )
        self.client = self._clients[client_key]

        # Ollama context window size — prevents prompt truncation.
        # Read from env OLLAMA_NUM_CTX, default 8192 (Ollama default is only 2048).
        self._num_ctx = int(os.environ.get('OLLAMA_NUM_CTX', '8192'))

    def _is_ollama(self) -> bool:
        """Check if we're talking to an Ollama server.
        
        Uses LLM_PROVIDER env var as primary signal (explicit config wins).
        Falls back to URL heuristic only when provider is unset.
        """
        provider = os.environ.get('LLM_PROVIDER', '').lower()
        if provider:
            return provider == 'ollama'
        # Fallback heuristic: Ollama default port or hostname
        url = (self.base_url or '').lower()
        return '11434' in url or 'ollama' in url

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: Optional[Dict] = None
    ) -> str:
        """
        Send chat request

        Args:
            messages: Message list
            temperature: Temperature parameter
            max_tokens: Max token count
            response_format: Response format (e.g., JSON mode)

        Returns:
            Model response text
        """
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if response_format:
            kwargs["response_format"] = response_format

        # For Ollama: pass num_ctx via extra_body to prevent prompt truncation
        if self._is_ollama() and self._num_ctx:
            kwargs["extra_body"] = {
                "options": {"num_ctx": self._num_ctx}
            }

        response = self.client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content
        # Some models (like MiniMax M2.5) include <think>thinking content in response, need to remove
        content = re.sub(r'<think>[\s\S]*?</think>', '', content).strip()
        return content

    def chat_json(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4096
    ) -> Dict[str, Any]:
        """
        Send chat request and return JSON

        Args:
            messages: Message list
            temperature: Temperature parameter
            max_tokens: Max token count

        Returns:
            Parsed JSON object
        """
        response = self.chat(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"}
        )
        
        # Robust JSON extraction
        cleaned_response = response.strip()
        
        # 1. Remove optional <think> blocks
        cleaned_response = re.sub(r'<think>[\s\S]*?</think>', '', cleaned_response).strip()
        
        # 2. Try to extract markdown JSON block
        md_match = re.search(r'```(?:json)?\s+([\s\S]*?)\s+```', cleaned_response, re.IGNORECASE)
        if md_match:
            cleaned_response = md_match.group(1).strip()
        else:
            # 3. Fallback: find first { or [ and last } or ]
            start_idx = cleaned_response.find('{')
            array_start = cleaned_response.find('[')
            
            if start_idx != -1 and array_start != -1:
                start_idx = min(start_idx, array_start)
            elif start_idx == -1:
                start_idx = array_start
                
            if start_idx != -1:
                end_char = '}' if cleaned_response[start_idx] == '{' else ']'
                end_idx = cleaned_response.rfind(end_char)
                if end_idx != -1 and end_idx > start_idx:
                    cleaned_response = cleaned_response[start_idx:end_idx+1].strip()

        try:
            return json.loads(cleaned_response)
        except json.JSONDecodeError:
            raise ValueError(f"Invalid JSON format from LLM: {response}")
