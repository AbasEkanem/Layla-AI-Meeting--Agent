"""Guardrails — deterministic, dependency-light safety filters for Layla.

Currently exposes the input guard used to keep untrusted text (meeting
transcripts, external content) from poisoning Layla's long-term memory.
"""

from .input_guard import contains_injection

__all__ = ["contains_injection"]
