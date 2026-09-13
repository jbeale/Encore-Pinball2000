# Revenge From Mars asset browser

Browse the game's graphics, movies, fonts and sounds in a web page.

    cd macos/asset-browser
    python3 extract.py            # ~1 minute; writes assets/ (git-ignored, ~200 MB)
    python3 -m http.server 8000   # then open http://localhost:8000/

`extract.py` needs the ROMs in `roms/` and the 1.60 update in `updates/`.
`--only REGEX` limits extraction to matching names, `--no-sounds` skips the audio.

## What the extractor understands
- Where things live: the game ROM (`pin2000_*_game.rom`, loaded at 0x100000) holds
  the symbol-named pointers (`anim_*_ptr`, `pict_*_ptr`, `movie_*_ptr`,
  `font_*_data_ptr`, `menu_background_*_ptr`); the data sits either in the PRISM
  flash banks (0x14000000 + bank<<24, chips u100..u107 word-interleaved in pairs)
  or, for the service-menu backgrounds, the system fonts and a few animations,
  in the update flash image `pin2000_*_im_flsh0.rom`, which the game maps at
  0x12008000 (behind the 32 KiB boot block of the BAR3 flash).
- `Animation` objects: 32-byte header {frames, fps, w, h, colours, palette ptr,
  palette size, frames ptr}; frames are 24-byte {format, w, h, x, y, data ptr}.
  The dispatch table in `decompress_image` maps format numbers to decoders:
  - 0: 8-bit raw indices into the Animation palette
  - 20: raw RGB555 words; 21: 16-bit line RLE (`decompress_15bit_image_l_rle`)
  - 22/23 (and row-delta 42/43, run-delta 44/45): byte-coded RLE against a 64- or
    32-colour RGB555 dictionary plus a table of pixel pairs; 0x7C1F is transparent.
  - 30: movie. A 4x4-block coder over an LSB-first bit stream, decoded like
    `decompress_movie_1x1`: per block a 2-bit opcode — 0 = four-colour block
    (r0 r1 g0 g1 b0 b1, 5 bits each, indices into [c0, (c0+2c1)/3, (2c0+c1)/3, c1]
    then 16 x 2-bit indices), 1 = keep the previous frame's block, 2 = solid
    15-bit colour, 3 = two-colour block (same colour header, 16 x 1-bit indices).
    Frames are written as PNG sprite sheets of up to 2048x2048 px.
- Fonts: `FontData` {glyphs, height, max width, colours, spacing, table}; each
  28-byte `Character` is {code, x offset, baseline, w, h, advance, pixels}. Pixels
  are one byte each: 0 transparent, otherwise an index into the colours the game
  sets at draw time (`Font::plot_character_ptr`). The sheet uses a fixed palette
  (1 white, 2 amber, 3 red, ...); the page renders arbitrary text from it.
- Sounds: `roms/rfm_sound.bin` (XOR 0x3A, Ogg Vorbis); names come from the game's
  `acd_*` audio descriptor symbols, matched by DCS track id.
- The upstream `sym_dump.py` is off by one: symbol entries are (address, name
  offset) pairs starting at file offset 0x18.
