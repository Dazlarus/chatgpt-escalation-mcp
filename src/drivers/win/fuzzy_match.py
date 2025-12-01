"""
Fuzzy string matching for OCR results.

Handles common OCR errors:
- Character substitutions (i/l, 0/O, etc.)
- Missing/extra characters
- Spacing issues
"""
from difflib import SequenceMatcher
from typing import List, Optional, Tuple


def similarity_ratio(s1: str, s2: str) -> float:
    """
    Calculate similarity ratio between two strings (0.0 to 1.0).
    Uses SequenceMatcher which handles insertions, deletions, and substitutions.
    """
    if not s1 or not s2:
        return 0.0
    return SequenceMatcher(None, s1.lower(), s2.lower()).ratio()


def fuzzy_match(target: str, candidates: List[str], threshold: float = 0.7) -> Optional[Tuple[str, float]]:
    """
    Find the best fuzzy match for target in candidates.
    
    Args:
        target: String to search for
        candidates: List of strings to search in
        threshold: Minimum similarity ratio to consider a match (0.0-1.0)
    
    Returns:
        Tuple of (matched_string, similarity) or None if no match above threshold
    """
    if not target or not candidates:
        return None
    
    best_match = None
    best_score = 0.0
    
    target_lower = target.lower()
    
    for candidate in candidates:
        if not candidate:
            continue
            
        candidate_lower = candidate.lower()
        
        # Exact match
        if target_lower == candidate_lower:
            return (candidate, 1.0)
        
        # Check if target is contained in candidate or vice versa
        if target_lower in candidate_lower or candidate_lower in target_lower:
            score = len(min(target_lower, candidate_lower, key=len)) / len(max(target_lower, candidate_lower, key=len))
            if score > best_score:
                best_score = score
                best_match = candidate
                continue
        
        # Fuzzy match using SequenceMatcher
        score = similarity_ratio(target, candidate)
        if score > best_score:
            best_score = score
            best_match = candidate
    
    if best_score >= threshold:
        return (best_match, best_score)
    
    return None


def fuzzy_contains(target: str, text: str, threshold: float = 0.75) -> bool:
    """
    Check if target is approximately contained in text.
    
    Handles cases like:
    - "Ensign Karl" in "Ensian Karl" (OCR error)
    - "Agent Expert" in "Agent Expert Help"
    - "New chat" in "New chat"
    """
    if not target or not text:
        return False
    
    target_lower = target.lower()
    text_lower = text.lower()
    
    # Exact containment
    if target_lower in text_lower or text_lower in target_lower:
        return True
    
    # Check similarity of the whole strings
    if similarity_ratio(target, text) >= threshold:
        return True
    
    # Check if all words from target are approximately in text
    target_words = target_lower.split()
    text_words = text_lower.split()
    
    if not target_words:
        return False
    
    matched_words = 0
    for tw in target_words:
        # Check each target word against all text words
        for txt_w in text_words:
            if tw == txt_w or similarity_ratio(tw, txt_w) >= 0.8:
                matched_words += 1
                break
    
    # If most target words matched, consider it a match
    return matched_words >= len(target_words) * 0.7


def find_best_match_in_list(target: str, items: List[str], threshold: float = 0.7) -> Optional[int]:
    """
    Find the index of the best matching item in a list.
    
    Args:
        target: String to search for
        items: List of strings to search in
        threshold: Minimum similarity to consider
    
    Returns:
        Index of best match, or None if no match above threshold
    """
    result = fuzzy_match(target, items, threshold)
    if result:
        matched_text, _ = result
        try:
            return items.index(matched_text)
        except ValueError:
            # Find by lowercase comparison
            for i, item in enumerate(items):
                if item.lower() == matched_text.lower():
                    return i
    return None


# Test
if __name__ == '__main__':
    print("=" * 60)
    print("FUZZY MATCHING TEST")
    print("=" * 60)
    
    test_cases = [
        # (target, candidate, expected_match)
        ("Ensign Karl", "Ensian Karl", True),      # OCR error
        ("Ensign Karl", "Ensign Karl", True),      # Exact
        ("New chat", "New chat", True),            # Exact
        ("Agent Expert Help", "Agent Expert", True),  # Partial
        ("Library", "Libary", True),               # Typo
        ("Monday", "Mondey", True),                # OCR error
        ("Codex", "Code", False),                  # Too different
        ("Search chats", "Search", False),         # Partial but key word missing
        ("New project", "New projct", True),       # Missing letter
    ]
    
    for target, candidate, expected in test_cases:
        score = similarity_ratio(target, candidate)
        matches = fuzzy_contains(target, candidate)
        status = "✓" if matches == expected else "✗"
        print(f"  {status} '{target}' ~ '{candidate}': {score:.2f} (match={matches}, expected={expected})")
    
    print("\n" + "=" * 60)
    print("FIND IN LIST TEST")
    print("=" * 60)
    
    ocr_results = ["New chat", "Search chats", "Libary", "Codex", "Explore GPTs", "Mondey", "New projct", "Agent Expert Help", "Ensian Karl"]
    
    searches = ["Ensign Karl", "Library", "Monday", "New project", "Agent Expert Help"]
    
    for search in searches:
        idx = find_best_match_in_list(search, ocr_results)
        if idx is not None:
            print(f"  ✓ '{search}' -> found at idx {idx}: '{ocr_results[idx]}'")
        else:
            print(f"  ✗ '{search}' -> NOT FOUND")
