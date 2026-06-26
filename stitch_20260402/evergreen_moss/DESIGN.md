# Mobile Design System: The Digital Arboretums

## 1. Overview & Creative North Star
### Creative North Star: "The Curated Grove"
The design system transcends the standard utility of a management tool to become a "digital conservatory." Our goal is to move beyond the rigid, boxy nature of traditional Material Design 3 and embrace a high-end editorial aesthetic that mirrors the patience and artistry of bonsai cultivation.

**Breaking the Template:**
We achieve a signature feel through **Intentional Asymmetry** and **Tonal Depth**. By avoiding heavy structural lines and instead using overlapping surfaces and varying "paper weights" (surface tiers), the UI feels organic and alive. High-contrast typography scales ensure that even in high-glare outdoor environments, the botanical data remains the protagonist of the screen.

---

## 2. Colors & Signature Textures
Our palette is rooted in the "Chlorophyll Spectrum"—a range of greens that feel biological rather than synthetic.

### The "No-Line" Rule
**Explicit Instruction:** Prohibition of 1px solid borders for sectioning. 
Boundaries must be defined solely through background color shifts. For example, a `surface-container-low` section sitting on a `surface` background provides all the separation required. 

### Surface Hierarchy & Nesting
Treat the UI as a series of physical layers—like stacked sheets of fine washi paper. 
- **Base:** `surface` (#f6faf6)
- **Secondary Sections:** `surface-container-low` (#f1f5f1)
- **Primary Content Cards:** `surface-container-lowest` (#ffffff) to create a soft "pop."
- **Floating Overlays:** Use `surface-bright` with a 10% opacity decrease for a glass-like feel.

### The "Glass & Gradient" Rule
To elevate the app from a simple database to a premium experience:
- **Glassmorphism:** Use for FABs and Bottom Navigation. Apply `surface` at 80% opacity with a `20px` backdrop-blur.
- **Botanical Gradients:** Use a subtle linear gradient for Hero Cards or Primary CTAs: `primary` (#0d631b) to `primary-container` (#2e7d32) at a 135-degree angle. This adds "soul" and prevents the interface from feeling flat.

---

## 3. Typography
We utilize a sophisticated editorial scale. By pairing the utilitarian `Inter/Roboto` with generous white space, we create an authoritative yet breathable layout.

| Level | Token | Font | Size | Weight | Usage |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Display** | `display-lg` | Inter | 3.5rem | 700 | Hero metrics (e.g., Age of Bonsai) |
| **Headline** | `headline-md` | Inter | 1.75rem | 600 | Page titles, Section headers |
| **Title** | `title-md` | Inter | 1.125rem | 500 | Card titles, Item names |
| **Body** | `body-md` | Noto Sans JP | 0.875rem | 400 | General logs, Care instructions |
| **Label** | `label-md` | Inter | 0.75rem | 600 | Metadata, Status tags (All Caps) |

**Editorial Contrast:** Use `display-lg` for numeric data (e.g., "12 Years") paired immediately with a `label-md` for description. This high-low pairing is the hallmark of premium digital magazines.

---

## 4. Elevation & Depth
Depth is achieved through **Tonal Layering** rather than shadows.

*   **Layering Principle:** Place a `surface-container-lowest` card (#ffffff) on top of a `surface-container-low` (#f1f5f1) background. This creates a natural "lift" that mimics the way light hits layered leaves.
*   **Ambient Shadows:** For floating elements (FABs), use a 12% opacity shadow using the `on-surface` color (#181d1a) with a `16px` blur. Never use pure black shadows.
*   **The Ghost Border Fallback:** If a border is required for accessibility, use `outline-variant` (#bfcaba) at **15% opacity**. 100% opaque borders are strictly forbidden.

---

## 5. Components

### 5.1 Buttons & Chips
*   **Primary Button:** Full round shape. Background: Gradient from `primary` to `primary_container`. Text: `on-primary` (#ffffff).
*   **Filter Chips:** `surface-container-high` (#e5e9e5) with `on-surface-variant` text. When selected, transition to `primary` with a subtle `2px` "glow" (ambient shadow).
*   **Forbid Dividers:** In lists, use `8px` of vertical whitespace or a subtle shift from `surface` to `surface-container-low` instead of a horizontal line.

### 5.2 Bonsai Information Cards
*   **Shape:** `12px` rounded corners.
*   **Layout:** Asymmetric. Image takes up 40% width (left), text 60% (right). 
*   **Status Indicators:** Use the defined state colors as a vertical "accent bar" (4px wide) on the left edge of the card rather than a full background color to maintain elegance.

### 5.3 Bottom Navigation & FAB
*   **Navigation:** Use the Glassmorphism rule. Active state indicated by a `primary_fixed` (#a3f69c) pill shape behind the icon.
*   **FAB:** Located bottom-right, oversized. Use the signature botanical gradient. This is the "Seed" of the interface; it should feel tactile and important.

### 5.4 Specialized Components: The "Growth Log"
*   **Timeline Element:** Use a vertical "stem" (2px width, `primary-fixed-dim`) to connect log entries, replacing traditional list dividers.
*   **Condition Badges:** 
    *   *Healthy:* `background: #E8F5E9` | `text: #2E7D32` | ✓ Icon
    *   *Warning:* `background: #FCE4EC` | `text: #BA1A1A` | ⚠ Icon
    *   *Critical:* `background: #FFEBEE` | `text: #BA1A1A` | ✕ Icon

---

## 6. Do's and Don'ts

### Do
*   **Do** use extreme vertical whitespace (e.g., `spacing-12` or `spacing-16`) between major sections to emphasize a sense of calm and "Zen."
*   **Do** ensure high contrast for outdoor use; the `on-surface` (#1b1c1b) text on `surface` (#f7fbf7) provides maximum legibility in sunlight.
*   **Do** use "Surface Nesting" to define content importance.

### Don't
*   **Don't** use 1px solid divider lines. It clutters the "Grove" and feels like a legacy template.
*   **Don't** use standard Material 3 elevation shadows (Elevation 4 or 5). Keep it grounded with Tonal Layering.
*   **Don't** use high-saturation reds for anything other than 'Critical' errors; the app should feel like a sanctuary, not a dashboard of alerts.