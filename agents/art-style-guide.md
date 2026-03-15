# Art Style Guide — mindpattern Editorial Cartoons

## The Look

Black and white pen and ink editorial cartoons in the tradition of classic American and European political satire. Every image should look like it belongs on the editorial page of a major newspaper.

## Style DNA

Combine these influences (describe the characteristics, do NOT name the artists in the prompt):

- **Sharp caricature with energetic lines** — exaggerated features, oversized heads, expressive faces, loose confident strokes. Sardonic recurring characters in the margins.
- **Heavy shadows and bold contrast** — dramatic dark areas created by dense crosshatching. Towering figures, weighty compositions. High contrast black against stark white.
- **Elegant flowing single-stroke lines** — sophisticated, refined, European magazine illustration quality. Understated satire. Sparse when appropriate, maximum elegance.
- **Extraordinary architectural detail** — ornate backgrounds, intricate environments, obsessive crosshatching on surfaces. Surreal scale and impossible perspectives.
- **Gritty humanizing texture** — rough, weathered line work. Battered objects, rumpled clothes, lived-in scenes. Raw emotional honesty.

## Critical Rules

### Use Real Logos, Real People, Real Companies
- Reference actual company logos by name: "the OpenAI logo", "the Google logo", "the Salesforce logo"
- Reference real public figures by name and appearance when they're part of the story: "Sam Altman", "Dario Amodei", "Jack Dorsey", "Satya Nadella"
- NEVER use generic stand-ins. If the story is about ChatGPT, the image must show the actual ChatGPT logo, not a made-up brain symbol
- If the story names a company, that company's actual branding must be recognizable

### Black and White Only
- Pure black and white ink illustration
- No color, no grayscale wash, no sepia tones
- Crosshatching and line density create all tonal variation
- Exception: the mindpattern logo may include its signature pink ribbon detail

### The mindpattern Logo
- The logo is a minimalist black silhouette of: swept-back hair with visible strokes, thick rectangular glasses with a small pink ribbon on the right temple, and a handlebar mustache. NO eyes, NO nose, NO mouth, NO face outline, NO body. Just hair + glasses + mustache floating together as a single icon.
- The illustrator MUST read the actual logo image at `assets/logo/logo.png` before generating. Match THAT shape exactly.
- Hide it somewhere in every illustration — embedded in architecture, etched into an object, woven into shadows, formed by negative space
- It should be findable but never obvious — like Hirschfeld hiding "NINA"
- IMPORTANT: This is NOT a portrait of a person. Do NOT draw an old man, a full face, or a character wearing glasses. The logo is an abstract icon — hair/glasses/mustache only. If any human figure appears in the scene, they should look like a modern tech worker in their 30s-40s.

### Composition
- Single editorial panel (not multi-panel comic strips)
- Dramatic perspective — slightly below, slightly above, or forced perspective
- Clear visual hierarchy — the viewer's eye should go to the metaphor first
- Leave breathing room — don't fill every inch

### Visual Metaphor Over Literal Illustration
- NEVER just illustrate the headline literally
- Find the metaphor: "layoffs after building AI" → chess pieces walking off the board
- Find the contrast: "stock soared after layoffs" → champagne toast on a sinking ship
- Find the absurdity: "AI flooding open source" → avalanche of identical papers burying one person
- The best editorial cartoons make you think, then laugh, then think again

## Caption Rules
- Art Director decides per image whether a caption adds punch
- If used: one punchy line, bold, below the image
- Most images should be purely visual — the LinkedIn post text provides context

## Image Dimensions
- LinkedIn: 1080x1350 (portrait, 4:5 — maximum feed real estate)
- Bluesky: 1200x628 (landscape, ~1.91:1)
- Flux 2 Pro supports custom dimensions in multiples of 16

## Prompt Structure for Flux 2 Pro
Front-load the important elements. Flux pays more attention to what comes first.

Template:
```
[Style description — ink, crosshatching, editorial cartoon characteristics]
[The scene — who, what, where, the visual metaphor]
[Specific details — real logos, real people, specific objects with labels]
[Composition — perspective, lighting through shadow density, background detail level]
[Constraints — pure black and white ink illustration, no color]
```

Optimal prompt length: 40-80 words. Flux degrades with overly long prompts.
