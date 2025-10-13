"""Example:
    generate_noisy_answer("Explain ACID in databases.", level=1)
"""

from .auto_reply import generate_noisy_answer  # Re-export noisy generation helper

__all__ = ["generate_noisy_answer"]
