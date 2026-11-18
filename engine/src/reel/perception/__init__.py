"""Perception: facts about the footage for Claude and the compiler (build step 3).

Every module reads the S0 mezzanine (single clock, ADR-0015); all times are microseconds
on that clock. Heavy dependencies are imported lazily (`uv sync --extra perception`).
"""
