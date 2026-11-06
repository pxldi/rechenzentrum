/*
 * Builds a dark layer from Planka's own compiled stylesheet.
 *
 * Planka hard-codes its light palette in about a thousand rules: white panels,
 * #17394d text, #dfe3e6 lists, Semantic UI's rgba(34,36,38,.15) borders. This
 * reads the compiled CSS and re-emits every rule that sets one of those
 * neutral colours, with the same selector and the matching --pk-* token from
 * theme.css. Same selector, later sheet: the copy wins without extra
 * specificity. Saturated colours (labels, avatars, links, warnings) and
 * anything already dark stay as they are.
 *
 * It runs in the inject-theme init container on Planka's image (which ships
 * Node), so the layer is rebuilt from whatever version is running. theme.css
 * loads after it for the parts a colour rule cannot decide.
 *
 *   node remap.js <compiled.css> > generated.css
 *
 * No dependencies. Works as a CommonJS module too: remap(cssText) -> cssText.
 */

'use strict';

// --- Colour parsing ----------------------------------------------------------

const NAMED = { white: [255, 255, 255, 1], black: [0, 0, 0, 1] };
// Named colours only as whole values: "black" inside --g-color-private-black-850
// is part of a variable name.
const COLOR_RE = /#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)|(?<![\w-])(?:white|black)(?![\w-])/g;

function parse(token) {
  const t = token.toLowerCase();
  if (NAMED[t]) return NAMED[t];
  if (t[0] === '#') {
    let h = t.slice(1);
    if (h.length === 3 || h.length === 4) h = [...h].map((c) => c + c).join('');
    if (h.length !== 6 && h.length !== 8) return null;
    const n = (i) => parseInt(h.slice(i, i + 2), 16);
    return [n(0), n(2), n(4), h.length === 8 ? n(6) / 255 : 1];
  }
  const v = t.match(/[\d.]+%?/g);
  if (!v || v.length < 3) return null;
  const num = (s) => (s.endsWith('%') ? (parseFloat(s) / 100) * 255 : parseFloat(s));
  const a = v[3] === undefined ? 1 : v[3].endsWith('%') ? parseFloat(v[3]) / 100 : parseFloat(v[3]);
  return [num(v[0]), num(v[1]), num(v[2]), a];
}

