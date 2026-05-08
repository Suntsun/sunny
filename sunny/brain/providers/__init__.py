"""Providers de cerebro (LLM) para Sunny.

Cada provider implementa BrainProvider y encapsula un backend concreto
(Ollama local, Groq cloud, etc.). La selección se hace vía factory.
"""

from sunny.brain.providers.base import BrainProvider

__all__ = ["BrainProvider"]
