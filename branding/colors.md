# Rechenzentrum brand

The look is Schall's, the design system in `pxldi-labs/cantus`. The two products
share a house, so they share a palette; this file is what rechenzentrum uses of
it and how, and `terraform/authentik/brand.css` is the implementation.

## The rules that decide everything else

- **Depth is tonal.** Ground, surface, inset, and a hairline between them. There
  is no box-shadow anywhere. A thing that needs to feel closer gets a lighter
  step of the same ladder.
- **A field is a well.** Anything you put something into is drawn one step
  *below* the page, never raised above it.
- **One accent.** Lilac is chrome, never meaning: the primary button on a
  screen, the focus ring, the working part of the mark. A status colour is not
  the accent and never borrows it.
- **No gradient.** Not in a button, not in a card, not in text.
- **Warm greys.** They lean plum rather than blue, so a page reads as a lit room
  rather than a terminal.

## Palette

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

## Type

Two faces, one job each, both self-hosted from `branding.pxldi.de/fonts/`.

- **Schibsted Grotesk** carries everything that is read, headings included.
  Hierarchy is weight and size, never a change of face.
- **Azeret Mono** carries every identifier, path, figure and input value. A
  username is an identifier, so a login field is set in it.
- **Syne 800** draws the wordmark and nothing else, the same rule it carries in
  Schall. It ships as outlines inside `wordmark.svg`, so there is no third font
  file to serve.

Micro-labels are the grotesque at `0.6875rem`, weight 600, uppercase, tracked
`0.1em`. Body sits at `0.8125rem`–`0.9375rem`. A card title is `1.1875rem` at
weight 600, tracked `-0.01em`.

## Radii and motion

`0.5rem` for a control, `0.75rem` for a card. Motion is `150ms` for a thing
changing in place and `280ms` for a thing arriving, on
`cubic-bezier(0.2, 0, 0, 1)`.

## Assets

| File | Used by |
|---|---|
| `icons/wordmark.svg` | The logo. Both halves of the compound justified to one width, in Syne 800 converted to outlines |
| `icons/wordmark-ink.svg` | The same outlines for a light ground, in `#221a26` and `#4c4152` |
| `icons/house.svg` | The symbol, for anywhere a word will not fit. The house quiet, the rack in accent |
| `icons/house-mark.svg` | Favicon. One solid block, heavier outline, legible at 16px |
| `wallpapers/login-bg.avif` | The dark room: login flow and homepage |
| `wallpapers/login-bg-light.webp` | The same room in light |
| `wallpapers/build-login-bg.sh` | The recipe that generates both |
| `fonts/*.woff2` | Both faces, served with a permissive CORS header |

The wallpaper is a dark room with light entering at one edge, which is what
Schall's "Die Blende" means one room over. It stays dark enough that a `#241a27`
card separates from it without a shadow. The light room is the same render with
the polarity turned over: the beam takes light away rather than adding it, and
the vignette greys the corners rather than darkening them.

Neither file is drawn on its own. A lossy codec reads a gradient this shallow
as flat plates, which is banding, so a tiled noise layer is composited over the
wallpaper in CSS at 4% in the dark room and 6% in the light one. That layer
cannot darken a near-black ground, so both renders are pre-compensated for it
and their ground colours in `build-login-bg.sh` sit below the palette's. The
opacities and the renders move together.

The two rooms are in different formats on purpose. Measured under the noise
layer, the dark room is flatter as AVIF (a 90th-percentile band of 6px against
7px for WebP, at the same size) and the light room is flatter as WebP (5px
against 7px), because AV1 spends its bits differently on a near-white gradient.

## Where it is drawn

| Surface | File |
|---|---|
| Login flow, user portal, admin interface | `terraform/authentik/brand.css` |
| Homepage | `kubernetes/apps/gethomepage/configmap.yaml`, under `custom.css` |

Both carry the same ten steps. authentik's are PatternFly variable names, the
homepage's are ten RGB triples on the html element, and each has a light mode
that swaps the palette without moving anything.
