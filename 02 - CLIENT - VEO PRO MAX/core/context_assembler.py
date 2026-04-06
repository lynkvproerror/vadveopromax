"""
VEO Pro Max - Context Assembler

Extracted from project_builder.py ContextManager class.
Assembles system prompts for each step of AI topic processing.

Each topic gets a FRESH context — no cross-topic contamination.
Injects matrix config dimensions and workflow rules into prompts.

Usage:
    from core.context_assembler import ContextAssembler
    ctx = ContextAssembler()
    system, user = ctx.build_context("Research", topic, template_body, rules)
"""

# Re-export the original ContextManager for now.
# This module exists as the designated import path for context assembly.
# When project_builder.py is fully decomposed, this module will contain
# the actual implementation instead of re-exporting.
from core.project_builder import ContextManager as ContextAssembler

__all__ = ["ContextAssembler"]
