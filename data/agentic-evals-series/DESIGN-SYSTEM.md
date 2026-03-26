# MindPattern Infographic Design System

Reusable design system for shareable infographic carousels. Based on Warm Minimalism principles with Swiss typographic foundations.

---

## Philosophy

**Warm Minimalism.** Every pixel serves a purpose. Typography does the heavy lifting. Color is surgical. Whitespace is a design element, not empty space.

Think Stripe annual reports, NYT data visualization, Swiss typography, Dieter Rams — "less, but better."

---

## Color Palette

Three colors total. That's it.

| Token | Hex | Usage |
|-------|-----|-------|
| `--ink` | `#101010` | Primary text, dark blocks, bars. Never pure black. |
| `--surface` | `#F5F3EF` | Panel background. Unbleached warm white, not sterile #FFF. |
| `--surface-b` | `#EDEAE4` | Slightly deeper warm for subtle backgrounds. |
| `--accent` | `#FA5D29` | Single accent. Used ONLY for: key data points, warnings, CTAs, eyebrow labels. Max 3-4 appearances per panel. |
| `--muted` | `#8A8680` | Warm gray for secondary text, labels, descriptions. |
| `--rule` | `rgba(16,16,16,0.10)` | Major divider lines. |
| `--rule-fine` | `rgba(16,16,16,0.06)` | Grid/cell borders. |

### The 60-30-10 Rule
- **60%** `--surface` (warm white background)
- **30%** `--ink` (headings, body, dark blocks)
- **10%** `--accent` (critical data, CTAs only)

### Color Don'ts
- Never use pure `#000000` or `#FFFFFF`
- Never use green, blue, or any secondary color as decoration
- Never apply `--accent` to body text or section backgrounds
- If everything is orange, nothing stands out

---

## Typography

**Font:** Inter Tight (Google Fonts), weights 300-900.

### Type Scale (1.25 ratio, base 15px)

| Token | Size | Usage |
|-------|------|-------|
| `--text-xs` | 11px | Eyebrow labels, footer text, captions |
| `--text-sm` | 13px | Descriptions, stat labels, secondary text |
| `--text-base` | 15px | Body text, list items |
| `--text-md` | 17px | Emphasized body text |
| `--text-lg` | 21px | Lead paragraphs |
| `--text-xl` | 27px | Section subheadings |
| `--text-2xl` | 33px | Sub-titles |
| `--text-3xl` | 42px | Data points, stat values |
| `--text-4xl` | 52px | Panel titles (h2) |
| `--text-5xl` | 65px | Large display |
| `--text-6xl` | 80px | Oversized data (big-num) |

### Weight System

| Weight | Usage |
|--------|-------|
| 800 | Display headings, big numbers, panel titles |
| 700 | Item titles, stat values, emphasis |
| 600 | Eyebrow labels, section labels, tags |
| 500 | Lead text, medium emphasis |
| 400 | Body text, descriptions |
| 300 | (reserved for italic/light accents) |

### Spacing Rules

| Context | Letter-spacing |
|---------|---------------|
| Display (h1/h2) | `-0.03em` to `-0.04em` |
| Body text | `0` (default) |
| Uppercase labels | `+0.12em` to `+0.15em` |
| Tags/pills | `+0.06em` |

| Context | Line-height |
|---------|-------------|
| Display headings | `0.93` - `0.98` |
| Subheadings | `1.3` - `1.4` |
| Body text | `1.5` - `1.6` |
| Tight lists | `1.35` - `1.45` |

---

## Spacing

8px base unit.

| Token | Value |
|-------|-------|
| `--sp-1` | 4px |
| `--sp-2` | 8px |
| `--sp-3` | 12px |
| `--sp-4` | 16px |
| `--sp-5` | 24px |
| `--sp-6` | 32px |
| `--sp-7` | 40px |
| `--sp-8` | 48px |
| `--sp-9` | 56px |
| `--sp-10` | 64px |

### Panel Padding
- Top: 72px
- Sides: 80px
- Bottom: handled by footer

---

## Layout Components

### Panel
1080 x 1350px (Instagram portrait). White warm background. Three zones:
1. **Header zone** — eyebrow + panel number + title + lead
2. **Content zone** — data, sections, lists (flexbox, grows)
3. **Footer zone** — source + brand + pagination (pinned bottom)

### Stat Strip
Horizontal row of stat cells divided by 1px rules. Each cell: large number + small description. Use for 2-4 key data points.

### Two-Column Grid
Items separated by right-border + bottom-border. Each cell has title (16px, 700 weight) + description (13px, muted). Use for 4-6 related items.

### Numbered List
Index number (01-06) left-aligned, title + description right. Separated by bottom rules. Use for sequential steps.

### Dimension Bars
Label (110px fixed) + track (flex) + value. Track is 24px tall, subtle background. Fill is `--ink` for good, `rgba(0.25)` for poor, `--accent` for critical failures.

### Dark Block
`--ink` background, white text, 4px border-radius. Used sparingly for key findings or warnings. Max one per panel.

### Callout
Left border 3px `--accent`, padded text. For key insights or quotes.

### Tags/Pills
Small uppercase labels with 1px border. `.primary` variant: filled ink background, white text.

### Warning Block
Dark block variant for critical warnings. Accent-colored highlight within.

---

## Iconography

**Zero emojis.** All visual markers are typographic:
- Numbers: `01`, `02`, etc. in monospace weight
- X marks: `×` character for "don't do this"
- Arrows: `→` for CTAs
- Dots: 6px filled circles for checklists
- Dividers: 1px horizontal rules

---

## Data Visualization

- **Bar charts**: Proportional height bars (panel 3 comparison)
- **Progress bars**: Horizontal tracks with fills — `--ink` for good, muted for poor, `--accent` for failures
- **Stat numbers**: Oversized (42-80px) bold numbers as focal points
- **Status indicators**: Text-based — "Unsolved", "Early stage", "Active research"

### Tufte Principles Applied
- Maximize data-ink ratio
- No chartjunk, no decorative elements
- Let the numbers and proportions speak
- Thin rules separate, they don't decorate

---

## Branding

Every panel footer includes:
- Source attribution (left)
- MindPattern logo (20px) + "mindpattern.ai" link (center)
- Page number (right)

Logo: `logo.png` — 20px wide, 60% opacity, warms up on hover.

---

## Animation (carousel only)

- Scroll: `scroll-snap-type: x mandatory`, `scroll-behavior: smooth`
- Dots: `0.3s ease-out` transition
- Bar fills: `0.6s ease-out`
- No animation within panels (they export as static PNGs)

---

## Export

- Format: PNG via html2canvas at 2x scale
- Size: 2160 x 2700px (retina)
- Naming: `agentic-evals-01.png` through `agentic-evals-10.png`

---

## File Structure

```
data/agentic-evals-series/
  infographic.html          # The carousel
  logo.png                  # MindPattern logo
  DESIGN-SYSTEM.md          # This file
  research/
    color-theory.md
    typography.md
    iconography-imagery.md
    micro-interactions-animation.md
```
