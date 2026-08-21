import os
import sys
import json
import calendar
from datetime import date
import requests
from PIL import Image, ImageDraw, ImageFont

IMAGE_URL = os.environ["IMAGE_URL"].strip().strip("'\"")
if not IMAGE_URL.startswith(("http://", "https://")):
    print(f"ERROR: IMAGE_URL doesn't look like a valid URL: {IMAGE_URL!r}", file=sys.stderr)
    print("If you pasted this manually, make sure it doesn't include surrounding quote marks.", file=sys.stderr)
    sys.exit(1)
BOX_X_PCT = float(os.environ["BOX_X_PCT"])
BOX_Y_PCT = float(os.environ["BOX_Y_PCT"])
BOX_W_PCT = float(os.environ["BOX_W_PCT"])
BOX_H_PCT = float(os.environ["BOX_H_PCT"])
MONTH_KEY = os.environ.get("MONTH_KEY", "this_month")

FIXTURES_FILE = "docs/fixtures.json"
FONT_FILE = "oswald.ttf"
OUTPUT_DIR = "docs/output"

# Matches the frontend's inner-margin ratio so the preview and final image agree
CONTENT_MARGIN_RATIO = 0.94


def get_output_filename():
    """e.g. 'aug2026.png' or 'sep2026.png', based on which month was selected."""
    today = date.today()
    if MONTH_KEY == "next_month":
        if today.month == 12:
            year, month = today.year + 1, 1
        else:
            year, month = today.year, today.month + 1
    else:
        year, month = today.year, today.month

    abbr = calendar.month_abbr[month].lower()  # 'aug', 'sep', ...
    return f"{abbr}{year}.png"


def load_fixture_text():
    with open(FIXTURES_FILE) as f:
        data = json.load(f)
    fixtures = data.get(MONTH_KEY, [])
    if not fixtures:
        return "No fixtures found for this period."
    blocks = [
        f"{fx['day_label']} | {fx['competition']}\n{fx['home']} vs. {fx['away']}\ntime {fx['time_label']}"
        for fx in fixtures
    ]
    return "\n\n".join(blocks)


def download_image(url):
    headers = {"User-Agent": "Mozilla/5.0 (compatible; WallpaperBot/1.0)"}
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    with open("source_image.tmp", "wb") as f:
        f.write(resp.content)
    return Image.open("source_image.tmp").convert("RGB")


def fit_text_size(draw, text, max_width, max_height, font_path):
    """Binary search the largest font size where the text fits within the box."""
    lo, hi = 4, 300
    best_font = ImageFont.truetype(font_path, lo)

    while lo < hi:
        mid = (lo + hi + 1) // 2
        font = ImageFont.truetype(font_path, mid)
        bbox = draw.multiline_textbbox((0, 0), text, font=font, align="center", spacing=int(mid * 0.3))
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]

        if text_w <= max_width and text_h <= max_height:
            lo = mid
            best_font = font
        else:
            hi = mid - 1

    return best_font


def main():
    print(f"Downloading source image: {IMAGE_URL}")
    img = download_image(IMAGE_URL)
    img_w, img_h = img.size
    print(f"Image size: {img_w}x{img_h}")

    box_x = BOX_X_PCT / 100 * img_w
    box_y = BOX_Y_PCT / 100 * img_h
    box_w = BOX_W_PCT / 100 * img_w
    box_h = BOX_H_PCT / 100 * img_h

    # Draw the semi-transparent black box on an RGBA overlay, then composite
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    overlay_draw.rectangle(
        [box_x, box_y, box_x + box_w, box_y + box_h],
        fill=(0, 0, 0, 153),  # 60% opacity
    )
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

    text = load_fixture_text()
    draw = ImageDraw.Draw(img)

    max_w = box_w * CONTENT_MARGIN_RATIO
    max_h = box_h * CONTENT_MARGIN_RATIO
    font = fit_text_size(draw, text, max_w, max_h, FONT_FILE)

    bbox = draw.multiline_textbbox((0, 0), text, font=font, align="center", spacing=int(font.size * 0.3))
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    text_x = box_x + (box_w - text_w) / 2 - bbox[0]
    text_y = box_y + (box_h - text_h) / 2 - bbox[1]

    draw.multiline_text(
        (text_x, text_y), text, font=font, fill=(255, 255, 255),
        align="center", spacing=int(font.size * 0.3),
    )

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, get_output_filename())
    img.save(output_path)
    print(f"Saved wallpaper to {output_path}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
