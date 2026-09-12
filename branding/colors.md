# Branding

Implemented in `terraform/authentik/brand.css` and Homepage's `custom.css`.
Use tonal depth, inset fields, warm greys, lilac accents and separate status colours.
Avoid gradients and shadows on UI controls.

| Name | Hex | Where it goes |
|---|---|---|
| Inset | `#08060a` | Fields, wells, scrollbar track |
| Ground | `#0e0b10` | The page |
| Surface | `#241a27` | Cards and panels |
| Surface thick | `#2d212f` | A panel that sits on another, a disabled fill |
| Line | `#3d2f42` | Hairlines |
| Line strong | `#4a3a50` | A hairline that has to be seen |
| Accent | `#bfa3e8` | Primary button, focus ring, the rack in the mark |
| Accent soft | `#d9c8f0` | The accent on hover |
| Accent ink | `#2a1c3d` | Text on an accent fill |
| Ink | `#ece5ea` | Body text |
| Ink 2 | `#bcb2b8` | Secondary text, the outline of the mark |
| Ink 3 | `#aaa0aa` | Labels, meta |
| Ok | `#7fb387` | Something completed or verified |
| Fail | `#cd5f4c` (border `#5c3733`) | Something failed or was refused |


Fonts: Schibsted Grotesk for text; Azeret Mono for identifiers and input values.
The Syne wordmark is stored as SVG outlines. WOFF2 files live in `fonts/`.

Control/card radii: 0.5rem/0.75rem. Motion: 150ms in place, 280ms on entry,
using `cubic-bezier(0.2, 0, 0, 1)`.

Icons and wordmarks live in `icons/`. `wallpapers/build-login-bg.sh` generates
the dark AVIF and light WebP backgrounds. Keep their CSS noise overlays and
rendered backgrounds in sync.
