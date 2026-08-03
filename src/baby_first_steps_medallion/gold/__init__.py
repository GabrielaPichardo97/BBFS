"""Public Gold semantic-search entry points."""

from baby_first_steps_medallion.gold.models import SearchResult
from baby_first_steps_medallion.gold.service import semantic_search

__all__ = ["SearchResult", "semantic_search"]
