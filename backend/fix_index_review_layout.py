from pathlib import Path
import re

path = Path(__file__).resolve().parents[1] / "index.html"
text = path.read_text(encoding="utf-8")

reviews_start = text.find('<section id="reviews">')
contact_start = text.find('<section class="light" id="contact">', reviews_start)
if reviews_start == -1 or contact_start == -1:
    raise SystemExit("Could not locate Reviews and Contact sections in index.html")

reviews = text[reviews_start:contact_start]

quote_match = re.search(r'<blockquote class="review-quote">.*?</blockquote>', reviews, re.DOTALL)
img_match = re.search(r'<img class="review-avatar"[^>]*alt="Gabriella C profile photo"[^>]*>', reviews, re.DOTALL)
note_match = re.search(r'<p class="review-note">.*?</p>', reviews, re.DOTALL)

if not quote_match:
    raise SystemExit("Could not find Gabriella review quote")
if not img_match:
    raise SystemExit("Could not find Gabriella profile image")

quote = quote_match.group(0).strip()
image = img_match.group(0).strip()
note = note_match.group(0).strip() if note_match else ""

new_reviews = f'''<section id="reviews">
  <div class="wrap reviews-layout">
    <div>
      <div class="section-number">Recommendations</div>
      <h2 class="section-title">Reviews</h2>
      <p class="section-copy">A note from someone who has seen how I approach the work: with follow-through, care, and the willingness to correct what needs correcting.</p>
    </div>

    <div class="review-card">
      {quote}

      <div class="review-attribution" aria-label="Gabriella C recommendation">
        <div class="review-rating" aria-label="Recommendation rating"><span>Recommended:</span> ★★★★★</div>
        {image}
        <div class="review-name">Gabriella C.</div>
      </div>
'''
if note:
    new_reviews += f'''\n      {note}\n'''
new_reviews += '''    </div>
  </div>
</section>

'''

text = text[:reviews_start] + new_reviews + text[contact_start:]

# Add the attribution layout CSS once. This keeps the rating, photo, and name
# together beneath the testimonial rather than alongside the quote.
css_anchor = '.review-rating span{color:#9f9288;font-size:.82rem;font-weight:600;letter-spacing:0}\n'
attribution_css = (
    '.review-attribution{display:flex;align-items:center;gap:12px 14px;margin-top:22px;flex-wrap:wrap}\n'
    '.review-attribution .review-rating{margin:0;font-size:1.85rem}\n'
    '.review-attribution .review-avatar{width:52px;height:52px;flex:0 0 auto}\n'
    '.review-attribution .review-name{margin:0}\n'
)
if '.review-attribution{' not in text:
    if css_anchor not in text:
        raise SystemExit("Could not locate review CSS anchor")
    text = text.replace(css_anchor, css_anchor + attribution_css, 1)

# Remove the redundant homepage Contact form button/helper copy. The form is
# already immediately beside the introduction in the desktop layout.
contact_details_pattern = re.compile(
    r'\n\s*<div class="contact-details">\s*'
    r'<a class="btn gold" href="#contact-form">Contact form</a>\s*'
    r'<p class="form-help"[^>]*>Use the form to send your inquiry securely to my client requests inbox\.</p>\s*'
    r'</div>',
    re.DOTALL,
)
text, removed = contact_details_pattern.subn('', text, count=1)
if removed == 0 and 'Use the form to send your inquiry securely to my client requests inbox.' in text:
    raise SystemExit("Found redundant contact copy but could not remove its block safely")

path.write_text(text, encoding="utf-8")
print("Repaired index review attribution and removed redundant contact button/copy.")
