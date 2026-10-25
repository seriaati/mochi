# Bento: the dashboard's design system

Read this before building or changing any UI. The look was chosen deliberately, out of five very different directions and four variations of the winner, so new pages, features and components must look like they were always part of it. When in doubt, copy an existing page.

Values live in `src/index.css` (tokens and shared classes). This file explains what they are for and the rules around them; it doesn't repeat hex values, so it can't drift from the CSS.

## The direction

Soft pastel tiles on a warm grey ground, arranged as a bento grid: colourful, calm and expressive, in the spirit of Material You. Light mode is the original Bento mockup; dark mode is **Bento Night**, the same layout with deep rust, moss and plum tints and the hero tile flipped to light.

Rejected on purpose. Don't drift back towards these:

- **Seed or dynamic colour theming** ("too much"). The fixed pastel palette is the design; don't add theming machinery.
- **Serif or editorial type** ("too editorial"). One sans family only.
- **All-white, monotone tiles** ("too monotone"). Colour carries meaning here; don't desaturate it away.
- Also out: gradients, glassmorphism, heavy shadows and borders on tiles, emoji, icon fonts.

## Tokens

All colours are CSS custom properties on `:root` in `src/index.css`, each written as `light-dark(<light>, <dark>)`. The theme follows the system unless the user picks one in Settings, which sets `data-theme` on `<html>` (see `src/theme.ts`).

- Use tokens, never raw colours, in page CSS.
- A new token needs **both** a light and a dark value, in the same `light-dark()` form, with a short comment saying what it's for.
- Reuse an existing token before adding one.

| Role | Tokens |
|---|---|
| Page ground, tiles, text | `--bg`, `--tile`, `--ink`, `--dim` (secondary text) |
| Hero tile (inverted) | `--hero`, `--on-hero`, `--hero-dim`, `--hero-inset`, `--hero-good*`, `--hero-warn`, `--hero-line` |
| Pastel tints | `--peach`, `--sage`, `--lavender`, `--blue`, `--yellow`, `--teal`, each with an `-ink` partner for text on it |
| On tinted tiles | `--muted` (secondary text), `--chip` (pills, insets), `--solid` (avatars, secondary buttons) |
| Status | `--good`, `--good-bg`, `--good-soft`; `--warn`, `--warn-bg` |
| Controls | `--field`, `--row`, `--pill`, `--track`, `--dash`, `--nav-bg`, `--nav-on`, `--backdrop` |
| Platforms | `--discord*`, `--line-*` |
| Shape and motion | `--radius-tile` (24px), `--radius-control` (12px), `--ease-out`, `--ease-spring` |

### What the colours mean

Keep these meanings consistent across pages:

- **Ink hero tile** (`.tile.ink`): the single most important thing on the page, e.g. the next payment to collect, or a project's price. At most one or two per page.
- **Peach**: needs attention: overdue money, things to act on. Also errors and destructive actions, through `--warn-bg` and `--warn`.
- **Sage**: money coming in and healthy states: earnings, collected payments, recurring income.
- **Lavender**: people and relationships: clients, a project's client, a client's maintenance.
- **Blue**: system and integration information, e.g. reminders and Discord setup.
- **Yellow, teal**: further variety, mostly per-record tints.
- **Per-record tints**: give a record such as a client a stable tint with `tintClass(id)` from `src/tint.ts`, so the same client always has the same colour.

## Typography

- **Plus Jakarta Sans** only, weights 400–700, loaded in `index.html`. Don't add fonts.
- Numbers are tabular everywhere (set on `body`).
- Scale:
  - page title: `.page-title`, 34px / 600, tight tracking
  - key figures: `.big-number`, 44px / 700, with units in `<small>`, e.g. `<small>NT$</small>12,000`
  - tile labels: `.tile-label`, 12.5px / 600, `--dim`
  - body: 14px
  - meta text: 12–13.5px

## Shape and space

- Tiles: `--radius-tile` (24px), 24px padding, flat, with no border and no shadow. Only floating things (dropdown menus, the nav pill) get a soft shadow.
- Controls and inputs: `--radius-control` (12px), 44px tall.
- Pills and chips: fully rounded.
- Rows inside tiles: about 14–16px radius on `--row`.
- Grid gap 16px. Leave generous breathing room rather than packing tiles.

## Layout

