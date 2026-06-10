"""Test brand profile + logo + caption/hashtags end to end."""
import server
from carousel import brand as brand_mod

# 1. Save a brand profile with a custom theme + logo + default hashtags.
brand_mod.save_brand({
    "name": "buildnotes",
    "handle": "@buildnotes",
    "logo": "_demo_logo.svg",
    "base_theme": "midnight",
    "theme": {"accent": "#f472b6", "bg": ["#1e1b4b", "#312e81"]},
    "default_hashtags": ["#buildinpublic", "#startup", "#devtips"],
    "caption_signature": "Follow @buildnotes for a build tip every day 🚀",
})

slides = [
    {"template": "title", "eyebrow": "Playbook",
     "heading": "5 ways to ship faster", "subheading": "A field-tested guide"},
    {"template": "list", "eyebrow": "The framework", "heading": "The 5 moves", "ordered": True,
     "items": ["Cut scope, not corners", "Ship behind a flag",
               "Automate the path to prod", "Review small, review often", "Measure, then decide"]},
    {"template": "cta", "eyebrow": "Your turn", "heading": "Which one will you try?",
     "body": "Save this for your next sprint.", "button": "Follow for more"},
]

res = server._render_all(
    "branded", "Ship Faster (branded)", None, "portrait", slides,
    brand_name="buildnotes",
    caption="Speed compounds. The teams that ship weekly learn 4x faster than the ones that ship monthly. Here are 5 moves that helped us cut our cycle time in half.",
    hashtags=["#shipfast", "#engineering"],
)
print("preview:", res["preview_url"])
print("--- caption.txt ---")
print(res["caption"])
