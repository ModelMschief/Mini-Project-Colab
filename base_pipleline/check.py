import pdfplumber
import re

#Extract lines from pdf along with their attributes and stats
def extract_lines(words, page_index, start_line_index, threshold=2):
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

            if word_font not in current_fonts:
                current_fonts.append(word_font)

            if word_size not in current_sizes:
                current_sizes.append(word_size)

        else:
            lines.append({
                "text": current_text,
                "line_index": line_index,
                "page_index": page_index,
                "layout": {"top": current_top},
                "word_count": len(current_text.split()),
                "size_stats": build_stats(current_sizes),
                "style_stats": build_stats(current_fonts),
                "has_symbol": has_symbol(current_text),
                "starts_with_number": starts_with_number(current_text),
                "ends_with_punctuation": ends_with_punctuation(current_text)
            })

            line_index += 1

            current_top = word_top
            current_text = word_text
            current_fonts = [word_font]
            current_sizes = [word_size]

    if current_text:
        lines.append({
            "text": current_text,
            "line_index": line_index,
            "page_index": page_index,
            "layout": {"top": current_top},
            "word_count": len(current_text.split()),
            "size_stats": build_stats(current_sizes),
            "style_stats": build_stats(current_fonts),
            "has_symbol": has_symbol(current_text),
            "starts_with_number": starts_with_number(current_text),
            "ends_with_punctuation": ends_with_punctuation(current_text)
        })

        line_index += 1

    return lines, line_index

#-------- HELPERS -------- -> helps in building stats and checking text properties
def build_stats(items):
    stats = {}
    for item in items:
        if item in stats:
            stats[item] += 1
        else:
            stats[item] = 1
    return stats


def has_symbol(text):
    return bool(re.search(r"[•●▪■→]", text))


def starts_with_number(text):
    return bool(re.match(r"^\d+[\.\)]", text.strip()))


def ends_with_punctuation(text):
    return text.strip().endswith((".", "!", "?"))

#load pdf and call extract_lines()
def extract_pdf_lines(pdf_path):
    all_lines = []
    current_line_index = 0

    with pdfplumber.open(pdf_path) as pdf:
        for page_index, page in enumerate(pdf.pages):
            words = page.extract_words(extra_attrs=["size", "fontname"])
            page_lines, current_line_index = extract_lines(
                words,
                page_index,
                current_line_index
            )
            all_lines.extend(page_lines)
    return all_lines


# -------- OUTPUT --------
#Over all document stats as fonts and sizes count
def doc_stats(all_lines):
    fonts_count = {}
    sizes_count = {}
    for line in all_lines:
        
        for key, value in line['size_stats'].items():
            
            normalized_size = round(key, 1)  
            if normalized_size in sizes_count:
                sizes_count[normalized_size] += value
            else:
                sizes_count[normalized_size] = value
        
        for key, value in line['style_stats'].items():
            
            if key in fonts_count:
                fonts_count[key] += value
            else:
                fonts_count[key] = value

    return fonts_count, sizes_count

#return heading and paragraph fonts
def font_insights(fonts_count):
    text_fonts = {}

    for font, count in fonts_count.items():
        f = font.lower()

        if "symbol" in f:
            continue

        is_bold = "bold" in f
        is_italic = "italic" in f

        # skip pure italic
        if is_italic and not is_bold:
            continue

        text_fonts[font] = count

    # sort by frequency (descending)
    sorted_fonts = []
    for font, count in text_fonts.items():
        sorted_fonts.append((font, count))

    sorted_fonts.sort(key=lambda x: x[1], reverse=True)

    paragraph_font = sorted_fonts[0][0]
    heading_fonts = []

    for font, count in sorted_fonts[1:]:
        heading_fonts.append(font)

    return heading_fonts, paragraph_font

#return heading and paragraph sizes
def size_insights(sizes_count):
    text_sizes = {}
    for size,count in sizes_count.items():
        if size >= 11:  # Assuming text sizes are 11 and above
            text_sizes[size] = count
    
    total_text_sizes = sum(text_sizes.values())
    print(f"Total text sizes count: {total_text_sizes}")

    size_likelihood = {}

    for size, count in text_sizes.items():
        size_likelihood[size] = count / total_text_sizes

    paragraphs_size = None
    max_count = 0

    for size, count in text_sizes.items():
        if count > max_count:
            max_count = count
            paragraphs_size = size

    # detect heading size (optional)
    headings_size = None
    for size, count in text_sizes.items():
        if size > paragraphs_size:
            headings_size = size
            break

    #paragraphs_size = max(size_likelihood, key=size_likelihood.get)
    #headings_size = min(size_likelihood, key=size_likelihood.get)
    return headings_size, paragraphs_size

# -------- MAIN EXECUTION --------
#main funcation to call all other functions and return final insights
def main_ex(pdf_path):
    
    all_lines = extract_pdf_lines(pdf_path)

    fonts_count, sizes_count = doc_stats(all_lines)
    headings_fonts, paragraphs_fonts = font_insights(fonts_count)
    headings_size, paragraphs_size = size_insights(sizes_count)

    para_head_dict = {
        "paragraph_font": paragraphs_fonts,
        "heading_font": headings_fonts,
        "paragraph_size": paragraphs_size,
        "heading_size": headings_size
    }
    return para_head_dict

# -------- RUNNING THE SCRIPT -------- Can call multiple pdfs

