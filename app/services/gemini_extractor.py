"""
Deprecated compatibility module.

The project now uses Groq for text structuring. Import GroqDocumentExtractor
from app.services.groq_extractor in new code.
"""

from app.services.groq_extractor import GroqDocumentExtractor

# Temporary alias so older local imports do not break immediately.
GeminiDocumentExtractor = GroqDocumentExtractor