- Pages render inside `<main className="page">` in `App.tsx`.
- **List pages** start with `.page-head`: `.page-title` plus `.page-sub` on the left, `.page-actions` on the right. Then comes the content.
- **Detail pages** start with a `.back` link, e.g. "← Clients".
- Content sits in a `.bento` grid: 12 columns, with tiles taking `.span-3/4/5/6/7/8/12`. Rows should add up to 12.
- At ≤1000px every span goes full width; that's in `index.css`, don't fight it.
- **Must work at 390px** with no horizontal page scroll. Wrap toolbars, stack rows, and put anything wide in its own scroll box.

## Components and shared classes

Reuse these instead of writing new ones:

- **`Dialog`** (`src/components/Dialog.tsx`): every modal. Render it to open it; close it through its ref so it animates out. Forms inside use `.form`, `.field`, `.form-row` (side-by-side fields), `.form-error` and `.form-actions` (`.push` pushes a button to the far side).
- **`Select`** (`src/components/Select.tsx`): every dropdown. **Never use a native `<select>`** or any other control with native browser styling; style it in Bento.
- **`DatePicker`** (`src/components/DatePicker.tsx`): every date or month field (`month` for YYYY-MM). Never use a native `type="date"` or `type="month"` input.
- **`Avatar`** (`src/components/Avatar.tsx`): any person or client picture. The image comes first, then initials if the image is missing or fails to load.
- **Buttons:** `.btn` (primary, ink), `.btn.secondary`, `.btn.danger`, `.link-btn` (text-only, e.g. "See all"). A `.btn` on a hero tile inverts automatically.
- **Status and progress:**
  - `.chip`, `.chip.good`, `.chip.warn`
  - `.track` with `<i style="width: N%">` for progress; `.track.open` (dashed) for "no end date"
- **Also shared:** `.segmented` (filters, buttons with `aria-pressed`), `.search`, `.tile-head` (label plus a link on one line), `.empty-note`.
- **Destructive actions** confirm in two steps on the same button, e.g. "Delete" becomes "Confirm delete". Don't use `window.confirm`.

## Content

- **Money:** `formatNTD()` displays it as `NT$12,000`.
- **Dates:** use `formatDay()`, `formatMonth()`, `timeAgo()` and the other helpers in `src/format.ts`. Don't hand-format.
- **Empty states:** friendly and useful, saying what will appear there and linking to the next action ("Add your first client"). Never leave a blank tile, `NaN%` or a broken chart.
- **Copy:** short and plain. Labels are in sentence case.

## Icons

Inline SVG only:
- stroked, `stroke="currentColor"`, width about 1.8–2, round caps and joins
- `aria-hidden="true"`; an icon-only button gets an `aria-label`
- no icon libraries, icon fonts or emoji

## Motion

Subtle and quick, built from what's in `index.css`:
- **Page and tiles:** pages fade in (`page-in`), and tiles rise in (`rise-in`), staggered by position inside `.bento`.
- **Controls:** dialogs spring in and out, dropdowns fade and slide (`@starting-style`), the nav pill springs between links, and buttons press to 0.97.
- **Easing:** use `--ease-out` for entrances and `--ease-spring` for playful ones.
- **Timing:** keep durations short, 0.15–0.5s.
- **Reduced motion:** the global `prefers-reduced-motion` rule turns everything off. Don't bypass it.

## CSS organisation

- Tokens and anything used by two or more pages go in `src/index.css`.
- Page-specific styles go in a CSS file next to the page, imported by it, with a class prefix for that page, e.g. `ov-` (Overview), `mt-` (Maintenance), `client-`, `project-`, `settings-`.
- No CSS frameworks or UI libraries.

## Accessibility

- Use real `<button>`, `<a>`, `<label>` and `<input>` elements, never clickable `<div>`s.
- Keep the global `:focus-visible` outline.
- Text contrast must be at least 4.5:1 in **both** themes. Check dark mode, not just light.

## Checklist for new UI

1. It's built from the tokens, shared classes and components above, with nothing new where something existing fits.
2. Tile colours follow the meanings above.
3. It looks right in light, in dark, and at 390px wide.
4. Empty and loading states are handled.
5. There are no native-styled controls, emoji, new fonts or raw colours.

The original static mockups (Overview, Projects, Clients, Maintenance and the dark theme) are on the design canvas: https://claude.ai/artifact/1xbwAPqoHHcxMj3bpYKgLP
