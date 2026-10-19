import difflib
import unicodedata

def normalize_text(text: str) -> str:
    """Normalize Polish characters and punctuation for comparison."""
    if not text:
        return ""
    text = text.lower().strip()
    # Replace common polish chars
    replacements = {
        'ą': 'a', 'ć': 'c', 'ę': 'e', 'ł': 'l', 'ń': 'n',
        'ó': 'o', 'ś': 's', 'ź': 'z', 'ż': 'z'
    }
    for pol, asc in replacements.items():
        text = text.replace(pol, asc)
    # Strip accents
    normalized = unicodedata.normalize('NFKD', text)
    ascii_text = ''.join(c for c in normalized if not unicodedata.combining(c))
    # Replace hyphens and underscores with spaces
    return ascii_text.replace('-', ' ').replace('_', ' ').strip()

def match_activity(query: str, target_slug: str, target_title: str) -> tuple[bool, float]:
    """
    Check if user query matches target activity (by slug or title).
    Returns (is_match, confidence_score).
    """
    norm_query = normalize_text(query)
    norm_slug = normalize_text(target_slug)
    norm_title = normalize_text(target_title)

    # 1. Exact match beats substring match (so 'hiit' prefers 'HIIT' over 'HIIT Kids')
    if norm_query == norm_slug or norm_query == norm_title:
        return True, 1.0

    if norm_query in norm_slug or norm_query in norm_title:
        return True, 0.95

    if norm_slug in norm_query or norm_title in norm_query:
        return True, 0.9

    # 2. Fuzzy match against slug and title
    score_slug = difflib.SequenceMatcher(None, norm_query, norm_slug).ratio()
    score_title = difflib.SequenceMatcher(None, norm_query, norm_title).ratio()
    best_score = max(score_slug, score_title)

    # Threshold for fuzzy match: 0.75 (e.g. 'szangi' vs 'sztangi' is > 0.85)
    if best_score >= 0.75:
        return True, best_score

    return False, best_score
