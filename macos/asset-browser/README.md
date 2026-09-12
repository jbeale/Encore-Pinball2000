# Revenge From Mars asset browser

Browse the game's graphics (all 424 named animations, decoded from the PRISM flash
banks) and sounds (866 DCS samples) in a web page.

    cd macos/asset-browser
    python3 extract.py            # ~ a few minutes; writes assets/ (git-ignored, ~hundreds of MB)
    python3 -m http.server 8000   # then open http://localhost:8000/

`extract.py` needs the ROMs in `roms/` and the 1.60 update in `updates/`.

## What the extractor understands
- `Animation` objects: 32-byte header {frames, fps, w, h, colours, palette ptr,
  palette size, frames ptr}; frames are 24-byte {format, w, h, x, y, data ptr}.
  Pointers are addresses in the PLX BAR5 windows (0x14000000 + bank<<24 + offset).
- Formats 22/23 (and row-delta variants 42-45): byte-coded RLE against a 64- or
  32-colour RGB555 dictionary plus a table of pixel pairs; 0x7C1F is transparent.
  Reverse-engineered from the game's `decompress_*_dict_rle/run_delta` code.
- Not decoded yet: the 14 "movies" (format 30, bit-packed) and a few 8-bit frames.
- Sounds: `roms/rfm_sound.bin` (XOR 0x3A, Ogg Vorbis); names come from the game's
  `acd_*` audio descriptor symbols, matched by DCS track id.
