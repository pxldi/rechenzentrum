#!/usr/bin/env bash
# Rebuilds login-bg.avif and login-bg-light.webp. The wallpaper is generated
# rather than drawn, so the recipe is the source: keep it here and re-run rather
# than editing the binaries. Needs ImageMagick, python3 and avifenc (libavif).
#
# "Die Blende" is Schall's north star, and this is the same idea one room over:
# a dark room with light entering at one edge and the rest of it left alone.
# One beam from the left, one soft rim along its leading edge, one pool where it
# lands, then a vignette. Everything stays dark enough that a #241a27 card sits
# on it with tonal separation and no shadow.
#
# Two numbers decide whether it looks generated or cheap, and the first cut got
# both wrong. It rendered at 2560 wide, which a hidpi screen upscales, and it
# carried four times this much noise; WebP cannot code per-pixel noise, so it
# approximated it in blocks and the result read as a low-resolution photograph.
# At 3840 with an eighth of a stop of grain the file is 40KB rather than 214KB.
#
# The grain below does not reach the screen, and that is the point of the noise
# tile in brand.css. WebP coded this gradient as flat plates: in the file this
# replaces, 79% of the tonal steps landed exactly on the 8-pixel block grid, and
# a vertical scan read a median band of 4px, a 90th percentile of 14px and one
# plate 67px tall. That was the banding. Raising quality does not fix it -- a
# clean render at q84 comes out worse, with plates up to 1016px -- because the
# encoder spends its bits on the noise and then quantises it away. So the
# dither that survives is applied at display time as a CSS noise layer. This
# much grain still stays here: it gives the encoder something to break its
# plates against, and the two dithers together beat either alone.
#
# The two rooms then take different encoders, which is the one asymmetry in this
# file. Measured under the noise layer across three renders each, the dark room
# reads a 90th-percentile band of 6px as AVIF q75 against 7px as WebP, on 34KB
# against 35KB, and its longest plate falls from 29-44px to 26-31px. The light
# room goes the other way: 5px as WebP against 7px as AVIF at any quality, since
# AV1 spends its bits differently on a near-white gradient. So dark is AVIF and
# light is WebP, and the numbers rather than tidiness are why. nginx 1.27 serves
# image/avif from its stock mime.types, so branding needs no change for it. The
# grain is drawn fresh on every run, so the longest plate moves about 15px from
# rebuild to rebuild; the percentile is the one to compare.
#
# Both renders are pre-compensated for that CSS layer. The noise tile composites
# over the wallpaper, and over-compositing cannot darken a near-black ground, so
# it lifts the dark room about 4 levels and, being centred on mid-grey, drops
# the light room about 6. The ground and vignette below are pulled the other way
# by the same amount, which is why they no longer read as the palette's #0b090d
# and #efe8f3. Change the opacity in brand.css and these have to move with it.
set -euo pipefail
cd "$(dirname "$0")"

W=3840
H=2160
S=1.5   # the geometry below was drawn against a 2560-wide frame

px() { python3 -c "print(round($1 * $S))"; }

# One recipe, two rooms. The light one is the same geometry with the polarity
# turned over: the layers are drawn on white and multiplied rather than drawn on
# black and screened, so the beam that adds light to the dark room takes it away
# from the bright one, and the vignette that darkens the corners of the first
# greys the corners of the second. Nothing moves.
render() {
  local out=$1 ground=$2 canvas=$3 op=$4 beam=$5 rim=$6 pool=$7 clear=$8 vignette=$9

  magick -size ${W}x${H} xc:"$ground" \
    \( -size ${W}x${H} xc:"$canvas" -fill "$beam" \
       -draw "polygon 0,$(px 120) 0,$(px 760) $(px 1900),${H} $(px 700),${H}" \
       -blur 0x$(px 110) \) -compose "$op" -composite \
    \( -size ${W}x${H} xc:"$canvas" -fill "$rim" \
       -draw "polygon 0,$(px 150) 0,$(px 240) $(px 1900),${H} $(px 1640),${H}" \
       -blur 0x$(px 45) \) -compose "$op" -composite \
    \( -size ${W}x${H} -define gradient:center=$(px 520),$(px 430) \
       -define gradient:radii=$(px 760),$(px 620) \
       radial-gradient:"$pool-$clear" \) -compose "$op" -composite \
    \( -size ${W}x${H} -define gradient:center=$(px 1280),$(px 720) \
       -define gradient:radii=$(px 2000),$(px 1500) \
       radial-gradient:"$clear-$vignette" \) -compose over -composite \
    -attenuate 0.12 +noise Gaussian \
    "$out"
}

report() { printf 'wrote %s (%s)\n' "$1" "$(du -h "$1" | cut -f1)"; }

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

render "$tmp/dark.png" '#040308' black screen \
  'rgba(150,116,170,0.30)' 'rgba(191,163,232,0.16)' 'rgba(191,163,232,0.13)' \
  'rgba(0,0,0,0)' 'rgba(2,1,3,0.95)'

# 4:4:4 and 10-bit cost nothing at this bitrate and keep the plum out of the
# chroma subsampler. ImageMagick's own AVIF writer needs four times the bytes
# for the same result, so this shells out to avifenc.
avifenc -q 75 -s 4 --yuv 444 --depth 10 "$tmp/dark.png" login-bg.avif >/dev/null
report login-bg.avif

render "$tmp/light.png" '#f2ebf6' white multiply \
  'rgba(109,74,168,0.24)' 'rgba(87,49,143,0.14)' 'rgba(109,74,168,0.10)' \
  'rgba(255,255,255,0)' 'rgba(174,157,186,0.55)'

magick "$tmp/light.png" -quality 84 login-bg-light.webp
report login-bg-light.webp
