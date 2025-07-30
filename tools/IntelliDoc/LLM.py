"""LLM wrapper module providing compatibility with llama_index-style interfaces.

This module provides a wrapper around RamaLama for legacy compatibility
with code that expects llama_index-style interfaces.
"""

from typing import Iterator, Any, Dict, Optional
from .RamalamaClient import RamaLama


class LLM:
    """LLM wrapper providing llama_index-style compatibility.
    
    This class wraps RamaLama to provide compatibility with existing
    code that expects llama_index-style interfaces.
    """
    
    def __init__(self, model: str = "llama3.1") -> None:
        """Initialize the LLM wrapper.
        
        Args:
            model: Name of the model to use (default: "llama3.1")
        """
        self.model = model
        self.temperature = 0.1
        self.max_tokens = 3900
        self.timeout = 360.0
        self.llm = RamaLama(model)
    
    def complete(self, prompt: str, **kwargs: Any) -> str:
        """Complete a prompt using the LLM.
        
        Compatibility method for llama_index-style completion.
        
        Args:
            prompt: Text prompt to complete
            **kwargs: Additional arguments (max_tokens, temperature, etc.)
            
        Returns:
            Generated completion text
        """
        max_tokens = kwargs.get('max_tokens', self.max_tokens)
        temperature = kwargs.get('temperature', self.temperature)
        return self.llm.query(prompt, max_tokens=max_tokens, temperature=temperature)
    
    def stream_complete(self, prompt: str, **kwargs: Any) -> Iterator[str]:
        """Stream complete a prompt using the LLM.
        
        Compatibility method for llama_index-style streaming completion.
        
        Args:
            prompt: Text prompt to complete
            **kwargs: Additional arguments (max_tokens, temperature, etc.)
            
        Yields:
            Generated text chunks
        """
        max_tokens = kwargs.get('max_tokens', self.max_tokens) 
        temperature = kwargs.get('temperature', self.temperature)
        yield from self.llm.stream(prompt, max_tokens=max_tokens, temperature=temperature)
    
    def query(self, prompt: str, **kwargs: Any) -> str:
        """Direct query method for simple text generation.
        
        Args:
            prompt: Text prompt to process
            **kwargs: Additional arguments
            
        Returns:
            Generated response text
        """
        return self.complete(prompt, **kwargs)
    
    def __enter__(self) -> 'LLM':
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        # RamaLama handles cleanup automatically
        pass
