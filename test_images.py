"""Test image support: full-bleed background photo + inline content image."""
import server

slides = [
    # Full-bleed background photo, light text auto-applied, scrim for legibility.
    {"template": "title", "eyebrow": "2026 Report",
     "heading": "The State of Remote Work",
     "subheading": "What 5,000 teams told us this year",
     "background_image": "assets/photo1.svg"},
    # Inline image card inside a content slide.
    {"template": "content", "eyebrow": "Key finding",
     "heading": "Hybrid is winning",
     "image": "assets/photo2.svg",
     "body": "58% of teams now run hybrid — up from 41% last year. Fully-remote held steady at 27%."},
    # Background photo on a CTA slide.
    {"template": "cta", "eyebrow": "Read more",
     "heading": "Get the full report",
     "body": "Link in bio.", "button": "Download",
     "background_image": "assets/photo1.svg"},
]

res = server._render_all("images", "Image Demo", "midnight", "portrait", slides)
print("OK:", res["preview_url"])
