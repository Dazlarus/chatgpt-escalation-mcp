"""
OCR-based text extraction for ChatGPT sidebar.

Uses PaddleOCR for accurate text reading from UI screenshots.
Works with the pixel-based hover detection for a complete solution.
"""
import numpy as np
from PIL import Image
from typing import Optional, List, Tuple
import os
import threading

# Suppress PaddleOCR verbose logging
os.environ['PADDLEOCR_HOME'] = os.path.join(os.path.dirname(__file__), '.paddleocr')

# Import PaddleOCR early (this import itself is slow ~2-3 seconds)
from paddleocr import PaddleOCR

_ocr_instance = None
_ocr_lock = threading.Lock()
_ocr_loading = False


def _preload_ocr():
    """Background thread to preload OCR models."""
    global _ocr_instance, _ocr_loading
    try:
        # PaddleOCR v3 API - use English, disable extra processing for speed
        instance = PaddleOCR(
            lang='en',
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )
        with _ocr_lock:
            if _ocr_instance is None:
                _ocr_instance = instance
    except Exception:
        pass  # Will fall back to blocking load in get_ocr()
    finally:
        _ocr_loading = False


def start_ocr_preload():
    """Start preloading OCR models in background thread."""
    global _ocr_loading
    with _ocr_lock:
        if _ocr_instance is not None or _ocr_loading:
            return  # Already loaded or loading
        _ocr_loading = True
    
    thread = threading.Thread(target=_preload_ocr, daemon=True)
    thread.start()


def get_ocr():
    """Get or create PaddleOCR instance (singleton for performance)."""
    global _ocr_instance, _ocr_loading
    
    # Fast path: already loaded
    if _ocr_instance is not None:
        return _ocr_instance
    
    # If background loading, wait for it
    with _ocr_lock:
        if _ocr_instance is not None:
            return _ocr_instance
        
        # Not loaded yet - load now (blocking)
        if not _ocr_loading:
            _ocr_instance = PaddleOCR(
                lang='en',
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
            )
    
    # Wait for background thread if it's loading
    while _ocr_loading and _ocr_instance is None:
        import time
        time.sleep(0.05)
    
    return _ocr_instance


# Start preloading OCR models immediately when module is imported
start_ocr_preload()


def preprocess_for_ocr(img: Image.Image, scale: int = 2) -> np.ndarray:
    """
    Preprocess image for better OCR results.
    
    Args:
        img: PIL Image to process
        scale: Upscale factor (2-3x helps with small UI fonts)
    
    Returns:
        Numpy array ready for OCR
    """
    # Upscale for better OCR on small fonts
    if scale > 1:
        new_size = (img.width * scale, img.height * scale)
        img = img.resize(new_size, Image.Resampling.LANCZOS)
    
    # Convert to RGB if needed
    if img.mode != 'RGB':
        img = img.convert('RGB')
    
    return np.array(img)


def ocr_image(img: Image.Image, scale: int = 2) -> List[Tuple[str, float]]:
    """
    Run OCR on an image and return detected text with confidence.
    
    Args:
        img: PIL Image to OCR
        scale: Upscale factor for preprocessing
    
    Returns:
        List of (text, confidence) tuples, sorted by position (top to bottom)
    """
    import tempfile
    
    ocr = get_ocr()
    img_processed = Image.fromarray(preprocess_for_ocr(img, scale))
    
    # PaddleOCR v3 API requires a file path, so save to temp file
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
        temp_path = f.name
        img_processed.save(temp_path)
    
    try:
        result = ocr.predict(temp_path)
        
        if not result:
            return []
        
        # PaddleOCR v3 returns a list of dict-like result objects
        texts = []
        for res in result:
            # Access via dict keys
            rec_texts = res.get('rec_texts', [])
            rec_scores = res.get('rec_scores', [])
            dt_polys = res.get('dt_polys', [])
            
            for i, text in enumerate(rec_texts):
                score = rec_scores[i] if i < len(rec_scores) else 0.9
                # Get y position from bounding box if available
                y_pos = 0
                if i < len(dt_polys) and len(dt_polys[i]) > 0:
                    y_pos = dt_polys[i][0][1]  # Top-left y coordinate
                texts.append((text, score, y_pos))
        
        # Sort by y position (top to bottom)
        texts.sort(key=lambda x: x[2])
        
        # Return just text and confidence
        return [(t[0], t[1]) for t in texts]
    finally:
        # Clean up temp file
        try:
            os.unlink(temp_path)
        except:
            pass


