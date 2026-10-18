"""Zdrofit automatic class registration package."""
from .client import ZdrofitClient
from .date_parser import parse_target_date, parse_weekday
from .matcher import match_activity

__all__ = ["ZdrofitClient", "parse_target_date", "parse_weekday", "match_activity"]
