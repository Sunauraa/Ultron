"""Ultron (Ultra-Light Task Router for Online Navigation), an optional fast path for Browser Use: tiny local models answer bounded decisions before the LLM."""

from .fastpath import FastPath, install, parse_document

__all__ = ["FastPath", "install", "parse_document"]
