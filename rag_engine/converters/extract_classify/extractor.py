import pdfplumber
import re
import os

from wordsegment import load, segment
import re

load()

def calculate_text_features(line_dict, text):
    """Calculates all text-based features for a given string and adds them to the dictionary"""
    clean_text = text.strip()
    chars = len(clean_text)
    
    # Base text updates
    line_dict["text"] = text
    line_dict["word_count"] = len(clean_text.split())
    line_dict["char_length"] = chars
    
    # Ratios and Counts
    alpha = sum(c.isalpha() for c in clean_text)
    digits = sum(c.isdigit() for c in clean_text)
    symbols = sum((not c.isalnum() and not c.isspace()) for c in clean_text)
    math_symbol_count = sum(c in set("=<>+-*/^θλβˆ∑≈≤≥") for c in clean_text)
    
    alpha_chars = [c for c in clean_text if c.isalpha()]
    total_alpha = len(alpha_chars)
    upper_count = sum(1 for c in alpha_chars if c.isupper())
    upper_ratio = upper_count / total_alpha if total_alpha > 0 else 0.0

    line_dict["is_upper"] = int(clean_text.isupper())
    line_dict["is_title"] = int(clean_text.istitle())
    line_dict["upper_ratio"] = round(upper_ratio, 3)
    
    line_dict["is_tiny"] = 1 if line_dict["word_count"] <= 2 else 0
    line_dict["is_numeric_only"] = 1 if clean_text.isdigit() else 0
    line_dict["alpha_ratio"] = alpha / chars if chars > 0 else 0
    line_dict["digit_ratio"] = digits / chars if chars > 0 else 0
    line_dict["symbol_ratio"] = symbols / chars if chars > 0 else 0
    line_dict["has_math_symbol"] = 1 if math_symbol_count > 0 else 0

    # RECALCULATE PUNCTUATION (Fixes the stale punctuation bug)
    line_dict["has_symbol"] = bool(re.search(r"[•●▪■→]", text))
    line_dict["starts_with_number"] = bool(re.match(r"^\d+[\.\)]", clean_text))
    line_dict["ends_with_punctuation"] = clean_text.endswith((".", "!", "?"))

    return line_dict

def repair_sentence(all_lines):
    for line in all_lines:
        text = line["text"]
        text = re.sub(r'\(cid:\d+\)', ' ', text)
        # 1. First, handle CamelCase to prevent "Longformer" becoming "long former"
        # We add a space before capital letters that follow a lowercase letter
        text = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', text)
        
        # 2. Split the string by actual spaces (if any exist)
        parts = text.split()
        
        final_repaired = []

        for part in parts:
            # 3. Use regex to find all "chunks" of letters or non-letters
            # This keeps "architecture," as ["architecture", ","]
            chunks = re.findall(r'[A-Za-z]+|[^A-Za-z]+', part)
            
            repaired_chunks = []
            for chunk in chunks:
                # If the chunk is purely alphabetic and long, segment it
                if chunk.isalpha() and len(chunk) > 3:
                    # segment() returns a list of words
                    split_words = segment(chunk)
                    
                    # Heuristic: If segmenting didn't change anything, keep original casing
                    if len(split_words) == 1 and split_words[0].lower() == chunk.lower():
                        repaired_chunks.append(chunk)
                    else:
                        repaired_chunks.append(" ".join(split_words))
                else:
                    repaired_chunks.append(chunk)
            
            final_repaired.append("".join(repaired_chunks))

        final_repaired = " ".join(final_repaired)
        
        calculate_text_features(line, final_repaired)

    return all_lines

# COMMON HELPERS

def build_stats(items):
    stats = {}
    for item in items:
        stats[item] = stats.get(item, 0) + 1
    return stats


def has_symbol(text):
    return bool(re.search(r"[•●▪■→]", text))


def starts_with_number(text):
    return bool(re.match(r"^\d+[\.\)]", text.strip()))


def ends_with_punctuation(text):
    return text.strip().endswith((".", "!", "?"))


#Extract lines from pdf along with their attributes and stats
def extract_lines_pdf(words, page_index, start_line_index, threshold=2):
    lines = []
    current_text = ""
    current_top = None
    current_fonts = []
    current_sizes = []
    line_index = start_line_index

    for word in words:
        word_text = word["text"]
        word_top = word["top"]
        word_font = word["fontname"]
        word_size = word["size"]

        if current_top is None:
            current_top = word_top
            current_text = word_text
            current_fonts = [word_font]
            current_sizes = [word_size]

        elif abs(word_top - current_top) <= threshold:
            current_text += " " + word_text
            if word_font not in current_fonts: current_fonts.append(word_font)
            if word_size not in current_sizes: current_sizes.append(word_size)
        else:
            # Build base dictionary, then add features
            line_dict = {
                "line_index": line_index,
                "page_index": page_index,
                "layout": {"top": current_top},
                "size_stats": build_stats(current_sizes),
                "style_stats": build_stats(current_fonts)
            }
            lines.append(calculate_text_features(line_dict, current_text))
            
            line_index += 1
            current_top = word_top
            current_text = word_text
            current_fonts = [word_font]
            current_sizes = [word_size]

    if current_text:
        line_dict = {
            "line_index": line_index,
            "page_index": page_index,
            "layout": {"top": current_top},
            "size_stats": build_stats(current_sizes),
            "style_stats": build_stats(current_fonts)
        }
        lines.append(calculate_text_features(line_dict, current_text))
        line_index += 1

    return lines, line_index


def extract_pdf_lines(pdf_path):
    all_lines = []
    current_line_index = 0

    with pdfplumber.open(pdf_path) as pdf:
        for page_index, page in enumerate(pdf.pages):
            words = page.extract_words(extra_attrs=["size", "fontname"])

            page_lines, current_line_index = extract_lines_pdf(
                words,
                page_index,
                current_line_index
            )

            all_lines.extend(page_lines)
    all_lines = repair_sentence(all_lines)

    return all_lines

# UNIFIED ENTRY POINT

def extract_document_lines(file_path):
        return extract_pdf_lines(file_path)