const lum = ([r, g, b]) => (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
const sat = ([r, g, b]) => {
  const mx = Math.max(r, g, b);
  return mx === 0 ? 0 : (mx - Math.min(r, g, b)) / mx;
};

// --- What each kind of property becomes ----------------------------------------

function background(c) {
  const [, , , a] = c;
  const l = lum(c);
  if (a < 1) {
    // Translucent white frosting or a dark wash used for hover: on a dark
    // ground both become a faint light wash.
    if (a === 0) return null;
    if (sat(c) > 0.35) return null;
    return `rgba(255,255,255,${Math.min(a * (l > 0.5 ? 0.1 : 0.5), 0.1).toFixed(3)})`;
  }
  if (sat(c) > 0.25 && l < 0.9) return null;
  if (l >= 0.97) return 'var(--pk-surface)';
  if (l >= 0.9) return 'var(--pk-raised)';
  if (l >= 0.75) return 'var(--pk-hover)';
  if (l >= 0.5) return 'var(--pk-line-strong)';
  return null;
}

function text(c) {
  const l = lum(c);
  if (c[3] === 0) return null;
  if (l < 0.3) return 'var(--pk-ink)';
  if (l < 0.62 && sat(c) < 0.5) return 'var(--pk-ink-3)';
  return null;
}

function border(c) {
  const l = lum(c);
  if (c[3] === 0) return null;
  if (c[3] < 1 && l < 0.5 && sat(c) < 0.35) return 'var(--pk-line)';
  if (l >= 0.6 && sat(c) < 0.3) return 'var(--pk-line)';
  return null;
}

function replaceColors(value, fn) {
  let changed = false;
  const out = value.replace(COLOR_RE, (tok) => {
    const c = parse(tok);
    const r = c && fn(c);
    if (!r) return tok;
    changed = true;
    return r;
  });
  return changed ? out : null;
}

// Each comma-separated shadow: a shadow with no blur is a drawn border, so its
// colour follows border(); a real shadow keeps its dark colour.
function boxShadow(value) {
  let changed = false;
  const parts = value.split(/,(?![^(]*\))/).map((part) => {
    const lengths = part.replace(COLOR_RE, '').match(/-?[\d.]+(px|em|rem)?/g) || [];
    const blur = lengths[2] ? parseFloat(lengths[2]) : 0;
    if (blur > 0) return part;
    const r = replaceColors(part, border);
    if (r) changed = true;
    return r || part;
  });
  return changed ? parts.join(',') : null;
}

function kindOfCustomProperty(name) {
  if (/private|shadow|brand|positive|negative|danger|warning|info|success|utility/.test(name)) return null;
  if (/text|ink|foreground/.test(name)) return text;
  if (/line|border|divider|outline/.test(name)) return border;
  if (/background|base|bg|fill|surface/.test(name)) return background;
  return null;
}

function remapDeclaration(prop, value) {
  const p = prop.trim().toLowerCase();
  if (/url\(/.test(value)) return null;
  if (p.startsWith('--')) {
    const fn = kindOfCustomProperty(p);
    return fn ? replaceColors(value, fn) : null;
  }
  if (p === 'color' || p === 'fill' || p === '-webkit-text-fill-color' || p === 'caret-color') {
    return replaceColors(value, text);
  }
  if (p === 'background-color') return replaceColors(value, background);
  if (p === 'background') {
    if (/gradient/.test(value)) return null;
    return replaceColors(value, background);
  }
  if (/^(border|outline)(-(top|right|bottom|left))?(-color)?$/.test(p) || p === 'column-rule-color') {
    return replaceColors(value, border);
  }
  if (p === 'box-shadow') return boxShadow(value);
  return null;
}

// --- A small CSS walker: rules, nested at-rule blocks, strings, comments ------

function splitDeclarations(body) {
  const out = [];
  let depth = 0;
  let quote = null;
  let start = 0;
  for (let i = 0; i < body.length; i += 1) {
    const ch = body[i];
    if (quote) {
      if (ch === '\\') i += 1;
      else if (ch === quote) quote = null;
    } else if (ch === '"' || ch === "'") quote = ch;
    else if (ch === '(') depth += 1;
    else if (ch === ')') depth -= 1;
    else if (ch === ';' && depth === 0) {
      out.push(body.slice(start, i));
      start = i + 1;
    }
  }
  out.push(body.slice(start));
  return out.map((d) => d.trim()).filter(Boolean);
}

// Returns [blockText, indexAfterClosingBrace] for the block opening at `open`.
function readBlock(css, open) {
  let depth = 0;
  let quote = null;
  for (let i = open; i < css.length; i += 1) {
    const ch = css[i];
    if (quote) {
      if (ch === '\\') i += 1;
      else if (ch === quote) quote = null;
    } else if (ch === '"' || ch === "'") quote = ch;
    else if (ch === '{') depth += 1;
    else if (ch === '}') {
      depth -= 1;
      if (depth === 0) return [css.slice(open + 1, i), i + 1];
    }
  }
  return [css.slice(open + 1), css.length];
}

const NESTING_AT_RULES = /^@(media|supports|layer|container|document)\b/i;

function walk(css) {
  let out = '';
  let i = 0;
  while (i < css.length) {
    const open = css.indexOf('{', i);
    if (open === -1) break;
    const prelude = css.slice(i, open).trim();
    const [body, next] = readBlock(css, open);
    i = next;
    if (prelude.startsWith('@')) {
      if (NESTING_AT_RULES.test(prelude)) {
        const inner = walk(body);
        if (inner) out += `${prelude}{${inner}}\n`;
      }
      continue; // @font-face, @keyframes, @page: nothing to remap
    }
    if (body.includes('{')) {
      // Native nesting: not used by Planka's build; skipped.
      continue;
    }
    // Gravity UI (the markdown editor) ships a full dark theme that Planka
    // never switches on: it renders <body class="g-root g-root_theme_light">.
    // Copy the dark variables onto the light class, one step more specific.
    if (prelude === '.g-root_theme_dark') {
      out += `.g-root.g-root_theme_light{${body}}\n`;
      continue;
    }
    const decls = [];
    for (const d of splitDeclarations(body)) {
      const colon = d.indexOf(':');
      if (colon === -1) continue;
      const prop = d.slice(0, colon);
      let value = d.slice(colon + 1).trim();
      const important = /!\s*important$/i.test(value);
      if (important) value = value.replace(/!\s*important$/i, '').trim();
      const mapped = remapDeclaration(prop, value);
      if (mapped) decls.push(`${prop.trim()}:${mapped}${important ? '!important' : ''}`);
    }
    if (decls.length) out += `${prelude}{${decls.join(';')}}\n`;
  }
  return out;
}

function remap(css) {
  const clean = css.replace(/\/\*[\s\S]*?\*\//g, '');
  return `/* Generated by remap.js from Planka's compiled CSS. Do not edit. */\n:root{color-scheme:dark}\n${walk(clean)}`;
}

if (typeof module !== 'undefined') module.exports = remap;

if (typeof require !== 'undefined' && require.main === module) {
  const fs = require('fs');
  const files = process.argv.slice(2);
  if (!files.length) {
    process.stderr.write('usage: node remap.js <compiled.css>...\n');
    process.exit(2);
  }
  process.stdout.write(files.map((f) => remap(fs.readFileSync(f, 'utf8'))).join('\n'));
}