def ocr_row(sidebar_img: Image.Image, row_top: int, row_bottom: int, 
            padding: int = 5, scale: int = 2) -> Optional[str]:
    """
    OCR a specific row from the sidebar image.
    
    Args:
        sidebar_img: Full sidebar screenshot
        row_top: Top y coordinate of row
        row_bottom: Bottom y coordinate of row
        padding: Extra pixels to include above/below
        scale: Upscale factor for OCR
    
    Returns:
        Detected text string, or None if OCR failed
    """
    # Crop the row with padding
    top = max(0, row_top - padding)
    bottom = min(sidebar_img.height, row_bottom + padding)
    
    row_crop = sidebar_img.crop((0, top, sidebar_img.width, bottom))
    
    # Run OCR
    results = ocr_image(row_crop, scale)
    
    if not results:
        return None
    
    # Return ALL detected text joined together
    # This handles rows with multiple elements (e.g., "New chat" + "Ctrl + Shift")
    # The fuzzy matcher can then find the target text within the combined string
    all_texts = [r[0] for r in results]
    return ' '.join(all_texts)


def ocr_all_rows(sidebar_img: Image.Image, row_height: int = 35, 
                 top_skip: int = 35, bottom_skip: int = 40) -> List[dict]:
    """
    OCR all menu rows in the sidebar.
    
    Returns list of dicts with row info and detected text.
    """
    height = sidebar_img.height
    rows = []
    
    y = top_skip
    row_idx = 0
    
    while y + row_height <= height - bottom_skip:
        text = ocr_row(sidebar_img, y, y + row_height)
        
        rows.append({
            'idx': row_idx,
            'y_start': y,
            'y_end': y + row_height,
            'text': text or '',
        })
        
        y += row_height
        row_idx += 1
    
    return rows


# Test function
if __name__ == '__main__':
    import sys
    
    # Test on existing debug images
    base_dir = r"N:\AI Projects\chatgpt-escalation-mcp\debug_output_v6"
    
    test_cases = [
        ("03_scan_15pct_sidebar.png", "New chat"),
        ("04_scan_23pct_sidebar.png", "Search chats"),
        ("05_scan_31pct_sidebar.png", "Library"),
        ("06_scan_39pct_sidebar.png", "Codex"),
        ("08_scan_55pct_sidebar.png", "Explore"),
        ("09_scan_63pct_sidebar.png", "Monday"),
        ("11_scan_79pct_sidebar.png", "New project"),
        ("12_scan_87pct_sidebar.png", "Agent Expert Help"),
        ("13_scan_95pct_sidebar.png", "Ensign Karl"),
    ]
    
    print("=" * 70)
    print("PADDLEOCR TEXT EXTRACTION TEST")
    print("=" * 70)
    
    for filename, expected in test_cases:
        filepath = os.path.join(base_dir, filename)
        if not os.path.exists(filepath):
            print(f"  SKIP: {filename}")
            continue
        
        img = Image.open(filepath)
        
        # OCR the full image
        results = ocr_image(img)
        
        # Check if expected text was found
        all_text = ' '.join([r[0] for r in results])
        found = expected.lower() in all_text.lower()
        
        status = "✓" if found else "✗"
        print(f"\n{status} {expected}")
        print(f"  Found text: {[r[0] for r in results[:5]]}...")
