# Reel & Carousel Engagement Playbook

Craft notes for making content that actually performs. The short-form-video
principles here are **adapted** from Roman Knox's *AI Video Generator — Claude*
skills (MIT-licensed, https://github.com/rediumvex/ai-video-generator-claude),
translated to what this tool actually produces (SVG slideshow reels + carousels).
We don't generate real video, so "camera moves" map to our motion/transitions
and "lighting" maps to our Flux image prompts.

## 1. The attention model (why the hook is everything)
- **0–2s is the gate.** If half bounce here, the reel dies; if most stay, the
  algorithm promotes it. **80%+ completion ≈ 2–3× reach.**
- So: **hook lands by ~1.5–2s**, scene 1 is a scroll-stopper, total runtime
  tight (most viral reels < 15–25s).
- **Loop it:** make the last scene visually echo the first (same theme/handle
  bug) so it reads as a seamless loop on replay.
- The **cover frame** (scene 1) must also work as a static grid thumbnail.

## 2. Hook patterns (use one on scene 1)
- **Pattern interrupt** — a bold, surprising first line / high-contrast image.
- **Curiosity gap** — tease, withhold the payoff ("the #1 X isn't what you think")
  and pay it off later in the reel.
- **Provocative question / hot take** — invites comments (comments = reach).
- **Before/after** — dramatic contrast.
- **Number/paradox** — a hard stat up front ("180% more code, same ship rate").
- **Kinetic text** — our animated text + `highlight` keywords *is* this; lean on it.

## 3. Camera vocabulary → our motion/transition fields
| Their move | Our setting | Use for |
|---|---|---|
| Snap zoom | `motion:"zoomin"` + short `transition_dur` | punchy emphasis |
| Whip pan | `transition:"slideleft"` | energetic list/step swaps |
| Pull-back reveal | `motion:"zoomout"` | a reveal / the "cost" beat |
| Rise reveal | `transition:"slideup"` | launches, growth, the hook→body |
| Reveal/turn | `transition:"circleopen"` | the payoff / CTA |
Match the move to the beat — don't use one transition for everything.

## 4. Lighting presets → Flux image prompts (`background_query`)
Add this vocabulary for cinematic, scroll-stopping generated backgrounds:
- **Neon contrast:** "dual-color neon rim light, pink/cyan from opposing sides,
  hard shadows, dark background, 80% saturation, cinematic, moody".
- **Silhouette:** "full backlight silhouette, subject as black outline, blown-out
  light behind" — great for curiosity.
- **Three-point / hero:** "warm key 45° left, soft fill right, cyan rim light,
  gradient background" — premium product/hero look.
- **Golden hour / flash strobe** for warmth / energy.
(For real entities/logos, still fetch the real image — don't generate.)

## 5. Sound stack → music recommendations
Recommend audio as layers and **sync the impact to the hook payoff**:
1. ambient/near-silence bed → 2. **bass hit/whoosh synced to the hook reveal**
→ 3. music enters after ~1–2s → 4. optional VO.
Tell the creator to pick a *rising* trending sound in-app (Reels > audio >
Trending), and to put the drop on the reveal scene.

## 6. Format templates (pick the angle)
viral hook · before/after · testimonial/social-proof · faceless · SaaS/product
("Apple-keynote" clean) · course/offer promo · personal-brand authority · luxury
("Chanel-level", lots of negative space) · podcast/audio-visual · listicle (saves).

## 7. Defaults that already encode this
`create_reel` applies: bigger reel text, `highlight` keywords, per-scene
`duration`/`motion`/`transition`, a persistent brand bug, vertically-centered
fuller scenes, ≤5 hashtags, music recs, and a `strategy` brief. Use them
deliberately per beat.
