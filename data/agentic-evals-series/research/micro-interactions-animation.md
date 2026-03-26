# Micro-Interactions & Animation in Web Design
## A Comprehensive Reference for Motion Design in Digital Interfaces

**Last Updated:** 2026-03-25
**Scope:** Exhaustive research covering animation principles, micro-interactions, page transitions, scroll-driven animation, CSS/JS techniques, motion design systems, performance, and accessibility.

---

## Table of Contents

1. [The 12 Principles of Animation (Disney) Applied to UI](#1-the-12-principles-of-animation-disney-applied-to-ui)
2. [Easing & Timing](#2-easing--timing)
3. [Micro-Interactions](#3-micro-interactions)
4. [Page Transitions](#4-page-transitions)
5. [Scroll-Driven Animation](#5-scroll-driven-animation)
6. [CSS Animation Techniques](#6-css-animation-techniques)
7. [JavaScript Animation Libraries](#7-javascript-animation-libraries)
8. [Motion Design Systems](#8-motion-design-systems)
9. [Purposeful vs Gratuitous Animation](#9-purposeful-vs-gratuitous-animation)
10. [Performance & Accessibility](#10-performance--accessibility)
11. [Common Animation Mistakes](#11-common-animation-mistakes)
12. [Quick Reference Tables](#12-quick-reference-tables)

---

## 1. The 12 Principles of Animation (Disney) Applied to UI

Disney's 12 principles of animation, first codified by Frank Thomas and Ollie Johnston in *The Illusion of Life* (1981), have become a foundational framework for digital motion design. Each principle maps directly to UI/web animation patterns.

### 1.1 Squash and Stretch

**Classic Definition:** Objects deform to convey weight, flexibility, and mass. A bouncing ball stretches when traveling and squashes on impact.

**UI Application:** Creates tactile feedback and conveys the physical responsiveness of interface elements. Elements compress on click and expand on release, mimicking real-world material behavior.

**Concrete Examples:**
- A button that compresses vertically when pressed, then springs back
- A toggle switch that stretches slightly as it moves between states
- A dropdown menu that slightly overshoots its final height before settling
- Pull-to-refresh indicators that stretch as users pull down

**CSS Implementation:**
```css
/* Button squash on press */
.button {
  transition: transform 0.2s cubic-bezier(0.34, 1.56, 0.64, 1);
}
.button:active {
  transform: scaleY(0.95) scaleX(1.05);
}

/* Toggle switch stretch */
.toggle-knob {
  transition: transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}
.toggle-knob.moving {
  transform: scaleX(1.2);
}
```

**Key Rule:** Always preserve volume. If an element compresses on one axis, it should expand slightly on the perpendicular axis. The total area should remain roughly constant.

**Anti-pattern:** Applying squash and stretch to rigid UI elements like text or icons where deformation feels unnatural.

---

### 1.2 Anticipation

**Classic Definition:** A preparatory movement before a main action. A character crouches before jumping.

**UI Application:** Prepares users for upcoming actions by signaling what will happen next. Prevents surprises and reduces cognitive load.

**Concrete Examples:**
- A delete button that shakes or recoils slightly before the deletion animation plays
- A card that tilts back slightly before flipping
- A menu icon whose bars begin shifting before the full menu opens
- A loading indicator that appears briefly before content loads
- A button that scales down slightly (0.97) before scaling up on hover

**CSS Implementation:**
```css
/* Button anticipation before navigation */
.nav-button {
  transition: transform 0.3s ease;
}
.nav-button:hover {
  transform: translateX(-3px); /* slight pullback */
}
.nav-button:active {
  transform: translateX(5px); /* then forward motion */
}

/* Card flip with anticipation */
@keyframes cardFlip {
  0% { transform: rotateY(0deg); }
  15% { transform: rotateY(-5deg); } /* anticipation: slight reverse */
  100% { transform: rotateY(180deg); }
}
```

**Key Rule:** Anticipation should be subtle in UI -- just enough to signal intent without slowing interaction. Keep anticipation phase to 50-100ms maximum.

**Anti-pattern:** Overly long anticipation delays that make the interface feel sluggish.

---

### 1.3 Staging

**Classic Definition:** Presenting an action clearly so it is unmistakably understood. Directing the audience's eye to the important action.

**UI Application:** Directs user attention to the most critical element on screen. Only one primary animation should command attention at a time.

**Concrete Examples:**
- A modal that dims the background before sliding in, ensuring focus on the dialog
- A primary CTA button that animates in after all other elements have settled
- An error message that shakes while other form elements remain static
- A notification badge that pulses while the rest of the header is still

**CSS Implementation:**
```css
/* Modal staging: background first, then content */
.modal-backdrop {
  animation: fadeIn 200ms ease-out;
}
.modal-content {
  animation: slideUp 300ms cubic-bezier(0.16, 1, 0.3, 1) 100ms backwards;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}
@keyframes slideUp {
  from { opacity: 0; transform: translateY(20px) scale(0.95); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}
```

**Key Rule:** Establish a clear visual hierarchy. Animate the primary action element prominently; keep secondary elements understated or static. Never animate multiple elements with equal prominence simultaneously.

---

### 1.4 Straight-Ahead Action vs. Pose-to-Pose

**Classic Definition:** Two approaches -- drawing frame-by-frame (straight-ahead) vs. planning key poses first then filling in between (pose-to-pose).

**UI Application:** CSS/web animation is inherently pose-to-pose: you define keyframe states and let the browser interpolate. JavaScript-driven, physics-based animations can feel more "straight-ahead" since each frame is dynamically calculated.

**Concrete Examples:**
- Keyframe animations (pose-to-pose): Define start, midpoint, end states for a theme transition
- Spring physics (straight-ahead): A dragged element follows the cursor with velocity-based physics, where each frame depends on the previous one
- Data visualizations that morph between states (pose-to-pose with GSAP)

**CSS Implementation:**
```css
/* Pose-to-pose: theme transition */
@keyframes themeSwitch {
  0% { background-color: #ffffff; color: #1a1a1a; }
  50% { background-color: #888888; color: #888888; }
  100% { background-color: #1a1a1a; color: #ffffff; }
}
```

**Key Rule:** Use pose-to-pose (keyframes) for predictable, well-defined state transitions. Use straight-ahead (spring physics, requestAnimationFrame) for interactive, gesture-driven animations where the outcome depends on user input velocity.

---

### 1.5 Follow-Through and Overlapping Action

**Classic Definition:** Different parts of an object stop at different times. A character's body stops but their hair and clothes continue moving.

**UI Application:** Staggered timing creates visual hierarchy and natural-feeling motion. Not everything should start and stop at the same time.

**Concrete Examples:**
- A card entering view: image appears first, then title (50ms delay), then description (100ms delay)
- A navigation menu where items cascade in from top to bottom
- A notification panel where the container slides in, then individual items stagger
- A form where input fields appear with overlapping timing

**CSS Implementation:**
```css
/* Staggered card content entrance */
.card img { animation: slideIn 0.4s ease-out; }
.card h2 { animation: slideIn 0.4s ease-out 0.05s backwards; }
.card p { animation: slideIn 0.4s ease-out 0.1s backwards; }
.card .cta { animation: slideIn 0.4s ease-out 0.15s backwards; }

@keyframes slideIn {
  from { opacity: 0; transform: translateY(15px); }
  to { opacity: 1; transform: translateY(0); }
}

/* Stagger children with CSS custom properties */
.stagger-container > * {
  animation: fadeInUp 400ms cubic-bezier(0.16, 1, 0.3, 1) backwards;
}
.stagger-container > *:nth-child(1) { animation-delay: 0ms; }
.stagger-container > *:nth-child(2) { animation-delay: 50ms; }
.stagger-container > *:nth-child(3) { animation-delay: 100ms; }
.stagger-container > *:nth-child(4) { animation-delay: 150ms; }
.stagger-container > *:nth-child(5) { animation-delay: 200ms; }
```

**Key Rule:** Stagger delays should be short (20-80ms between items). Total stagger sequence should not exceed 300-400ms. Keep individual item delays consistent.

**Anti-pattern:** Staggering with delays over 100ms between items, creating a tedious "domino" effect that wastes users' time.

---

### 1.6 Slow In and Slow Out (Easing)

**Classic Definition:** Objects accelerate when starting and decelerate when stopping. Real-world physics -- nothing starts or stops instantly.

**UI Application:** The single most important animation principle for UI. Easing determines whether motion feels natural or robotic. See Section 2 for deep coverage.

**Key Rule:** Never use `linear` timing for UI motion (exception: continuous rotations like spinners). Always apply easing curves. Ease-out for entrances, ease-in for exits.

---

### 1.7 Arcs

**Classic Definition:** Natural motion follows curved paths, not straight lines. A thrown ball follows a parabolic arc.

**UI Application:** Elements that move through space should follow slightly curved trajectories when the path is long enough to notice.

**Concrete Examples:**
- Drag-and-drop items following a curved path to their destination
- FAB (Floating Action Button) expansion following an arc
- File icons traveling in an arc to the trash/recycle bin
- Navigation transitions that curve slightly rather than moving linearly

**CSS Implementation:**
```css
/* Arc path using multiple keyframes */
@keyframes arcToTrash {
  0% { transform: translate(0, 0) scale(1); opacity: 1; }
  40% { transform: translate(80px, -40px) scale(0.8); opacity: 0.8; }
  100% { transform: translate(200px, 60px) scale(0.3); opacity: 0; }
}

/* CSS offset-path for true curved motion */
.moving-element {
  offset-path: path('M 0 0 Q 150 -80 300 20');
  animation: followArc 500ms ease-in-out forwards;
}
@keyframes followArc {
  from { offset-distance: 0%; }
  to { offset-distance: 100%; }
}
```

**Key Rule:** Arcs matter most for elements traveling significant distances (>100px). For short movements, straight-line motion with proper easing is sufficient.

---

### 1.8 Secondary Action

**Classic Definition:** Supporting animations that supplement the primary action without distracting from it.

**UI Application:** Complementary visual effects that reinforce the primary action's meaning.

**Concrete Examples:**
- When an item is added to cart: primary action is the "Added" button state change; secondary is a small particle burst or the cart icon bouncing
- When a form submits: primary is the success checkmark; secondary is confetti particles
- When deleting: primary is the item sliding out; secondary is the list items shifting up to fill the gap
- When a notification arrives: primary is the badge appearing; secondary is a subtle highlight flash on the icon

**Key Rule:** Secondary actions must never compete with or overshadow the primary action. They should be shorter in duration and lower in visual prominence. If removing the secondary action doesn't reduce understanding, it's doing its job right.

---

### 1.9 Timing

**Classic Definition:** The speed of an action conveys its weight, mood, and personality. Faster = lighter/more energetic. Slower = heavier/more deliberate.

**UI Application:** Duration communicates the significance and nature of an action. Quick feedback for small interactions; longer transitions for major state changes.

**Duration Guidelines:**
| Action Type | Duration Range | Rationale |
|---|---|---|
| Button press feedback | 80-100ms | Must feel instant |
| Tooltip appear | 100-150ms | Informational, shouldn't distract |
| Micro-interactions | 150-200ms | Quick but noticeable |
| Button hover | 200ms | Fast responsiveness |
| Dropdown/menu | 200-250ms | Predictable, avoid bounce |
| Modal entrance | 250-300ms | Larger element needs grace |
| Page transition | 300-500ms | Major context change |
| Success celebration | 500-800ms | Celebration deserves emphasis |
| Complex choreography | 600-1000ms | Total sequence duration |

**Key Rule:** Most UI animations should fall between 150-400ms. Anything under 100ms feels instantaneous (and may not register). Anything over 500ms feels slow (and may block interaction).

---

### 1.10 Exaggeration

**Classic Definition:** Amplifying an action to make it more dynamic and readable. Not distortion, but emphasis.

**UI Application:** Subtle exaggeration makes interactions more satisfying without being distracting. The key is restraint.

**Concrete Examples:**
- A "like" heart that scales to 1.3x before settling at 1x (overshoot)
- An error shake that travels 6-8px instead of a barely-visible 2px
- A success checkmark that draws with a slight bounce at the end
- A badge counter that briefly scales up when incrementing

**CSS Implementation:**
```css
/* Like button with exaggerated spring */
@keyframes likeHeart {
  0% { transform: scale(1); }
  15% { transform: scale(1.35); }
  30% { transform: scale(0.9); }
  45% { transform: scale(1.1); }
  60% { transform: scale(0.95); }
  100% { transform: scale(1); }
}
.like-btn.active .heart {
  animation: likeHeart 600ms cubic-bezier(0.34, 1.56, 0.64, 1);
}
```

**Key Rule:** Exaggeration in UI should be 10-30% beyond the natural endpoint. Going further risks feeling cartoonish. The scale of exaggeration should match the importance of the action.

---

### 1.11 Solid Drawing (Consistency)

**Classic Definition:** Maintaining consistent volume, perspective, and weight throughout animation.

**UI Application:** Animation should maintain consistent physics, perspective, and visual rules across the entire interface. Shadows, depth, and spatial relationships must remain coherent.

**Concrete Examples:**
- Shadows that grow proportionally as an element "lifts" on hover
- 3D transforms that maintain consistent vanishing points
- Scale animations where shadows adjust realistically
- Cards that maintain consistent border-radius during transforms

**CSS Implementation:**
```css
/* Consistent shadow elevation on hover */
.card {
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
  transition: transform 200ms ease-out, box-shadow 200ms ease-out;
}
.card:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 24px rgba(0,0,0,0.15);
}
```

**Key Rule:** Define a consistent elevation system. If a card lifts 4px on hover, its shadow should grow proportionally. Never mix flat and 3D animation paradigms in the same interface.

---

### 1.12 Appeal

**Classic Definition:** Making the character or action engaging and pleasing. The animation equivalent of charisma.

**UI Application:** Motion should add personality and delight to the interface, making it memorable and emotionally engaging.

**Concrete Examples:**
- A playful loading animation that tells a micro-story
- Onboarding illustrations that animate to explain features
- A 404 page with a charming animated character
- Branded micro-interactions that express company personality (Mailchimp's high-five, Slack's loading messages)
- Easter egg animations discovered through unexpected interactions

**Key Rule:** Appeal should never come at the cost of usability. Delightful animations should be brief and non-blocking. After the first impression fades, animation must remain functional and non-irritating.

---

## 2. Easing & Timing

Easing is the single most impactful aspect of UI animation quality. It determines whether motion feels natural or robotic, smooth or jarring, intentional or accidental.

### 2.1 Why Linear Motion Feels Wrong

Linear motion (constant velocity) violates every expectation humans have about how objects move in the physical world. Nothing in nature starts at full speed and stops instantaneously. Linear motion feels:
- **Robotic** -- like a machine moving on a track
- **Artificial** -- our brains immediately recognize it as "computer-generated"
- **Disconnected** -- it creates no sense of weight, mass, or materiality

**The only valid use of linear timing** is for continuous, non-directional motion: loading spinners, progress bar fills, color cycling, and looping background animations.

### 2.2 Cubic-Bezier Curves Explained

CSS easing functions are defined using `cubic-bezier(x1, y1, x2, y2)` where:
- `x1, y1` define the first control point (influences the start of the curve)
- `x2, y2` define the second control point (influences the end of the curve)
- The x-axis represents time (0 to 1)
- The y-axis represents progress (0 to 1, but can exceed this range)

**Key insight:** x values must be between 0 and 1 (time can't go backward), but y values can exceed 0-1, creating overshoot/bounce effects.

```
cubic-bezier(0.34, 1.56, 0.64, 1)
              ^     ^     ^    ^
              |     |     |    +-- end: arrives exactly at target
              |     |     +------- second handle x: late adjustment
              |     +------------- first handle y: overshoots to 156%!
              +------------------- first handle x: early acceleration
```

### 2.3 CSS Keyword Easings

| Keyword | Cubic-Bezier | Character | When to Use |
|---|---|---|---|
| `linear` | `(0, 0, 1, 1)` | Constant speed | Spinners, progress fills only |
| `ease` | `(0.25, 0.1, 0.25, 1)` | Gentle, default | Browser default; rarely optimal |
| `ease-in` | `(0.42, 0, 1, 1)` | Slow start, fast end | Elements exiting/leaving the screen |
| `ease-out` | `(0, 0, 0.58, 1)` | Fast start, slow end | Elements entering/appearing |
| `ease-in-out` | `(0.42, 0, 0.58, 1)` | Slow start and end | Elements moving within the viewport |

### 2.4 Production-Ready Easing Curves

These are battle-tested curves used in production by top design teams:

**Spring-Like (Energetic):** `cubic-bezier(0.34, 1.56, 0.64, 1)`
- Slight overshoot creates a playful, tactile feel
- Best for: button interactions, cards, success feedback, micro-interactions
- Avoid for: large page transitions, critical user actions

**Smooth Ease-Out (Gentle):** `cubic-bezier(0.16, 1, 0.3, 1)`
- Very gentle deceleration with no overshoot
- Professional feel with minimal settling time
- Best for: modals, page transitions, large elements, drawers, panels
- Avoid for: small quick interactions (feels sluggish at small scale)

**Fast Response (Snappy):** `cubic-bezier(0.4, 0, 0.2, 1)`
- Quick acceleration and deceleration
- Immediate and responsive feel
- Best for: toggles, checkboxes, tooltips, icons, loading spinners
- Avoid for: large movements (too abrupt), decorative animations

**Material Design Standard:** `cubic-bezier(0.2, 0, 0, 1)`
- M3's workhorse easing for most transitions
- Balanced responsiveness with smooth settling

**Material Design Emphasized Decelerate:** `cubic-bezier(0.05, 0.7, 0.1, 1)`
- Dramatic deceleration for important entrances
- Elements arrive quickly and settle softly

**Material Design Emphasized Accelerate:** `cubic-bezier(0.3, 0, 0.8, 0.15)`
- Quick start for exits and dismissals

### 2.5 The Easing Functions Cheat Sheet

**Sine Family (Subtle, gentle):**
- `easeInSine`: `cubic-bezier(0.47, 0, 0.745, 0.715)`
- `easeOutSine`: `cubic-bezier(0.39, 0.575, 0.565, 1)`
- `easeInOutSine`: `cubic-bezier(0.445, 0.05, 0.55, 0.95)`

**Cubic Family (Natural, balanced):**
- `easeInCubic`: `cubic-bezier(0.55, 0.055, 0.675, 0.19)`
- `easeOutCubic`: `cubic-bezier(0.215, 0.61, 0.355, 1)`
- `easeInOutCubic`: `cubic-bezier(0.645, 0.045, 0.355, 1)`

**Quart/Quint Family (Pronounced, dramatic):**
- `easeOutQuart`: `cubic-bezier(0.165, 0.84, 0.44, 1)`
- `easeOutQuint`: `cubic-bezier(0.23, 1, 0.32, 1)`

**Expo Family (Extreme acceleration/deceleration):**
- `easeInExpo`: `cubic-bezier(0.95, 0.05, 0.795, 0.035)`
- `easeOutExpo`: `cubic-bezier(0.19, 1, 0.22, 1)`

**Back Family (Overshoot):**
- `easeInBack`: `cubic-bezier(0.6, -0.28, 0.735, 0.045)`
- `easeOutBack`: `cubic-bezier(0.175, 0.885, 0.32, 1.275)`
- `easeInOutBack`: `cubic-bezier(0.68, -0.55, 0.265, 1.55)`

### 2.6 The `linear()` Timing Function

The `linear()` function (not the keyword `linear`) is a breakthrough CSS feature that enables true spring physics and complex easing curves in pure CSS.

**How it works:** You provide discrete points along the easing curve, and the browser draws straight lines between them. With enough points (25-75+), any curve can be approximated.

```css
/* Basic spring approximation */
.element {
  transition: transform 500ms linear(
    0, 0.013 0.6%, 0.05 1.2%, 0.2 2.5%,
    0.5 5.4%, 0.78 8.7%, 0.95 12%,
    1.05 16%, 1.08 18%, 1.05 22%,
    1.02 26%, 0.99 30%, 1.005 38%,
    1 46%, 0.998 54%, 1 62%, 1
  );
}
```

**Key advantages:**
- Spring physics in pure CSS (no JavaScript required)
- Bounce, elastic, and wiggle effects previously impossible with cubic-bezier
- Negligible performance impact even with 100+ points
- ~1.3KB gzipped for three maximum-accuracy spring functions

**Limitations:**
- Requires explicit duration (springs are naturally duration-less)
- Mid-animation interruptions feel unnatural (browser applies "reversing shortening factor")
- ~88% browser support as of late 2025

**Best practice:** Store `linear()` functions in CSS custom properties:
```css
:root {
  --spring-smooth: cubic-bezier(0.16, 1, 0.3, 1); /* fallback */
  --spring-smooth-time: 600ms;
}
@supports (animation-timing-function: linear(0, 1)) {
  :root {
    --spring-smooth: linear(
      0, 0.006, 0.025 2.8%, 0.101 6.1%,
      0.539 18.9%, 0.721 25.3%, 0.849 31.5%,
      0.937 38.1%, 0.968 41.8%, 0.991 45.7%,
      1.006 50.1%, 1.015 55%, 1.017 63.9%,
      1.001 85.6%, 1
    );
  }
}
```

**Tools for generating `linear()` values:**
- Linear Easing Generator by Jake Archibald & Adam Argyle
- Easing Wizard
- easings.net for reference curves

### 2.7 Spring Physics

Spring physics represent a fundamentally different paradigm from duration-based animation. Instead of specifying "move from A to B in 300ms," you describe the physical properties of a spring, and the animation duration emerges naturally.

**Three Parameters:**

| Parameter | Effect | Low Value | High Value |
|---|---|---|---|
| **Tension/Stiffness** | How tightly wound the spring is | Gentle, slow | Snappy, bouncy |
| **Friction/Damping** | Resistance that slows oscillation | Very bouncy | No bounce (critically damped) |
| **Mass** | Weight of the attached object | Responsive, quick | Sluggish, deliberate |

**Why springs feel better than duration-based animation:**
- They naturally incorporate velocity (a gesture's speed carries into the animation)
- They feel "alive" and responsive rather than predetermined
- They resolve the "what duration should this be?" question organically
- They handle interruption gracefully -- a spring can be redirected mid-flight

**When to use springs:**
- Physical properties: position (x, y), scale, rotation
- Gesture-driven interactions: drag, swipe, flick
- Interactive feedback: button presses, toggles

**When NOT to use springs:**
- Color transitions (use duration-based easing)
- Opacity transitions (springs can cause opacity overshoot past 1.0)
- Progress indicators (users expect predictable linear progress)

**Implementation requires JavaScript** -- there is no native CSS spring function (though the `linear()` function can approximate springs). Libraries: Framer Motion, React Spring, Motion One.

**Material Design 3 Spring Tokens:**

| Token | Damping | Stiffness | Use Case |
|---|---|---|---|
| `motionSpringFastSpatial` | 0.9 | 1400 | Quick positional animations |
| `motionSpringFastEffects` | 1.0 | 3800 | Snappy visual effects (no bounce) |
| `motionSpringDefaultSpatial` | 0.9 | 700 | Standard movement |
| `motionSpringDefaultEffects` | 1.0 | 1600 | Standard visual effects |
| `motionSpringSlowSpatial` | 0.9 | 300 | Deliberate, heavy movement |
| `motionSpringSlowEffects` | 1.0 | 800 | Slow visual effects |

### 2.8 The Relationship Between Duration and Distance

Duration should scale with the magnitude of change:
- **Small changes** (button state, icon swap): 100-200ms
- **Medium changes** (dropdown, panel expand): 200-350ms
- **Large changes** (full-screen transition, modal): 300-500ms
- **Very large changes** (page-level transitions): 400-800ms

**Rule of thumb:** Increase duration by ~50ms for every 100px of travel distance, up to a maximum of about 700ms.

The larger the change in distance or size, the longer the animation should take. But never let duration grow linearly with distance -- use a logarithmic relationship so very large movements don't feel tediously slow.

---

## 3. Micro-Interactions

### 3.1 Dan Saffer's Framework

Dan Saffer defined micro-interactions as "contained product moments that revolve around a single use case." His framework identifies four components:

**1. Trigger** -- What initiates the micro-interaction
- **Manual triggers:** User-initiated (click, tap, swipe, hover, scroll, keyboard input)
- **System triggers:** Condition-based (timer expires, data received, threshold reached, geolocation change)

**2. Rules** -- What happens after the trigger fires
- The logic that determines the micro-interaction's behavior
- Defines what can and cannot happen
- Controls sequencing and conditions
- Example: "When the user clicks 'Submit' AND all fields are valid, show the success state. ELSE, highlight the invalid fields."

**3. Feedback** -- How the system communicates its response
- **Visual:** Color changes, opacity shifts, icon morphs, progress indicators
- **Auditory:** Click sounds, success chimes, error tones
- **Haptic:** Vibrations (mobile), force feedback
- **Motion:** Animation that reinforces the state change

**4. Loops and Modes** -- How the interaction evolves over time
- **Loops:** Repeated behaviors (a notification badge that pulses every 30 seconds)
- **Modes:** Alternate states that change the interaction's rules (Do Not Disturb mode suppresses notifications)
- **Progressive disclosure:** Reducing animation intensity over repeated use (first-time delight vs. efficiency for power users)

### 3.2 Button States

Buttons are the most common micro-interaction surface. Each state requires distinct visual feedback:

```css
/* Complete button state system */
.button {
  /* Default state */
  background: #2563eb;
  color: white;
  border: none;
  padding: 12px 24px;
  border-radius: 8px;
  cursor: pointer;
  transition:
    transform 200ms cubic-bezier(0.34, 1.56, 0.64, 1),
    background-color 150ms ease,
    box-shadow 200ms ease;
}

/* Hover: elevated, brighter */
.button:hover {
  background: #3b82f6;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(37, 99, 235, 0.3);
}

/* Active/Pressed: compressed, darker */
.button:active {
  transform: scale(0.97);
  background: #1d4ed8;
  box-shadow: 0 1px 2px rgba(37, 99, 235, 0.2);
  transition-duration: 80ms;
  transition-timing-function: cubic-bezier(0.4, 0, 0.2, 1);
}

/* Focus: visible ring for keyboard navigation */
.button:focus-visible {
  outline: 2px solid #2563eb;
  outline-offset: 2px;
}

/* Disabled: muted, no interaction */
.button:disabled {
  background: #94a3b8;
  cursor: not-allowed;
  transform: none;
  box-shadow: none;
}

/* Loading state */
.button.loading {
  pointer-events: none;
  position: relative;
  color: transparent;
}
.button.loading::after {
  content: '';
  position: absolute;
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255,255,255,0.3);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 600ms linear infinite;
}

@media (prefers-reduced-motion: reduce) {
  .button {
    transition: background-color 150ms ease;
  }
  .button:hover { transform: none; }
  .button:active { transform: none; }
}
```

**Timing rules for button states:**
- Hover transition: 200ms (fast enough to feel responsive)
- Active/press: 80ms (must feel instant)
- Release spring-back: 200ms with spring curve
- Focus ring: instant (0ms) or very fast (50ms)

### 3.3 Loading States

#### Skeleton Screens
Skeleton screens display a wireframe-like placeholder that mirrors the final layout structure, providing spatial context while content loads.

```css
/* Base skeleton element */
.skeleton {
  background: hsl(200, 20%, 88%);
  border-radius: 4px;
  position: relative;
  overflow: hidden;
}

/* Shimmer (wave) effect -- preferred */
.skeleton::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(
    90deg,
    transparent 0%,
    rgba(255, 255, 255, 0.4) 50%,
    transparent 100%
  );
  transform: translateX(-100%);
  animation: shimmer 1.5s ease-in-out infinite;
}

@keyframes shimmer {
  to { transform: translateX(100%); }
}

/* Pulse effect -- simpler alternative */
.skeleton-pulse {
  animation: pulse 1.5s ease-in-out infinite;
}
@keyframes pulse {
  0%, 100% { background: hsl(200, 20%, 88%); }
  50% { background: hsl(200, 20%, 95%); }
}

/* Synchronized shimmer across multiple elements */
.skeleton-sync::after {
  background-attachment: fixed; /* syncs gradient across all elements */
}
```

**Key principles for skeleton screens:**
- Match the shape and layout of actual content (text lines, images, avatars)
- Wave/shimmer is preferred over pulse (feels faster and more active)
- Don't add skeleton screens for loads under 300ms (use instant rendering instead)
- Transition from skeleton to real content with a subtle fade (200ms)

#### Spinners and Progress Bars

```css
/* Simple spinner */
.spinner {
  width: 24px;
  height: 24px;
  border: 2px solid rgba(0, 0, 0, 0.1);
  border-top-color: #2563eb;
  border-radius: 50%;
  animation: spin 600ms linear infinite;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}

/* Determinate progress bar */
.progress-bar {
  height: 4px;
  background: #e2e8f0;
  border-radius: 2px;
  overflow: hidden;
}
.progress-bar-fill {
  height: 100%;
  background: #2563eb;
  border-radius: 2px;
  transition: width 300ms cubic-bezier(0.4, 0, 0.2, 1);
}

/* Indeterminate progress bar */
.progress-indeterminate::after {
  content: '';
  display: block;
  height: 100%;
  width: 30%;
  background: #2563eb;
  border-radius: 2px;
  animation: indeterminate 1.5s ease-in-out infinite;
}
@keyframes indeterminate {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(400%); }
}

@media (prefers-reduced-motion: reduce) {
  .spinner { animation-duration: 1200ms; }
  .progress-indeterminate::after { animation-duration: 3s; }
}
```

**When to use which loading pattern:**
- **Skeleton screens:** Content loading where layout is known (feeds, dashboards, lists)
- **Spinners:** Short operations (<3 seconds), unknown layout, inline feedback
- **Progress bars:** Operations with measurable progress (file upload, data processing)
- **Shimmer overlays:** Refreshing existing content (pull-to-refresh)

### 3.4 Toggle Animations

```css
/* iOS-style toggle switch */
.toggle {
  width: 52px;
  height: 32px;
  background: #cbd5e1;
  border-radius: 16px;
  padding: 2px;
  cursor: pointer;
  transition: background-color 200ms ease;
}
.toggle.active {
  background: #2563eb;
}

.toggle-knob {
  width: 28px;
  height: 28px;
  background: white;
  border-radius: 50%;
  box-shadow: 0 1px 3px rgba(0,0,0,0.2);
  transition: transform 300ms cubic-bezier(0.34, 1.56, 0.64, 1);
}
.toggle.active .toggle-knob {
  transform: translateX(20px);
}
```

### 3.5 Form Validation Feedback

```css
/* Error shake animation */
@keyframes shake {
  0%, 100% { transform: translateX(0); }
  20% { transform: translateX(-6px); }
  40% { transform: translateX(6px); }
  60% { transform: translateX(-4px); }
  80% { transform: translateX(4px); }
}

.input-error {
  border-color: #ef4444;
  animation: shake 400ms cubic-bezier(0.36, 0.07, 0.19, 0.97);
}

/* Success check animation */
@keyframes checkDraw {
  0% { stroke-dashoffset: 30; }
  100% { stroke-dashoffset: 0; }
}
.check-icon {
  stroke-dasharray: 30;
  stroke-dashoffset: 30;
  animation: checkDraw 300ms ease-out forwards;
}

/* Error message entrance */
.error-message {
  animation: slideDown 200ms ease-out;
}
@keyframes slideDown {
  from { opacity: 0; transform: translateY(-8px); max-height: 0; }
  to { opacity: 1; transform: translateY(0); max-height: 50px; }
}
```

### 3.6 Notification Badges

```css
/* Badge appearance with bounce */
@keyframes badgePop {
  0% { transform: scale(0); }
  50% { transform: scale(1.3); }
  70% { transform: scale(0.9); }
  100% { transform: scale(1); }
}
.badge {
  animation: badgePop 400ms cubic-bezier(0.34, 1.56, 0.64, 1);
}

/* Badge count increment */
@keyframes countBump {
  0% { transform: scale(1); }
  50% { transform: scale(1.2); }
  100% { transform: scale(1); }
}
.badge.updated {
  animation: countBump 300ms ease-out;
}
```

### 3.7 Toast/Snackbar Notifications

```css
/* Toast entrance from bottom */
.toast {
  position: fixed;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%) translateY(120%);
  opacity: 0;
  transition:
    transform 300ms cubic-bezier(0.16, 1, 0.3, 1),
    opacity 200ms ease;
}
.toast.visible {
  transform: translateX(-50%) translateY(0);
  opacity: 1;
}

/* Toast exit */
.toast.exiting {
  transform: translateX(-50%) translateY(120%);
  opacity: 0;
  transition:
    transform 200ms cubic-bezier(0.4, 0, 1, 1),
    opacity 150ms ease;
}
```

### 3.8 Tooltip Reveals

```css
/* Tooltip with delayed entrance */
.tooltip {
  opacity: 0;
  transform: translateY(4px);
  pointer-events: none;
  transition:
    opacity 150ms ease,
    transform 150ms ease;
  transition-delay: 0ms; /* no delay on exit */
}
.trigger:hover .tooltip {
  opacity: 1;
  transform: translateY(0);
  transition-delay: 300ms; /* 300ms hover delay before showing */
}
```

### 3.9 Scroll Progress Indicators

```css
/* Reading progress bar using scroll-driven animation */
.progress-indicator {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: #2563eb;
  transform-origin: left;
  animation: growProgress linear;
  animation-timeline: scroll(root);
}
@keyframes growProgress {
  from { transform: scaleX(0); }
  to { transform: scaleX(1); }
}
```

---

## 4. Page Transitions

### 4.1 The View Transitions API

The View Transitions API is the native browser solution for animated transitions between views. It works for both SPAs (same-document transitions) and MPAs (cross-document transitions).

**Browser Support (2025-2026):** Chrome 111+, Edge 111+, Safari 18+, Firefox 144+. Baseline Newly Available across all major browsers.

#### Same-Document Transitions (SPAs)

```javascript
// Basic usage
document.startViewTransition(() => {
  // Update the DOM
  updateContent(newData);
});

// With configuration and types
document.startViewTransition({
  update: () => updateContent(newData),
  types: ['slide', 'forwards']
});

// With async updates (React, Vue, Svelte)
document.startViewTransition(async () => {
  // React
  flushSync(() => setState(newState));

  // Vue
  // state.value = newValue;
  // await nextTick();

  // Svelte
  // data = newData;
  // await tick();
});
```

#### Pseudo-Element Tree

When a view transition runs, the browser creates this pseudo-element structure:

```
::view-transition
 +-- ::view-transition-group(root)
 |    +-- ::view-transition-image-pair(root)
 |         +-- ::view-transition-old(root)  [screenshot of old state]
 |         +-- ::view-transition-new(root)  [live new state]
 +-- ::view-transition-group(header)
      +-- ::view-transition-image-pair(header)
           +-- ::view-transition-old(header)
           +-- ::view-transition-new(header)
```

#### Named View Transitions (Shared Element / Hero Animations)

```css
/* Give elements unique view-transition-names */
.product-thumbnail {
  view-transition-name: product-image;
}
.product-full-image {
  view-transition-name: product-image; /* same name = shared transition */
}

/* Header stays in place during page transitions */
.site-header {
  view-transition-name: site-header;
}

/* Automatic name matching (2025+) */
.list-item {
  view-transition-name: match-element; /* browser auto-generates unique names */
}
```

#### Customizing View Transition Animations

```css
/* Slide transitions based on navigation direction */
@keyframes slide-from-right {
  from { transform: translateX(100%); }
}
@keyframes slide-to-left {
  to { transform: translateX(-100%); }
}
@keyframes fade-in {
  from { opacity: 0; }
}
@keyframes fade-out {
  to { opacity: 0; }
}

/* Forward navigation */
html:active-view-transition-type(forwards) {
  &::view-transition-old(root) {
    animation:
      90ms cubic-bezier(0.4, 0, 1, 1) both fade-out,
      300ms cubic-bezier(0.4, 0, 0.2, 1) both slide-to-left;
  }
  &::view-transition-new(root) {
    animation:
      210ms cubic-bezier(0, 0, 0.2, 1) 90ms both fade-in,
      300ms cubic-bezier(0.4, 0, 0.2, 1) both slide-from-right;
  }
}

/* Backward navigation */
html:active-view-transition-type(backwards) {
  &::view-transition-old(root) {
    animation-name: fade-out, slide-to-right;
  }
  &::view-transition-new(root) {
    animation-name: fade-in, slide-from-left;
  }
}
```

#### Cross-Document Transitions (MPAs)

```css
/* Both pages must opt in */
@view-transition {
  navigation: auto;
}

/* Customize the cross-document transition */
::view-transition-old(root) {
  animation: fade-out 200ms ease;
}
::view-transition-new(root) {
  animation: fade-in 300ms ease;
}
```

#### Circular Reveal Transition (JavaScript-driven)

```javascript
function navigateWithCircularReveal(data) {
  const x = lastClick?.clientX ?? innerWidth / 2;
  const y = lastClick?.clientY ?? innerHeight / 2;
  const endRadius = Math.hypot(
    Math.max(x, innerWidth - x),
    Math.max(y, innerHeight - y)
  );

  const transition = document.startViewTransition(() => {
    updateContent(data);
  });

  transition.ready.then(() => {
    document.documentElement.animate(
      {
        clipPath: [
          `circle(0 at ${x}px ${y}px)`,
          `circle(${endRadius}px at ${x}px ${y}px)`,
        ],
      },
      {
        duration: 500,
        easing: 'ease-in',
        pseudoElement: '::view-transition-new(root)',
      }
    );
  });
}
```

#### Reduced Motion Support

```css
@media (prefers-reduced-motion) {
  ::view-transition-group(*),
  ::view-transition-old(*),
  ::view-transition-new(*) {
    animation: none !important;
  }
}
```

### 4.2 Common Page Transition Patterns

#### Crossfade
The simplest and most universal transition. Old content fades out while new content fades in. The View Transitions API does this by default.

#### Slide
Content slides in from one direction. Common for tab interfaces, carousels, and wizard flows. Direction should match navigation direction (forward = left-to-right in LTR layouts).

#### Scale/Zoom
Content scales up from a thumbnail to full view (or vice versa). Ideal for image galleries, card-to-detail transitions.

#### Morph
Elements transform from one shape/position to another. The View Transitions API handles this automatically for elements with matching `view-transition-name` values.

#### Staggered List Entrance
List items appear sequentially with short delays. Total animation sequence should not exceed 400ms.

### 4.3 Page Load Sequences

**Above-the-fold first:** Critical content at the top of the viewport animates in first. Below-fold content loads and animates progressively as users scroll.

**Progressive reveal pattern:**
1. Navigation/header: instant or 0ms (already visible)
2. Hero content: 0-100ms delay
3. Primary CTA: 100-200ms delay
4. Supporting content: 200-300ms delay
5. Footer/secondary: no animation (loads silently)

### 4.4 Skeleton-to-Content Transitions

```css
/* Skeleton to content fade */
.content-container {
  position: relative;
}
.skeleton-layer {
  position: absolute;
  inset: 0;
  transition: opacity 200ms ease;
}
.content-container.loaded .skeleton-layer {
  opacity: 0;
  pointer-events: none;
}
.content-layer {
  opacity: 0;
  transition: opacity 200ms ease 50ms; /* slight delay */
}
.content-container.loaded .content-layer {
  opacity: 1;
}
```

---

## 5. Scroll-Driven Animation

### 5.1 CSS Scroll-Driven Animations API

The CSS Scroll-Driven Animations API allows you to control animations based on scroll position rather than time. This is a pure CSS solution that runs on the compositor thread for optimal performance.

**Browser Support (2025-2026):** Chrome 115+, Edge 115+, Safari 18+, Firefox 110+ (full support across all major browsers).

### 5.2 Two Timeline Types

#### Scroll Timelines (`scroll()`)
Progress is based on the scroll position of a scroll container.

```css
/* Basic scroll progress */
.element {
  animation: fadeIn linear;
  animation-timeline: scroll(); /* defaults to nearest scroll container, block axis */
}

/* Specific scroller and axis */
.element {
  animation-timeline: scroll(root block);    /* root scroller, vertical */
  animation-timeline: scroll(nearest inline); /* nearest scroller, horizontal */
  animation-timeline: scroll(self);           /* element's own scroll */
}
```

#### View Timelines (`view()`)
Progress is based on an element's visibility within its scroll container.

```css
/* Basic view-based animation */
.element {
  animation: revealUp linear;
  animation-timeline: view(); /* 0% = element enters viewport, 100% = exits */
}

/* With axis and inset */
.element {
  animation-timeline: view(block);            /* vertical visibility */
  animation-timeline: view(inline 100px);     /* horizontal with inset */
  animation-timeline: view(block 0px 200px);  /* different start/end insets */
}
```

### 5.3 Animation Range

The `animation-range` property controls which portion of the scroll/view timeline drives the animation:

```css
/* Animate only during entry */
.element {
  animation: fadeIn linear;
  animation-timeline: view();
  animation-range: entry 0% entry 100%;
}

/* Animate while fully visible */
.element {
  animation-range: contain 0% contain 100%;
}

/* Animate during exit */
.element {
  animation-range: exit 0% exit 100%;
}

/* Custom range */
.element {
  animation-range: entry 25% exit 75%;
}

/* Full journey (entry through exit) */
.element {
  animation-range: cover 0% cover 100%;
}
```

**Range keywords:**
- `entry`: Element entering the scrollport (from first pixel visible to fully visible)
- `exit`: Element leaving the scrollport
- `contain`: Element fully contained within the scrollport
- `cover`: Full journey from first pixel visible to last pixel leaving

### 5.4 Named Scroll Timelines

```css
/* Define a named timeline on a scroll container */
.scroll-container {
  scroll-timeline-name: --main-scroll;
  scroll-timeline-axis: block;
}

/* Reference the named timeline from a descendant */
.animated-child {
  animation: slideIn linear;
  animation-timeline: --main-scroll;
}

/* Named view timeline */
.observed-element {
  view-timeline-name: --element-view;
  view-timeline-axis: block;
}
.other-element {
  animation: respond linear;
  animation-timeline: --element-view;
}
```

### 5.5 Practical Scroll Animation Examples

#### Reading Progress Bar

```css
.progress-bar {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: linear-gradient(to right, #667eea, #764ba2);
  transform-origin: left;
  animation: growProgress linear;
  animation-timeline: scroll(root);
}
@keyframes growProgress {
  from { transform: scaleX(0); }
  to { transform: scaleX(1); }
}
```

#### Fade-In Reveal on Scroll

```css
.reveal-section {
  animation: fadeInUp linear;
  animation-timeline: view();
  animation-range: entry 0% cover 40%;
}
@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(50px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
```

#### Parallax Layers

```css
.parallax-back {
  animation: parallaxSlow linear;
  animation-timeline: scroll(root);
}
.parallax-mid {
  animation: parallaxMedium linear;
  animation-timeline: scroll(root);
}
@keyframes parallaxSlow {
  to { transform: translateY(200px); }
}
@keyframes parallaxMedium {
  to { transform: translateY(100px); }
}
```

#### Text Color Reveal

```css
.reveal-text {
  background: linear-gradient(
    to right,
    #1a1a1a 0%, #1a1a1a 50%,
    #ccc 50%, #ccc 100%
  );
  background-size: 200% 100%;
  background-clip: text;
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  animation: revealText linear;
  animation-timeline: view();
  animation-range: entry 0% cover 40%;
}
@keyframes revealText {
  from { background-position: 100% 0; }
  to { background-position: 0% 0; }
}
```

#### Horizontal Scroll Gallery

```css
.gallery {
  display: flex;
  overflow-x: auto;
  scroll-snap-type: x mandatory;
}
.gallery-item {
  scroll-snap-align: center;
  animation: scaleOnScroll linear;
  animation-timeline: view(inline);
  animation-range: entry 0% cover 50%;
}
@keyframes scaleOnScroll {
  from { transform: scale(0.7); opacity: 0.3; }
  to { transform: scale(1); opacity: 1; }
}
```

### 5.6 Performance Characteristics

**Compositor thread vs. main thread:**

CSS scroll-driven animations that use only `transform` and `opacity` run entirely on the compositor thread. This means:
- They never block the main thread
- They never cause layout recalculations
- They maintain smooth 60fps even during heavy JavaScript execution
- They do not trigger paint operations

**This is a major advantage over JavaScript scroll handlers**, which:
- Run on the main thread
- Can cause jank if not properly throttled
- Require `requestAnimationFrame` for smooth results
- May compete with other JavaScript tasks for CPU time

### 5.7 Feature Detection

```css
@supports (animation-timeline: scroll()) {
  .element {
    animation: fadeIn linear;
    animation-timeline: scroll();
  }
}

@supports not (animation-timeline: scroll()) {
  /* Fallback: use IntersectionObserver in JavaScript */
  .element {
    opacity: 1;
    transform: none;
  }
}
```

### 5.8 Accessibility for Scroll-Driven Animation

```css
@media (prefers-reduced-motion: reduce) {
  * {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
  }
  .reveal-section {
    animation: none !important;
    opacity: 1 !important;
    transform: none !important;
  }
}
```

---

## 6. CSS Animation Techniques

### 6.1 Transitions vs. Keyframe Animations

**Use `transition` when:**
- Animating between exactly two states (A and B)
- The animation is triggered by a state change (hover, focus, class toggle)
- You need interruptibility (transitions handle mid-flight interruptions gracefully)

**Use `@keyframes` when:**
- You need more than two states
- You need animations that run without user interaction
- You need animations that loop or play in sequence
- You need independent control of direction, iteration, and fill mode

```css
/* Transition: two-state */
.element {
  transition: transform 300ms cubic-bezier(0.16, 1, 0.3, 1);
}
.element:hover {
  transform: translateY(-4px);
}

/* Keyframes: multi-state */
@keyframes pulse {
  0% { transform: scale(1); opacity: 1; }
  50% { transform: scale(1.05); opacity: 0.8; }
  100% { transform: scale(1); opacity: 1; }
}
.element {
  animation: pulse 2s ease-in-out infinite;
}
```

### 6.2 Transform Operations (The Performance Champions)

Transforms are the foundation of performant animation because they operate on the compositor thread without triggering layout or paint:

```css
/* The four transform functions */
.element {
  /* Move: translateX(), translateY(), translate(), translate3d() */
  transform: translateX(100px);
  transform: translate(50px, 30px);
  transform: translate3d(50px, 30px, 0); /* forces GPU layer */

  /* Scale: scaleX(), scaleY(), scale() */
  transform: scale(1.5);
  transform: scaleX(0.8) scaleY(1.2);

  /* Rotate: rotate(), rotateX(), rotateY(), rotate3d() */
  transform: rotate(45deg);
  transform: rotateY(180deg); /* 3D flip */

  /* Skew: skewX(), skewY(), skew() */
  transform: skewX(-5deg);
}

/* Combining transforms */
.element {
  transform: translateX(100px) scale(1.2) rotate(10deg);
  /* Order matters! Transforms apply right-to-left */
}
```

**Why transforms are cheap:**
1. The browser promotes the element to its own compositor layer
2. The GPU handles the transformation math
3. No layout recalculation needed (the element's box model doesn't change)
4. No repaint needed (the texture is just repositioned/stretched/rotated)

### 6.3 Opacity Animations

Opacity is the other GPU-accelerated property. Animating opacity does not trigger layout or paint, only compositing.

```css
.fade-element {
  transition: opacity 200ms ease;
}
.fade-element.hidden {
  opacity: 0;
}
```

**Important detail:** An element with `opacity: 0` is invisible but still occupies space and is still interactive. Use `visibility: hidden` or `pointer-events: none` to prevent interaction with hidden elements.

### 6.4 The `will-change` Property

`will-change` tells the browser to prepare for upcoming animations by promoting the element to its own compositor layer ahead of time.

```css
/* Apply before animation starts */
.will-animate-soon {
  will-change: transform, opacity;
}

/* Remove after animation completes */
.animation-done {
  will-change: auto;
}
```

**Critical rules for `will-change`:**
- It is a **last resort** optimization, not a default
- Each element with `will-change` creates a new compositor layer, consuming GPU memory
- Overuse causes performance degradation (the opposite of what you want)
- Apply it dynamically (e.g., on mouseenter) and remove it after the animation
- Never apply `will-change` to more than a handful of elements simultaneously
- The `transform: translateZ(0)` hack achieves a similar effect but is even more brute-force

### 6.5 CSS Custom Properties for Dynamic Animation

```css
/* Dynamic stagger using custom properties */
.stagger-item {
  animation: fadeInUp 400ms ease backwards;
  animation-delay: calc(var(--index) * 50ms);
}

/* In HTML or JavaScript: */
/* <div class="stagger-item" style="--index: 0"> */
/* <div class="stagger-item" style="--index: 1"> */
/* <div class="stagger-item" style="--index: 2"> */
```

```css
/* Dynamic duration based on distance */
.sliding-element {
  --travel-distance: 200px;
  --base-duration: 200ms;
  --duration: calc(var(--base-duration) + var(--travel-distance) * 0.5ms);
  transition: transform var(--duration) ease-out;
}
```

### 6.6 `@property` for Animatable Custom Properties

Standard CSS custom properties cannot be animated because the browser treats them as strings. `@property` registers typed custom properties that the browser can interpolate.

```css
/* Register a custom property as a color */
@property --gradient-start {
  syntax: '<color>';
  initial-value: #667eea;
  inherits: false;
}
@property --gradient-end {
  syntax: '<color>';
  initial-value: #764ba2;
  inherits: false;
}

/* Now you can animate gradients! */
.gradient-bg {
  background: linear-gradient(135deg, var(--gradient-start), var(--gradient-end));
  transition: --gradient-start 500ms ease, --gradient-end 500ms ease;
}
.gradient-bg:hover {
  --gradient-start: #f093fb;
  --gradient-end: #f5576c;
}
```

```css
/* Animated conic gradient (e.g., pie chart) */
@property --angle {
  syntax: '<angle>';
  initial-value: 0deg;
  inherits: false;
}

.pie-chart {
  background: conic-gradient(#2563eb var(--angle), #e2e8f0 var(--angle));
  border-radius: 50%;
  transition: --angle 1s cubic-bezier(0.16, 1, 0.3, 1);
}
.pie-chart.loaded {
  --angle: 270deg; /* 75% */
}
```

**Supported `@property` syntax types:**
- `<color>` -- color interpolation
- `<length>` -- px, rem, em, etc.
- `<percentage>` -- percentage values
- `<number>` -- raw numbers
- `<angle>` -- deg, rad, turn
- `<integer>` -- whole numbers
- `<length-percentage>` -- either length or percentage
- `<custom-ident>` -- custom identifiers (not animatable)

**Browser Support:** Chrome 85+, Edge 85+, Safari 15.4+, Firefox 128+.

### 6.7 The `contain` Property for Animation Performance

```css
/* Isolate animated elements from affecting sibling layout */
.animated-card {
  contain: layout style paint;
}

/* Most restrictive -- best performance */
.self-contained-animation {
  contain: strict; /* equivalent to size layout paint style */
}
```

`contain` tells the browser that changes inside this element won't affect anything outside it, allowing aggressive optimization of paint and layout calculations.

### 6.8 Multiple Animations with Different Easings

```css
/* Apply different timing to different properties */
.element {
  transition:
    opacity 300ms linear,
    transform 400ms cubic-bezier(0.34, 1.56, 0.64, 1);
}

/* Or use multiple keyframe animations */
@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}
@keyframes slideUp {
  from { transform: translateY(20px); }
  to { transform: translateY(0); }
}
.element {
  animation:
    fadeIn 300ms linear forwards,
    slideUp 400ms cubic-bezier(0.16, 1, 0.3, 1) forwards;
}
```

---

## 7. JavaScript Animation Libraries

### 7.1 When to Use CSS vs. JavaScript

**Choose CSS when:**
- Simple state transitions (hover, active, focus)
- Animations tied to pseudo-classes
- Scroll-driven animations (CSS Scroll-Driven API)
- Performance-critical animations on many elements
- No complex sequencing or conditional logic needed
- Bundle size is a concern

**Choose JavaScript when:**
- Complex timelines with sequencing and callbacks
- Physics-based motion (springs, velocity, friction)
- Gesture-driven interactions (drag, pinch, flick)
- Dynamic animations based on runtime values
- Animations that need to be interrupted and redirected
- Orchestrating many elements with precise choreography

### 7.2 GSAP (GreenSock Animation Platform)

**Bundle size:** ~23KB gzipped (core), plugins add 5-15KB each
**Framework support:** Any (vanilla JS, React, Vue, Angular, Svelte)

GSAP is the industry standard for complex web animation. Key features:

**Timeline:**
```javascript
const tl = gsap.timeline({ defaults: { ease: 'power2.out' } });

tl.from('.hero-title', { y: 60, opacity: 0, duration: 0.8 })
  .from('.hero-subtitle', { y: 40, opacity: 0, duration: 0.6 }, '-=0.4')
  .from('.hero-cta', { scale: 0.8, opacity: 0, duration: 0.5 }, '-=0.3')
  .from('.hero-image', { x: 100, opacity: 0, duration: 1 }, '-=0.6');
```

**ScrollTrigger:**
```javascript
gsap.to('.parallax-bg', {
  y: '30%',
  ease: 'none',
  scrollTrigger: {
    trigger: '.hero-section',
    start: 'top top',
    end: 'bottom top',
    scrub: 1, // smooth scrubbing with 1s lag
    pin: true, // pin element during scroll
  }
});
```

**SplitText (text animation):**
```javascript
const split = new SplitText('.headline', { type: 'chars,words' });

gsap.from(split.chars, {
  y: 50,
  opacity: 0,
  stagger: 0.03,
  duration: 0.6,
  ease: 'power2.out',
  scrollTrigger: {
    trigger: '.headline',
    start: 'top 80%',
  }
});
```

**Flip (layout animation):**
```javascript
// Record initial state
const state = Flip.getState('.grid-item');

// Change the layout
container.classList.toggle('reordered');

// Animate from old positions to new
Flip.from(state, {
  duration: 0.6,
  ease: 'power2.inOut',
  stagger: 0.05,
  absolute: true,
});
```

### 7.3 Motion (formerly Framer Motion)

**Bundle size:** ~32KB gzipped
**Framework support:** React (primary), vanilla JS

Motion is the de facto animation library for React applications. It provides a declarative API.

**Basic component animation:**
```jsx
import { motion } from 'motion/react';

function Card() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      transition={{
        duration: 0.3,
        ease: [0.16, 1, 0.3, 1]
      }}
    >
      Card content
    </motion.div>
  );
}
```

**AnimatePresence (exit animations):**
```jsx
import { AnimatePresence, motion } from 'motion/react';

function App() {
  const [items, setItems] = useState([...]);

  return (
    <AnimatePresence>
      {items.map(item => (
        <motion.div
          key={item.id}
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: 'auto' }}
          exit={{ opacity: 0, height: 0 }}
          transition={{ duration: 0.3 }}
        >
          {item.text}
        </motion.div>
      ))}
    </AnimatePresence>
  );
}
```

**Layout animations (automatic FLIP):**
```jsx
<motion.div layout>
  {/* When this element's position changes in the DOM,
      it automatically animates to its new position */}
</motion.div>
```

**Spring physics:**
```jsx
<motion.div
  animate={{ x: 100 }}
  transition={{
    type: 'spring',
    stiffness: 300,
    damping: 20,
    mass: 1
  }}
/>
```

**Gesture animations:**
```jsx
<motion.button
  whileHover={{ scale: 1.05 }}
  whileTap={{ scale: 0.95 }}
  transition={{
    type: 'spring',
    stiffness: 400,
    damping: 17
  }}
>
  Click me
</motion.button>
```

**Reduced motion support:**
```jsx
import { useReducedMotion } from 'motion/react';

function Component() {
  const shouldReduceMotion = useReducedMotion();

  return (
    <motion.div
      animate={{ x: 100 }}
      transition={shouldReduceMotion
        ? { duration: 0 }
        : { type: 'spring', stiffness: 300 }
      }
    />
  );
}
```

### 7.4 Lottie

**Use case:** Designer-created animations from After Effects exported as JSON.
**Bundle size:** ~50KB (lottie-web player)

**Key characteristics:**
- Vector-based, resolution-independent
- Tiny file sizes (kilobytes) for complex animations
- Pixel-perfect replication of After Effects compositions
- Cross-platform (web, iOS, Android)
- Pre-defined timelines -- not interactive

**When to use Lottie:**
- Complex illustrative animations (onboarding, empty states, celebrations)
- Brand animations and logo reveals
- Icon animations (loading, success, error states)
- Animations designed by motion designers in After Effects

**When NOT to use Lottie:**
- Simple CSS-achievable animations (use CSS instead)
- Interactive/physics-based animations (use Motion/GSAP)
- Animations that need to respond to real-time data
- Performance-critical scenarios on low-end devices

### 7.5 Three.js

**Use case:** 3D graphics, WebGL-based animations, immersive experiences.
**Bundle size:** ~150KB+ gzipped

**When to use Three.js:**
- Product 3D visualizations and configurators
- Interactive 3D backgrounds
- Data visualizations in 3D space
- WebGL-based particle effects
- Anything requiring actual 3D geometry

**Not for:** Standard UI animations, 2D transitions, or simple micro-interactions.

### 7.6 Anime.js

**Bundle size:** ~17KB gzipped
**Use case:** Lightweight, framework-agnostic animation library.

```javascript
anime({
  targets: '.element',
  translateX: 250,
  rotate: '1turn',
  duration: 800,
  easing: 'easeInOutQuad',
  delay: anime.stagger(100),
});
```

### 7.7 Animation Technology Decision Framework

| Scenario | Best Choice | Rationale |
|---|---|---|
| Simple hover/focus effects | CSS | Zero overhead, best performance |
| State transitions (show/hide) | CSS transitions | Interruptible, lightweight |
| Scroll-driven reveals | CSS Scroll-Driven API | Compositor thread, no JS |
| Complex page sequences | GSAP | Timeline control, precise choreography |
| React component animations | Motion | Declarative, layout animations, exit animations |
| Designer-created illustrations | Lottie | Bridges design-to-dev workflow |
| State-driven interactive animations | Rive | Built-in state machine |
| Interactive storytelling | GSAP + ScrollTrigger | Scrubbing, pinning, complex timelines |
| Physics-based motion | Motion or React Spring | Native spring support |
| 3D product visualization | Three.js | Full WebGL 3D engine |
| Simple framework-agnostic | Anime.js | Lightweight, clean API |

---

## 8. Motion Design Systems

### 8.1 Why Motion Needs a System

Without a motion design system, animations across an application become inconsistent -- different durations, different easing curves, different behaviors for similar interactions. A motion design system provides:

- **Consistency:** Every similar interaction feels the same
- **Efficiency:** Developers don't reinvent animation decisions
- **Scalability:** New features automatically inherit the motion language
- **Quality:** A curated set of motion patterns prevents gratuitous animation

### 8.2 Motion Tokens

Motion tokens encapsulate timing, easing, and delay values into named, reusable variables. They are the foundation of a motion design system.

#### Duration Tokens

Material Design 3 duration scale:

| Token | Value | Use Case |
|---|---|---|
| `duration-short-1` | 50ms | Instant state changes |
| `duration-short-2` | 100ms | Tooltips, micro-feedback |
| `duration-short-3` | 150ms | Small interactions |
| `duration-short-4` | 200ms | Button hover, toggle |
| `duration-medium-1` | 250ms | Dropdown, menu |
| `duration-medium-2` | 300ms | Page transition (default) |
| `duration-medium-3` | 350ms | Complex transitions |
| `duration-medium-4` | 400ms | Large element entrance |
| `duration-long-1` | 450ms | Full-screen transitions |
| `duration-long-2` | 500ms | Complex choreography |
| `duration-long-3` | 550ms | Expanded sequences |
| `duration-long-4` | 600ms | Maximum single-element duration |
| `duration-extra-long-1` | 700ms | Multi-element orchestration |
| `duration-extra-long-2` | 800ms | Complex sequences |
| `duration-extra-long-3` | 900ms | Extended choreography |
| `duration-extra-long-4` | 1000ms | Maximum total sequence |

#### Easing Tokens

Material Design 3 easing curves:

| Token | Cubic-Bezier | Use Case |
|---|---|---|
| `standard` | `cubic-bezier(0.2, 0, 0, 1)` | Most transitions |
| `standard-decelerate` | `cubic-bezier(0, 0, 0, 1)` | Elements entering |
| `standard-accelerate` | `cubic-bezier(0.3, 0, 1, 1)` | Elements exiting |
| `emphasized` | Path-based (complex) | Important transitions |
| `emphasized-decelerate` | `cubic-bezier(0.05, 0.7, 0.1, 1)` | Important entrances |
| `emphasized-accelerate` | `cubic-bezier(0.3, 0, 0.8, 0.15)` | Important exits |

#### CSS Token Implementation

```css
:root {
  /* Duration tokens */
  --motion-duration-instant: 50ms;
  --motion-duration-fast: 150ms;
  --motion-duration-normal: 250ms;
  --motion-duration-slow: 400ms;
  --motion-duration-slower: 600ms;

  /* Easing tokens */
  --motion-ease-standard: cubic-bezier(0.2, 0, 0, 1);
  --motion-ease-decelerate: cubic-bezier(0, 0, 0, 1);
  --motion-ease-accelerate: cubic-bezier(0.3, 0, 1, 1);
  --motion-ease-spring: cubic-bezier(0.34, 1.56, 0.64, 1);

  /* Composite tokens (semantic) */
  --motion-enter: var(--motion-duration-normal) var(--motion-ease-decelerate);
  --motion-exit: var(--motion-duration-fast) var(--motion-ease-accelerate);
  --motion-standard: var(--motion-duration-normal) var(--motion-ease-standard);
  --motion-spring: var(--motion-duration-normal) var(--motion-ease-spring);
}

/* Usage */
.modal {
  transition: transform var(--motion-enter), opacity var(--motion-enter);
}
.modal.closing {
  transition: transform var(--motion-exit), opacity var(--motion-exit);
}
```

### 8.3 Motion Categories

#### Productive Motion (IBM Carbon)
- Efficient and responsive
- Subtle and out of the way
- For task-completion moments
- Shorter durations, gentler curves
- Used for: dropdowns, tooltips, data tables, form interactions

#### Expressive Motion (IBM Carbon)
- Enthusiastic and vibrant
- Highly visible
- For moments of delight and major state changes
- Longer durations, more dramatic curves
- Used for: onboarding, empty states, celebrations, feature introductions

### 8.4 Choreography Principles

**Sequential choreography:** Elements animate one after another in a defined order.

```css
/* Sequential: header, then content, then footer */
.header { animation-delay: 0ms; }
.content { animation-delay: 100ms; }
.footer { animation-delay: 200ms; }
```

**Staggered choreography:** Similar elements animate with overlapping timing.

```css
/* Staggered: list items cascade */
.list-item:nth-child(n) {
  animation-delay: calc((n - 1) * 50ms);
}
```

**Rules for choreography:**
1. Begin each item's staggered entrance no more than 20ms apart (Material Design recommendation)
2. Total stagger sequence should not exceed 300-400ms
3. Primary actions animate first, secondary actions follow
4. Elements closest to the trigger point animate first
5. Larger elements should animate before smaller ones (they establish the spatial context)

### 8.5 Enter, Exit, and Shared Motion Patterns

| Pattern | Enter | Exit |
|---|---|---|
| **Fade** | Opacity 0 to 1 | Opacity 1 to 0 |
| **Slide** | From offscreen direction | To opposite direction |
| **Scale** | From small (0.95) to normal | From normal to small (0.95) |
| **Expand** | Height/width from 0 to auto | Height/width from auto to 0 |
| **Shared** | Morph from previous element | Morph to next element |

**Enter animations** should use **ease-out** (decelerate): elements arrive quickly and settle softly.

**Exit animations** should use **ease-in** (accelerate): elements depart gently then speed away.

**Shared element transitions** should use **ease-in-out**: smooth acceleration and deceleration.

### 8.6 Apple Human Interface Guidelines -- Motion Principles

Apple's motion design philosophy emphasizes:

1. **Purposeful motion:** Every animation must communicate something -- status, feedback, instruction, or spatial orientation
2. **Realism and credibility:** Motion should obey physical laws; defying physics disorients users
3. **Quick and precise:** Brevity and precision make animations feel lightweight and non-intrusive
4. **Optional motion:** Animations must not be the only way to communicate information. Always respect Reduce Motion settings

### 8.7 Microsoft Fluent Design -- Motion Principles

Fluent 2's motion system is built on:

1. **Timing, easing, directionality, and gravity** as foundational elements
2. **Natural and quick** motion that considers element size and travel distance
3. **Consistency across products** to strengthen the Fluent identity
4. **Hierarchy** to direct attention through ordered animation sequences

### 8.8 `prefers-reduced-motion` in Design Systems

Every motion token should have a reduced-motion variant:

```css
:root {
  --motion-duration-normal: 250ms;
  --motion-ease-standard: cubic-bezier(0.2, 0, 0, 1);
}

@media (prefers-reduced-motion: reduce) {
  :root {
    --motion-duration-normal: 0ms;
    --motion-ease-standard: linear;
    /* Or keep subtle opacity transitions: */
    /* --motion-duration-normal: 100ms; */
  }
}
```

**Important nuance:** "Reduced motion" does not mean "no motion." Consider:
- Replacing transform animations with opacity-only fades
- Reducing travel distances
- Shortening durations significantly
- Keeping progress indicators functional
- Maintaining state change feedback (just without motion)

---

## 9. Purposeful vs. Gratuitous Animation

### 9.1 When Animation Serves UX

The Nielsen Norman Group identifies four legitimate purposes for UI animation:

#### 1. Feedback for Micro-Interactions
Animation confirms that the system recognized the user's action. Without feedback, users may:
- Click again (causing double submissions)
- Assume the interface is broken
- Miss that their action succeeded

**Examples:** Button press state, cart badge update, form submission confirmation, toggle switch movement.

#### 2. Communicating State Changes
Animation makes state transitions visible and comprehensible.

**Examples:** Icon morphing (hamburger to X), skeleton-to-content loading, progress indicators, dark/light mode transitions.

#### 3. Spatial Orientation
Animation helps users understand where they are in an information hierarchy and where things went.

**Examples:**
- Zooming in = going deeper in hierarchy; zooming out = going higher
- Sliding right = moving forward; sliding left = going back
- Smooth scrolling to anchor = "this content is on the same page"
- Shared element transitions = "this thumbnail IS that full-screen image"

#### 4. Signification (Affordance)
Motion direction signals how elements can be interacted with.

**Examples:**
- A card that enters from the bottom can be dismissed by swiping down
- A notification that slides in from the right can be swiped right to dismiss
- A list item that bounces on hold signals that swiping reveals actions

### 9.2 When Animation Hurts UX

**"The best animation is the one you don't notice."** If users are consciously aware of an animation, it's either (a) serving a critical purpose or (b) getting in their way.

#### Motion Sickness and Vestibular Disorders
- Over 35% of adults experience vestibular dysfunction by age 40
- Large-scale motion, parallax, zooming, and scrolljacking can trigger dizziness, nausea, and vertigo
- Symptoms can persist long after the user has left the page
- 3% of people with epilepsy have photosensitive epilepsy; rapid flashing can trigger seizures

#### Attention Hijacking
Humans detect motion through peripheral vision (rod photoreceptors) as an evolutionary survival mechanism. This makes it nearly impossible to ignore motion, meaning poorly-used animation is uniquely disruptive.

**Problematic patterns:**
- Decorative animations that loop continuously
- Multiple simultaneous animations competing for attention
- Animations that play during content-heavy reading experiences
- Auto-playing video backgrounds
- Parallax effects on text-heavy pages

#### Slow Perceived Performance
Animations that take too long or animate before allowing interaction create the perception of slowness. Users in usability testing consistently report frustration with:
- Entrance animations that play before content is interactive
- Slide-out menus that block interaction until animation completes
- Loading animations that feel longer than the actual load
- Transition animations between pages that add unnecessary delay

#### Battery and Resource Drain
Complex animations -- especially JavaScript-driven ones, canvas/WebGL effects, and continuously running animations -- consume CPU/GPU resources and drain battery on mobile devices.

### 9.3 The Decision Framework

Before adding any animation, ask:

1. **Does this animation help the user understand something they couldn't understand without it?** (spatial relationship, state change, affordance)
2. **Does this animation provide feedback that would otherwise be missed?** (small state changes far from focus point)
3. **Can the information be communicated without animation?** If yes, is the animation still justified for perceived performance or delight?
4. **Will this animation still feel good on the 100th use?** (first-time delight fades; functional animation doesn't)
5. **Does this animation block or delay interaction?** If yes, reconsider.
6. **Is there a reduced-motion alternative?** There must be.

### 9.4 The Delight Spectrum

| Category | Example | Delight Duration | When Justified |
|---|---|---|---|
| **Functional** | Button press feedback | Permanent (always useful) | Always |
| **Informative** | Loading skeleton | Permanent (always useful) | Always |
| **Orientational** | Page slide transition | Permanent (reduces confusion) | Always |
| **Celebratory** | Success confetti | ~3 uses before fading | Milestone moments only |
| **Decorative** | Background particle effects | ~1 use before ignored | Rarely; brand pages only |
| **Gratuitous** | Entrance animation on every scroll | 0 uses (immediately annoying) | Never |

---

## 10. Performance & Accessibility

### 10.1 The Rendering Pipeline

Every frame of animation requires the browser to potentially execute five steps:

```
JavaScript → Style → Layout → Paint → Composite
```

| Step | What Happens | Properties That Trigger |
|---|---|---|
| **JavaScript** | Run JS animation logic | requestAnimationFrame callbacks |
| **Style** | Recalculate computed styles | Any CSS change |
| **Layout** | Recalculate element geometry | width, height, margin, padding, top, left, right, bottom, font-size, border |
| **Paint** | Draw pixels for each element | color, background, box-shadow, border-radius, outline, text-decoration |
| **Composite** | Combine painted layers | transform, opacity (ONLY THESE SKIP LAYOUT + PAINT) |

### 10.2 The GPU-Accelerated Properties

Only two CSS properties can be animated without triggering layout or paint:

| Property | Rendering Cost | Notes |
|---|---|---|
| `transform` | Composite only | translate, scale, rotate, skew -- all cheap |
| `opacity` | Composite only | Fading in/out |

**Every other animated property triggers at least paint, and many trigger layout:**

**Layout triggers (most expensive):**
- `width`, `height`, `min-*`, `max-*`
- `margin`, `padding`
- `top`, `left`, `right`, `bottom`
- `border-width`
- `font-size`, `line-height`
- `display`, `position`, `float`

**Paint triggers (expensive):**
- `color`, `background-color`, `background-image`
- `box-shadow`, `text-shadow`
- `border-radius`, `border-color`
- `outline`, `text-decoration`
- `filter` (especially blur)

### 10.3 Frame Budget

At 60fps, you have **16.67ms per frame** to complete all work:

```
16.67ms = JavaScript + Style + Layout + Paint + Composite
```

At 120fps (increasingly common on modern displays): **8.33ms per frame**.

If your animation work exceeds the frame budget, the browser drops frames, causing visible jank.

**Practical implications:**
- `transform` and `opacity` animations: ~0.1ms per frame (compositor-only)
- `background-color` animation: ~2-4ms per frame (triggers paint)
- `height` animation: ~5-15ms per frame (triggers layout + paint + composite)
- Complex `box-shadow` animation: ~3-8ms per frame (triggers paint)

### 10.4 `requestAnimationFrame`

For JavaScript-driven animations, always use `requestAnimationFrame` instead of `setTimeout` or `setInterval`:

```javascript
function animate(timestamp) {
  // Update animation state based on timestamp
  element.style.transform = `translateX(${progress}px)`;

  if (progress < target) {
    requestAnimationFrame(animate);
  }
}
requestAnimationFrame(animate);
```

**Why rAF is essential:**
- Synchronizes with the browser's repaint cycle
- Automatically pauses when the tab is backgrounded (saves battery)
- Provides a high-precision timestamp for consistent timing
- Runs before each repaint, not on an arbitrary timer

**Browser throttling awareness:**
- Background tabs: rAF is throttled to ~1fps or paused entirely
- iOS Low Power Mode: rAF throttled to 30fps
- Cross-origin iframes: May be throttled to 30fps before user interaction

### 10.5 IntersectionObserver for Lazy Animation

Only animate elements that are visible:

```javascript
const observer = new IntersectionObserver(
  (entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('animate-in');
        observer.unobserve(entry.target); // animate once only
      }
    });
  },
  { threshold: 0.1, rootMargin: '50px' }
);

document.querySelectorAll('.animate-on-scroll').forEach(el => {
  observer.observe(el);
});
```

This approach is being superseded by CSS scroll-driven animations for simple reveal effects, but IntersectionObserver remains valuable for:
- Triggering JavaScript animations
- Starting/stopping expensive animations (canvas, WebGL)
- Lazy-loading animation assets (Lottie files, video)

### 10.6 Accessibility: `prefers-reduced-motion`

This is a **non-negotiable requirement** for any animated interface.

#### Detection

```css
/* CSS: reduce or remove motion */
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
```

```javascript
// JavaScript: detect preference
const prefersReducedMotion = window.matchMedia(
  '(prefers-reduced-motion: reduce)'
).matches;

// Listen for changes
window.matchMedia('(prefers-reduced-motion: reduce)')
  .addEventListener('change', (event) => {
    if (event.matches) {
      // User now prefers reduced motion
      disableAnimations();
    } else {
      enableAnimations();
    }
  });
```

#### Implementation Strategies

**Strategy 1: Global animation disable (nuclear option)**
```css
@media (prefers-reduced-motion: reduce) {
  * { animation: none !important; transition: none !important; }
}
```
Simple but removes all feedback, including useful state changes.

**Strategy 2: Selective reduction (recommended)**
```css
/* Keep functional feedback, remove decorative motion */
@media (prefers-reduced-motion: reduce) {
  /* Replace movement with opacity */
  .modal {
    animation: fadeOnly 200ms ease forwards;
  }
  @keyframes fadeOnly {
    from { opacity: 0; }
    to { opacity: 1; }
  }

  /* Remove parallax and scroll effects */
  .parallax { transform: none !important; }

  /* Slow down spinners (don't remove them) */
  .spinner { animation-duration: 1.5s; }

  /* Keep progress indicators functional */
  .progress-bar { transition: width 100ms linear; }
}
```

**Strategy 3: Opt-in animation (progressive enhancement)**
```css
/* Default: no motion */
.element {
  opacity: 1;
  transform: none;
}

/* Only animate for users who haven't requested reduced motion */
@media (prefers-reduced-motion: no-preference) {
  .element {
    animation: fadeInUp 300ms ease-out;
  }
}
```

#### WCAG Guidelines

- **WCAG 2.1 SC 2.3.1:** No content flashes more than 3 times per second
- **WCAG 2.1 SC 2.3.3:** Motion animation triggered by interaction can be disabled
- **WCAG 2.1 SC 2.2.2:** Moving, blinking, scrolling content lasting >5 seconds must have a pause mechanism

#### Who Is Affected

| Condition | Prevalence | Triggered By |
|---|---|---|
| Vestibular disorders | 35% of adults 40+ | Parallax, zoom, large-scale motion |
| Photosensitive epilepsy | 3% of epilepsy patients | Rapid flashing, high-contrast strobing |
| ADHD | 5-10% of population | Continuous motion, auto-playing animation |
| Motion sickness | Varies widely | Scrolljacking, background video, parallax |
| Migraine disorders | 12% of population | Flashing, high-contrast patterns |

### 10.7 Performance Debugging Checklist

1. **Chrome DevTools Performance tab:** Record animation and look for long frames (>16.67ms)
2. **Rendering tab:** Enable "Paint flashing" to see what's being repainted
3. **FPS meter:** Enable in Rendering tab to monitor frame rate
4. **Layers panel:** Check how many compositor layers are created
5. **Lighthouse:** Run performance audit for animation impact
6. **Test on low-end devices:** Performance bottlenecks are most visible on older Android phones
7. **Test in Safari:** Safari's rendering pipeline differs from Chromium; test thoroughly

---

## 11. Common Animation Mistakes

### 11.1 Too Slow

**The problem:** Animations that take too long make the interface feel sluggish and test user patience. This is the #1 most common animation mistake.

**The threshold:** If you can consciously think "I'm waiting for this animation to finish," it's too slow.

**The fix:** Most UI animations should be 150-400ms. Test by making the animation faster until it feels too fast, then back off slightly. The sweet spot is usually faster than you'd expect.

### 11.2 Too Fast

**The problem:** Animations under 100ms are often imperceptible. They provide no visual feedback and waste code.

**The fix:** If an animation needs to exist, it should be at least 100ms (ideally 150ms+) to register consciously. If it doesn't need to be seen, remove it entirely.

### 11.3 Too Many Things Moving at Once

**The problem:** Multiple prominent animations competing for attention. The eye doesn't know where to look. Each animation diminishes the impact of every other animation.

**The fix:** Apply the staging principle. Only one primary animation should command attention at any given moment. Secondary animations should be subtle and supportive.

### 11.4 Inconsistent Easing

**The problem:** Different easing curves on similar elements create a disjointed, unprofessional feel. Research indicates 83% of users prefer familiarity with movement styles, and 62% express dissatisfaction with disjointed visual behavior.

**The fix:** Define 2-3 easing curves in your motion tokens and use them consistently. One for entrances (ease-out), one for exits (ease-in), one for general motion (ease-in-out or standard).

### 11.5 Animating Expensive Properties

**The problem:** Animating properties that trigger layout recalculation:

```css
/* BAD: Triggers layout on every frame */
.element {
  transition: width 300ms ease, height 300ms ease, margin-left 300ms ease;
}

/* BAD: Box-shadow is a paint operation */
.card:hover {
  transition: box-shadow 300ms ease;
  box-shadow: 0 20px 60px rgba(0,0,0,0.3);
}
```

**The fix:**
```css
/* GOOD: Use transform instead */
.element {
  transition: transform 300ms ease;
}
.element.expanded {
  transform: scaleX(1.5) scaleY(1.5) translateX(50px);
}

/* GOOD: Use pseudo-element for shadow */
.card {
  position: relative;
}
.card::after {
  content: '';
  position: absolute;
  inset: 0;
  box-shadow: 0 20px 60px rgba(0,0,0,0.3);
  opacity: 0;
  transition: opacity 300ms ease;
  border-radius: inherit;
}
.card:hover::after {
  opacity: 1;
}
```

### 11.6 Not Respecting Reduced Motion

**The problem:** Ignoring `prefers-reduced-motion` entirely, causing physical discomfort for users with vestibular disorders.

**The fix:** Always implement `prefers-reduced-motion`. See Section 10.6 for implementation strategies.

### 11.7 Animation Without Purpose

**The problem:** Adding animation because "it looks cool" rather than because it serves a function. After the initial novelty fades, purposeless animation becomes an annoyance that slows down every interaction.

**The fix:** For every animation, articulate what it communicates. If you can't name its purpose (feedback, orientation, state change, signification), remove it.

### 11.8 Blocking User Interaction During Animation

**The problem:** Disabling buttons, links, or scroll during animation playback. Users must wait for the animation to complete before they can proceed.

**The fix:** All animations should be interruptible. CSS transitions support interruption natively. For JavaScript animations, ensure your library supports cancellation (GSAP's `.kill()`, Motion's gesture interruption).

### 11.9 Entrance Animations on Every Scroll

**The problem:** Elements that animate every time they enter the viewport during scroll, creating a distracting carnival effect on long pages.

**The fix:** Animate elements once on first appearance, then stop observing them:

```javascript
observer.observe(element);
// In callback:
if (entry.isIntersecting) {
  entry.target.classList.add('revealed');
  observer.unobserve(entry.target); // IMPORTANT: stop watching
}
```

### 11.10 Using `ease-in` for Entrances

**The problem:** `ease-in` (slow start, fast finish) makes entering elements feel like they're accelerating toward the user. This creates a jarring, uncomfortable effect.

**The fix:** Use `ease-out` (fast start, slow finish) for entrances. Elements should arrive quickly and settle softly. Use `ease-in` only for exits.

### 11.11 Linear Easing on UI Elements

**The problem:** Using `linear` (constant speed) for any directional motion. It feels mechanical, robotic, and unnatural.

**The fix:** Reserve `linear` exclusively for:
- Continuous rotation (spinners)
- Progress bar fills
- Color cycling
- Scroll-driven animations where scroll position IS the easing

### 11.12 Forgetting Exit Animations

**The problem:** Elements that appear with a beautiful entrance animation but disappear instantly without a corresponding exit.

**The fix:** Every entrance animation should have a matching exit animation. Exits should typically be faster than entrances (asymmetric timing). In React, use `AnimatePresence` from Motion to handle exit animations.

### 11.13 Infinite Looping Decorative Animations

**The problem:** Animations that loop forever catch the eye continuously, drain battery, and trigger motion sensitivity.

**The fix:** Limit decorative animations to 3-5 iterations, then stop. If a continuous animation is essential (e.g., loading spinner), ensure it respects `prefers-reduced-motion` and stops when no longer needed.

---

## 12. Quick Reference Tables

### 12.1 Animation Duration Cheat Sheet

| Element | Duration | Easing | Notes |
|---|---|---|---|
| Button press | 80-100ms | `cubic-bezier(0.4, 0, 0.2, 1)` | Must feel instant |
| Tooltip appear | 100-150ms | `cubic-bezier(0.4, 0, 0.2, 1)` | Informational, don't distract |
| Micro-interaction | 150-200ms | `cubic-bezier(0.34, 1.56, 0.64, 1)` | Quick delight |
| Button hover | 200ms | `cubic-bezier(0.34, 1.56, 0.64, 1)` | Responsive feedback |
| Toggle switch | 200-250ms | `cubic-bezier(0.34, 1.56, 0.64, 1)` | Spring feel |
| Dropdown menu | 200-250ms | `cubic-bezier(0.16, 1, 0.3, 1)` | Smooth, no bounce |
| Modal entrance | 250-300ms | `cubic-bezier(0.16, 1, 0.3, 1)` | Gentle for large elements |
| Tab transition | 250-300ms | `cubic-bezier(0.2, 0, 0, 1)` | Standard motion |
| Page transition | 300-500ms | `cubic-bezier(0.16, 1, 0.3, 1)` | Major context change |
| Success celebration | 500-800ms | `cubic-bezier(0.34, 1.56, 0.64, 1)` | Worth the emphasis |
| Complex choreography | 600-1000ms | Varies | Total sequence, not individual |

### 12.2 Pre-Ship Animation Checklist

- [ ] Duration under 300ms (unless intentionally slow with justification)
- [ ] Only animating `transform` and/or `opacity`
- [ ] Custom cubic-bezier curve (not `linear` or default `ease`)
- [ ] Respects `prefers-reduced-motion`
- [ ] User can interrupt smoothly
- [ ] Animates from a contextually meaningful origin
- [ ] Adds genuine UX value (not decoration)
- [ ] Matches similar animations in the design system
- [ ] Runs at 60fps on target devices
- [ ] Tested in Chrome, Firefox, Safari, and mobile
- [ ] Has matching exit animation
- [ ] Does not block interaction during playback

### 12.3 Properties to Animate vs. Avoid

| Animate (Cheap) | Avoid (Expensive) |
|---|---|
| `transform: translateX/Y()` | `left`, `top`, `right`, `bottom` |
| `transform: scale()` | `width`, `height` |
| `transform: rotate()` | `margin`, `padding` |
| `opacity` | `border-width` |
| | `font-size` |
| | `box-shadow` (use pseudo-element opacity) |
| | `border-radius` (during animation) |
| | `filter: blur()` |
| | `clip-path` (complex paths) |

### 12.4 Easing Quick Reference

| Easing Name | CSS Value | Best For |
|---|---|---|
| Smooth ease-out | `cubic-bezier(0.16, 1, 0.3, 1)` | Modals, panels, large elements |
| Spring-like | `cubic-bezier(0.34, 1.56, 0.64, 1)` | Buttons, cards, micro-interactions |
| Fast response | `cubic-bezier(0.4, 0, 0.2, 1)` | Toggles, tooltips, checkboxes |
| M3 Standard | `cubic-bezier(0.2, 0, 0, 1)` | General purpose |
| M3 Emphasized decel | `cubic-bezier(0.05, 0.7, 0.1, 1)` | Important entrances |
| M3 Emphasized accel | `cubic-bezier(0.3, 0, 0.8, 0.15)` | Important exits |

### 12.5 The FLIP Technique

For animating layout properties without performance cost:

1. **First:** Record the element's current position/size with `getBoundingClientRect()`
2. **Last:** Make the layout change instantly (toggle a class, reorder DOM)
3. **Invert:** Calculate the difference and apply an inverse `transform` to make it LOOK like it's still in the old position
4. **Play:** Remove the transform with a transition/animation, and the element animates to its new position using only `transform` (cheap!)

```javascript
// Record First
const first = element.getBoundingClientRect();

// Apply the layout change (Last)
element.classList.toggle('expanded');
const last = element.getBoundingClientRect();

// Calculate Invert
const deltaX = first.left - last.left;
const deltaY = first.top - last.top;
const deltaW = first.width / last.width;
const deltaH = first.height / last.height;

// Apply inverse transform
element.style.transform = `translate(${deltaX}px, ${deltaY}px) scale(${deltaW}, ${deltaH})`;
element.style.transformOrigin = 'top left';

// Force a reflow to ensure the transform is applied
element.getBoundingClientRect();

// Play: animate to the new position
element.style.transition = 'transform 300ms cubic-bezier(0.2, 0, 0, 1)';
element.style.transform = '';
```

**Libraries that automate FLIP:**
- GSAP's Flip plugin
- Motion's `layout` prop
- The View Transitions API (built-in FLIP for view changes)

---

## Sources & References

### Standards & Documentation
- [MDN: CSS Scroll-Driven Animations](https://developer.mozilla.org/en-US/docs/Web/CSS/Guides/Scroll-driven_animations)
- [MDN: View Transition API](https://developer.mozilla.org/en-US/docs/Web/API/View_Transition_API)
- [MDN: prefers-reduced-motion](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/At-rules/@media/prefers-reduced-motion)
- [MDN: animation-timing-function](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/animation-timing-function)
- [W3C: Scroll-Driven Animations Module Level 1](https://drafts.csswg.org/scroll-animations-1/)
- [W3C: Animation from Interactions (WCAG 2.3.3)](https://www.w3.org/WAI/WCAG21/Understanding/animation-from-interactions.html)

### Design Systems
- [Material Design 3: Easing and Duration](https://m3.material.io/styles/motion/easing-and-duration/tokens-specs)
- [Material Design 3: Motion Overview](https://m3.material.io/styles/motion/overview/how-it-works)
- [Material Components Android: Motion Tokens](https://github.com/material-components/material-components-android/blob/master/docs/theming/Motion.md)
- [Carbon Design System: Motion](https://carbondesignsystem.com/elements/motion/overview/)
- [Fluent 2 Design System: Motion](https://fluent2.microsoft.design/motion)
- [Apple Human Interface Guidelines: Motion](https://developer.apple.com/design/human-interface-guidelines/motion)

### Technical Guides
- [Chrome Developers: View Transitions (Same-Document)](https://developer.chrome.com/docs/web-platform/view-transitions/same-document)
- [Chrome Developers: CSS linear() Easing Function](https://developer.chrome.com/docs/css-ui/css-linear-easing-function)
- [web.dev: How to Create High-Performance CSS Animations](https://web.dev/animations-guide/)
- [web.dev: Accessibility -- Motion](https://web.dev/learn/accessibility/motion)
- [Josh W. Comeau: Springs and Bounces in Native CSS](https://www.joshwcomeau.com/animation/linear-timing-function/)
- [Josh W. Comeau: A Friendly Introduction to Spring Physics](https://www.joshwcomeau.com/animation/a-friendly-introduction-to-spring-physics/)
- [Josh Collinsworth: Ten Tips for Better CSS Transitions](https://joshcollinsworth.com/blog/great-transitions)
- [Easings.net: Easing Functions Cheat Sheet](https://easings.net/)

### UX Research
- [NN/g: The Role of Animation and Motion in UX](https://www.nngroup.com/articles/animation-purpose-ux/)
- [NN/g: Skeleton Screens 101](https://www.nngroup.com/articles/skeleton-screens/)
- [IxDF: UI Animation -- Disney's 12 Principles Applied](https://ixdf.org/literature/article/ui-animation-how-to-apply-disney-s-12-principles-of-animation-to-ui-design)
- [A List Apart: Designing Safer Web Animation for Motion Sensitivity](https://alistapart.com/article/designing-safer-web-animation-for-motion-sensitivity/)

### Libraries & Tools
- [GSAP (GreenSock Animation Platform)](https://gsap.com/)
- [Motion (formerly Framer Motion)](https://motion.dev/)
- [Scroll-Driven Animations Demos](https://scroll-driven-animations.style/)
- [CSS-Tricks: Animating Layouts with the FLIP Technique](https://css-tricks.com/animating-layouts-with-the-flip-technique/)

### Community Resources
- [Web Animation Best Practices & Guidelines (GitHub Gist)](https://gist.github.com/uxderrick/07b81ca63932865ef1a7dc94fbe07838)
- [5 Steps for Including Motion Design in Your System](https://www.designsystems.com/5-steps-for-including-motion-design-in-your-system/)
- [Motion Design System -- A Practical Guide (Medium)](https://medium.com/@aviadtend/motion-design-system-practical-guide-8c15599262fe)
- [Advanced UI Animation Strategies (Medium)](https://medium.com/@vacmultimedia/advanced-ui-animation-strategies-when-to-use-css-lottie-rive-js-or-video-56289e8d2629)
