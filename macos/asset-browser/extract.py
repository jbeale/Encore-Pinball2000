#!/usr/bin/env python3
"""
Extract Revenge From Mars (Pinball 2000) graphics and sounds into a folder the
asset browser (index.html) can load.

  python3 extract.py [--out DIR] [--roms ROMS_DIR] [--update UPDATE_DIR]

Graphics: the game's 424 named Animation objects live in the PRISM flash banks
(u100..u107, two 16-bit chips per 32-bit bank).  Each Animation has a frame rate,
size, a colour dictionary and N frames; frames are byte-coded RLE against a 32- or
64-colour dictionary plus a table of pixel pairs (formats 22/23 and the row-delta
variants 42-45), decoded exactly like the game's decompress_*_dict_rle/run_delta
functions.  Frames are written as one sprite sheet PNG per animation.

Also extracted: the 54 pict_* stills, the service-menu backgrounds and the
system fonts that live in the update flash (pin2000_*_im_flsh0.rom, mapped at
0x12008000), the 20 movie_* full-screen movies (format 30: a 4x4-block coder
with skip / solid / 2-colour / 4-colour blocks, decoded like the game's
decompress_movie_1x1) and the 11 fonts (FontData + 28-byte Character records
with 8-bit colour-index glyphs, as drawn by Font::plot_character_ptr).

Sounds: roms/rfm_sound.bin is Encore's XOR-0x3A container of 866 Ogg Vorbis
samples named by DCS track id; the game's acd_* audio descriptors give them
readable names.
"""
import argparse, json, os, re, struct, sys, time, zlib
from array import array

TRANSPARENT = 0x7c1f
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))

# ---------------------------------------------------------------- ROM access
class Banks:
    IM_BASE = 0x12008000   # *_im_flsh0.rom sits behind the 32 KiB boot block of the BAR3 update flash
    def __init__(self, roms, im_flash=None):
        self.im = open(im_flash, 'rb').read() if im_flash else b''
        pairs = [('rfm_u100.rom','rfm_u101.rom'),('rfm_u102.rom','rfm_u103.rom'),
                 ('rfm_u104.rom','rfm_u105.rom'),('rfm_u106.rom','rfm_u107.rom')]
        self.b = []
        for lo, hi in pairs:
            a = open(os.path.join(roms, lo), 'rb').read(); c = open(os.path.join(roms, hi), 'rb').read()
            out = bytearray(len(a) * 2)
            out[0::4] = a[0::2]; out[1::4] = a[1::2]; out[2::4] = c[0::2]; out[3::4] = c[1::2]
            self.b.append(bytes(out))
    def rd(self, addr, n):
        if 0x14000000 <= addr < 0x18000000:
            b = (addr - 0x14000000) >> 24; o = addr & 0xffffff
            return self.b[b][o:o + n]
        if self.IM_BASE <= addr < self.IM_BASE + len(self.im):
            o = addr - self.IM_BASE
            return self.im[o:o + n]
        raise ValueError("address %x not in flash windows" % addr)

def load_symbols(path):
    d = open(path, 'rb').read()
    n = struct.unpack_from('<I', d, 16)[0]
    ents = [struct.unpack_from('<II', d, 0x18 + i * 8) for i in range(n)]  # (addr, name_off)
    end = 0x18 + n * 8
    best = None
    for sb in range(end - 16, end + 64):
        good = 0
        for addr, off in ents[:400]:
            p = sb + off
            if p <= 0 or p >= len(d): break
            s = d[p:d.find(b'\0', p)]
            if s and d[p-1] == 0 and all(32 <= c < 127 for c in s): good += 1
        if best is None or good > best[0]: best = (good, sb)
    sb = best[1]
    out = {}
    for addr, off in ents:
        p = sb + off; out[addr] = d[p:d.find(b'\0', p)].decode('latin1')
    return out

# ---------------------------------------------------------------- animations
def parse_anim(banks, ptr):
    nf, rate, w, h, pc, pp, palsize, fp = struct.unpack('<8I', banks.rd(ptr, 32))
    frames = []
    for i in range(nf):
        fmt, fw, fh, x, y, dp = struct.unpack('<6I', banks.rd(fp + i * 24, 24))
        frames.append((fmt, fw, fh, x, y, dp))
    return dict(nframes=nf, rate=rate, w=w, h=h, pal_count=pc, pal_ptr=pp, palsize=palsize, frames_ptr=fp, frames=frames)

DICT_FORMATS = {22: 6, 23: 5, 42: 6, 43: 5, 44: 6, 45: 5}   # format -> colour index bits
LRLE_FORMATS = {21}                                          # 16-bit line RLE (decompress_*_l_rle)
RAW_FORMATS = {20}                                           # 16-bit raw (decompress_15bit_image_raw)
RAW8_FORMATS = {0}                                           # 8-bit raw indices into the Animation palette
MOVIE_FORMAT = 30                                            # decompress_movie_1x1

def decode_lrle15(data, w, h):
    """Format 21: per row, words of {count|0x8000?}: high bit clear = run of the next
    colour word for `count` pixels (0x7C1F = transparent skip); high bit set = `count`
    literal colour words."""
    out = array('H', [TRANSPARENT]) * (w * h)
    p = 0; n = len(data)
    for y in range(h):
        x = 0; base = y * w
        while x < w - 1:
            if p + 2 > n: return out, 'short'
            d = data[p] | (data[p + 1] << 8); p += 2
            cnt = d & 0x7fff
            if d <= 0x7fff:
                if p + 2 > n: return out, 'short'
                c = data[p] | (data[p + 1] << 8); p += 2
                if c != TRANSPARENT:
                    e = min(base + x + cnt, base + w)
                    for k in range(base + x, e): out[k] = c
                x += cnt
            else:
                for k in range(cnt):
                    if p + 2 > n: return out, 'short'
                    c = data[p] | (data[p + 1] << 8); p += 2
                    if c != TRANSPARENT and x + k < w: out[base + x + k] = c
                x += cnt
    return out, None

def decode_dict_rle(data, w, h, pal, pairs, fmt, bits):
    out = array('H', [TRANSPARENT]) * (w * h)
    op_off = data[0] | (data[1] << 8)
    flags = data[2:op_off]
    ops = data[op_off:]
    oi = 0; fi = 0
    rowskip = None
    if fmt in (42, 43, 44, 45):
        nwords = (h + 31) >> 5
        rowskip = struct.unpack_from('<%dI' % nwords, ops, 0); oi = nwords * 4
    skip2 = fmt in (44, 45)
    nops = len(ops)
    if bits == 5:
        cmask, pmask = 0x1f, 0x7f
    else:
        cmask, pmask = 0x3f, 0x3f
    pal_arr = pal
    for y in range(h):
        if rowskip is not None and (rowskip[y >> 5] >> (y & 31)) & 1:
            continue
        x = 0; base = y * w; rowend = base + w
        while x < w:
            if oi >= nops: return out, 'short'
            op = ops[oi]; oi += 1
            if bits == 5:
                if op < 0x80:
                    kind = op & 0xe0; idx = op & 0x1f
                    if kind == 0x00:
                        out[base + x] = pal_arr[idx]; x += 1
                    elif kind == 0x20:
                        if skip2: x += idx + 2
                        else:
                            v = pal_arr[idx]; out[base + x] = v
                            if x + 1 < w: out[base + x + 1] = v
                            x += 2
                    elif kind == 0x40:
                        n = idx + 3; v = pal_arr[0]
                        if v != TRANSPARENT:
                            e = min(base + x + n, rowend)
                            for k in range(base + x, e): out[k] = v
                        x += n
                    else:
                        n = ops[oi] + 3; oi += 1; v = pal_arr[idx]
                        e = min(base + x + n, rowend)
                        for k in range(base + x, e): out[k] = v
                        x += n
                    continue
            else:
                kind = op & 0xc0; idx = op & 0x3f
                if kind == 0x00:
                    out[base + x] = pal_arr[idx]; x += 1; continue
                elif kind == 0x40:
                    if skip2: x += idx + 2
                    else:
                        v = pal_arr[idx]; out[base + x] = v
                        if x + 1 < w: out[base + x + 1] = v
                        x += 2
                    continue
                elif kind == 0xc0:
                    n = ops[oi] + 3; oi += 1; v = pal_arr[idx]
                    e = min(base + x + n, rowend)
                    for k in range(base + x, e): out[k] = v
                    x += n
                    continue
            # pair
            pr = pairs[op & pmask]
            lo, hi = pr & 0xffff, pr >> 16
            bit = (flags[fi >> 3] >> (fi & 7)) & 1 if (fi >> 3) < len(flags) else 0
            fi += 1
            a, b = (hi, lo) if bit else (lo, hi)
            out[base + x] = a
            if x + 1 < w: out[base + x + 1] = b
            x += 2
    return out, None

def decode_frame(banks, anim, i, cache):
    fmt, w, h, x, y, dp = anim['frames'][i]
    if fmt in LRLE_FORMATS:
        return decode_lrle15(banks.rd(dp, 1 << 21), w, h)
    if fmt in RAW_FORMATS:
        raw = banks.rd(dp, w * h * 2)
        return array('H', raw[:w * h * 2]), ('short' if len(raw) < w * h * 2 else None)
    if fmt in RAW8_FORMATS:
        pal = struct.unpack('<%dH' % anim['pal_count'], banks.rd(anim['pal_ptr'], anim['pal_count'] * 2))
        raw = banks.rd(dp, w * h)
        return array('H', [pal[b] if b < len(pal) else TRANSPARENT for b in raw]), ('short' if len(raw) < w * h else None)
    bits = DICT_FORMATS.get(fmt)
    if bits is None: raise NotImplementedError("format %d" % fmt)
    key = (anim['pal_ptr'], bits)
    if key not in cache:
        ndict, npairs = (32, 128) if bits == 5 else (64, 64)
        raw = banks.rd(anim['pal_ptr'], ndict * 2 + npairs * 4)
        cache[key] = (list(struct.unpack('<%dH' % ndict, raw[:ndict * 2])), list(struct.unpack('<%dI' % npairs, raw[ndict * 2:])))
    pal, pairs = cache[key]
    data = banks.rd(dp, 1 << 21)
    return decode_dict_rle(data, w, h, pal, pairs, fmt, bits)


# ---------------------------------------------------------------- movies (format 30)
def _interp3(a, b): return (a + 2 * b) // 3

def decode_movie_frame(data, w, h, canvas):
    """One format-30 frame, applied to `canvas` (array of RGB555, w*h) in place.
    LSB-first bitstream over 4x4 blocks in raster order; per block a 2-bit opcode:
      0: 4-colour block: r0 r1 g0 g1 b0 b1 (5 bits each) then 16 x 2-bit indices into
         [c0, (c0+2c1)/3, (2c0+c1)/3, c1] (per channel, like the game's *_interpolate tables)
      1: keep the previous frame's pixels
      2: solid block: one 15-bit colour
      3: 2-colour block: r0 r1 g0 g1 b0 b1 then 16 x 1-bit indices into [c0, c1]
    Returns the number of bytes consumed."""
    buf = data[0] | data[1] << 8 | data[2] << 16 | data[3] << 24; nb = 32; p = 4
    for by in range(0, h, 4):
        rows = [(by + k) * w for k in range(4)]
        for bx in range(0, w, 4):
            if nb <= 24:
                while nb <= 24: buf |= data[p] << nb; p += 1; nb += 8
            op = buf & 3; buf >>= 2; nb -= 2
            if op == 1: continue
            if op == 2:
                while nb <= 24: buf |= data[p] << nb; p += 1; nb += 8
                c = buf & 0x7fff; buf >>= 15; nb -= 15
                for r in rows: canvas[r + bx:r + bx + 4] = array('H', (c, c, c, c))
                continue
            while nb <= 24: buf |= data[p] << nb; p += 1; nb += 8
            r0 = buf & 31; r1 = (buf >> 5) & 31; buf >>= 10; nb -= 10
            while nb <= 24: buf |= data[p] << nb; p += 1; nb += 8
            g0 = buf & 31; g1 = (buf >> 5) & 31; buf >>= 10; nb -= 10
            while nb <= 24: buf |= data[p] << nb; p += 1; nb += 8
            b0 = buf & 31; b1 = (buf >> 5) & 31; buf >>= 10; nb -= 10
            c0 = r0 << 10 | g0 << 5 | b0; c1 = r1 << 10 | g1 << 5 | b1
            if op == 0:
                pal = (c0, _interp3(r0, r1) << 10 | _interp3(g0, g1) << 5 | _interp3(b0, b1),
                       _interp3(r1, r0) << 10 | _interp3(g1, g0) << 5 | _interp3(b1, b0), c1)
                for r in rows:
                    while nb <= 24: buf |= data[p] << nb; p += 1; nb += 8
                    canvas[r + bx:r + bx + 4] = array('H', (pal[buf & 3], pal[(buf >> 2) & 3], pal[(buf >> 4) & 3], pal[(buf >> 6) & 3]))
                    buf >>= 8; nb -= 8
            else:
                while nb <= 24: buf |= data[p] << nb; p += 1; nb += 8
                for r in rows:
                    canvas[r + bx:r + bx + 4] = array('H', (c1 if buf & 1 else c0, c1 if buf & 2 else c0, c1 if buf & 4 else c0, c1 if buf & 8 else c0))
                    buf >>= 4; nb -= 4
    return p

def decode_movie(banks, anim):
    """Yields (frame_index, canvas copy) for every frame of a format-30 movie."""
    w, h = anim['w'], anim['h']
    canvas = array('H', [0]) * (w * h)
    for i, (fmt, fw, fh, x, y, dp) in enumerate(anim['frames']):
        nxt = anim['frames'][i + 1][5] if i + 1 < len(anim['frames']) else dp + (1 << 20)
        data = banks.rd(dp, max(nxt - dp, 0) + 8)
        decode_movie_frame(data, fw, fh, canvas)
        yield i, array('H', canvas)

# ---------------------------------------------------------------- fonts
FONT_COLORS = [b'\0\0\0\0', b'\xff\xff\xff\xff', b'\xff\xb4\x28\xff', b'\xff\x50\x50\xff', b'\x50\xa0\xff\xff', b'\x7e\xe7\x87\xff']

def parse_font(banks, ptr):
    """FontData {nchars, height, max_w, ncolors, spacing, chars*}; Character (28 bytes)
    {code, x_off, baseline, w, h, advance (0 = w + spacing), pixels*}; pixels are one
    byte per pixel: 0 transparent, else an index into the Font's colour table."""
    nchars, height, max_w, ncolors, spacing, tab = struct.unpack('<6I', banks.rd(ptr, 24))
    glyphs = []
    for i in range(nchars):
        code, xo, base, w, h, adv, dp = struct.unpack('<7I', banks.rd(tab + i * 28, 28))
        xo = xo - (1 << 32) if xo >= 1 << 31 else xo
        base = base - (1 << 32) if base >= 1 << 31 else base
        glyphs.append(dict(ch=chr(code & 0xff), xo=xo, base=base, w=w, h=h, adv=adv or (w + spacing), data=dp))
    return dict(nchars=nchars, height=height, max_w=max_w, ncolors=ncolors, spacing=spacing, glyphs=glyphs)

def font_sheet(banks, font, path):
    """All glyphs side by side (1 px gap) in one PNG; returns the glyph list with sheet x."""
    gl = font['glyphs']
    top = min(g['base'] - g['h'] for g in gl); bottom = max(g['base'] for g in gl)
    H = max(1, bottom - top); W = sum(g['w'] + 1 for g in gl)
    lines = [bytearray(W * 4) for _ in range(H)]
    x = 0; out = []
    for g in gl:
        px = banks.rd(g['data'], g['w'] * g['h'])
        y0 = g['base'] - g['h'] - top
        for y in range(g['h']):
            row = px[y * g['w']:(y + 1) * g['w']]
            lines[y0 + y][x * 4:(x + g['w']) * 4] = b''.join(FONT_COLORS[min(v, len(FONT_COLORS) - 1)] for v in row)
        out.append(dict(ch=g['ch'], sx=x, sy=0, w=g['w'], h=H, xo=g['xo'], adv=g['adv']))
        x += g['w'] + 1
    png_from_rgba_rows(lines, W, H, path)
    return out, W, H, top

# ---------------------------------------------------------------- PNG output
LUT = [None] * 65536
def _lut():
    for v in range(32768):
        r = (v >> 10) & 31; g = (v >> 5) & 31; b = v & 31
        LUT[v] = bytes((r << 3 | r >> 2, g << 3 | g >> 2, b << 3 | b >> 2, 255))
    for v in range(32768, 65536): LUT[v] = LUT[v & 0x7fff]   # high bit ignored by the 15-bit display
    LUT[TRANSPARENT] = b'\0\0\0\0'
_lut()

def png_from_rgba_rows(rows, w, h, path):
    def ch(t, b): return struct.pack('>I', len(b)) + t + b + struct.pack('>I', zlib.crc32(t + b) & 0xffffffff)
    raw = b''.join(b'\0' + r for r in rows)
    open(path, 'wb').write(b'\x89PNG\r\n\x1a\n' + ch(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0)) + ch(b'IDAT', zlib.compress(raw, 6)) + ch(b'IEND', b''))

try:
    import numpy as _np
    _NPLUT = _np.frombuffer(b''.join(LUT[v] if LUT[v] else b'\0\0\0\0' for v in range(65536)), dtype=_np.uint32)
    def rgba_row(row): return _NPLUT[_np.frombuffer(row.tobytes() if hasattr(row, 'tobytes') else bytes(row), dtype=_np.uint16)].tobytes()
except ImportError:
    def rgba_row(row): return b''.join(LUT[v] for v in row)

def sheet(frames_pix, sizes, w, h, path, max_w=2048, cols=None):
    n = len(frames_pix)
    if cols is None: cols = max(1, min(n, max_w // max(w, 1)))
    rows = (n + cols - 1) // cols
    SW, SH = cols * w, rows * h
    lines = [bytearray(SW * 4) for _ in range(SH)]
    for i, pix in enumerate(frames_pix):
        fw, fh = sizes[i]
        cx, cy = (i % cols) * w, (i // cols) * h
        for y in range(fh):
            line = lines[cy + y]; row = pix[y * fw:(y + 1) * fw]
            line[cx * 4:(cx + fw) * 4] = rgba_row(row)
    png_from_rgba_rows(lines, SW, SH, path)
    return cols, rows

# ---------------------------------------------------------------- sounds
def extract_sounds(sound_bin, out_dir, acd_names):
    raw = open(sound_bin, 'rb').read()
    ver, hs, cnt, es = struct.unpack_from('<IIII', raw, 0)
    os.makedirs(out_dir, exist_ok=True)
    entries = []
    for i in range(cnt):
        e = bytes(b ^ 0x3a for b in raw[hs + i * es:hs + (i + 1) * es])
        name = e[:e.find(b'\0')].decode('latin1')
        off, size = struct.unpack_from('<II', e, es - 8)
        blob = bytes(b ^ 0x3a for b in raw[off:off + size])
        fn = name + '.ogg'
        open(os.path.join(out_dir, fn), 'wb').write(blob)
        m = re.match(r'S([0-9A-F]{4})', name)
        tid = int(m.group(1), 16) if m else None
        entries.append(dict(id=i, name=name, file=fn, size=size, track=tid, label=acd_names.get(tid, '')))
    return entries

def acd_labels(game_rom, syms):
    g = open(game_rom, 'rb').read()
    labels = {}
    for addr, s in syms.items():
        if not s.startswith('acd_'): continue
        o = addr - 0x100000
        if 0 <= o < len(g) - 4:
            tid = struct.unpack_from('<H', g, o)[0]
            lab = re.sub(r'_tr_\d+$', '', s[4:])
            labels.setdefault(tid, lab)
    return labels

# ---------------------------------------------------------------- main
CATEGORIES = [  # (symbol regex, kind, name group)
    (r'anim_(.*)_ptr$', 'anim'),
    (r'pict_(.*)_ptr$', 'pict'),
    (r'movie_(.*)_ptr$', 'movie'),
    (r'(menu_background_.*|system_video_test_align)_ptr$', 'menu'),
]

def extract_graphic(banks, a, name, kind, ptr, cache, log):
    rec = dict(name=name, kind=kind, ptr='%08x' % ptr,
               bank=(ptr - 0x14000000) >> 24 if 0x14000000 <= ptr < 0x18000000 else ('update flash' if ptr >= 0x12000000 and ptr < 0x14000000 else None))
    try:
        an = parse_anim(banks, ptr)
    except Exception as e:
        rec.update(status='unreadable', error=str(e)); return rec
    fmts = sorted(set(f[0] for f in an['frames']))
    rec.update(nframes=an['nframes'], fps=an['rate'], w=an['w'], h=an['h'], colors=an['pal_count'], formats=fmts)
    if fmts == [MOVIE_FORMAT]:
        w, h = an['w'], an['h']
        cols = max(1, min(an['nframes'], 2048 // w)); per = cols * max(1, 2048 // h)
        sheets = []; batch = []
        def flush():
            k = len(sheets); fn = 'gfx/%s_%d.png' % (name, k)
            sheet(batch, [(w, h)] * len(batch), w, h, os.path.join(a.out, fn), cols=cols)
            sheets.append(fn); batch.clear()
        for i, canvas in decode_movie(banks, an):
            batch.append(canvas)
            if len(batch) == per: flush()
            if i % 50 == 49: log('  %s frame %d/%d' % (name, i + 1, an['nframes']))
        if batch: flush()
        rec.update(status='ok', sheets=sheets, per_sheet=per, cols=cols, rows=(per + cols - 1) // cols, warnings=0)
        return rec
    if not all(f in DICT_FORMATS or f in LRLE_FORMATS or f in RAW_FORMATS or f in RAW8_FORMATS for f in fmts):
        rec.update(status='unsupported'); return rec
    pix = []; warn = 0; sizes = []
    for i in range(an['nframes']):
        fmt, fw, fh = an['frames'][i][:3]
        try:
            p, err = decode_frame(banks, an, i, cache)
        except Exception as e:
            rec.update(status='unreadable', error='frame %d: %s' % (i, e)); return rec
        pix.append(p); sizes.append((fw, fh)); warn += bool(err)
    cw = max(sz[0] for sz in sizes); chh = max(sz[1] for sz in sizes)
    cols, rows = sheet(pix, sizes, cw, chh, os.path.join(a.out, 'gfx', name + '.png'))
    rec.update(status='ok', sheet='gfx/' + name + '.png', cols=cols, rows=rows, warnings=warn, w=cw, h=chh)
    if any(sz != (cw, chh) for sz in sizes): rec['frame_sizes'] = sizes
    return rec

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(HERE, 'assets'))
    ap.add_argument('--roms', default=os.path.join(REPO, 'roms'))
    ap.add_argument('--update', default=os.path.join(REPO, 'updates', 'pin2000_50070_0160_09222003_B_10000000', '50070'))
    ap.add_argument('--only', default='', help='regex: only extract graphics/fonts whose name matches (testing)')
    ap.add_argument('--no-sounds', action='store_true')
    a = ap.parse_args()
    os.makedirs(os.path.join(a.out, 'gfx'), exist_ok=True)
    os.makedirs(os.path.join(a.out, 'fonts'), exist_ok=True)
    t0 = time.time()
    log = lambda s: print('%6.0fs %s' % (time.time() - t0, s), flush=True)
    def upd(suffix): return os.path.join(a.update, 'pin2000_50070_0160_' + suffix)
    banks = Banks(a.roms, upd('im_flsh0.rom'))
    game_rom = upd('game.rom')
    syms = load_symbols(upd('symbols.rom'))
    g = open(game_rom, 'rb').read()
    only = re.compile(a.only) if a.only else None
    # logo gif served by the game's http server
    i = g.find(b'GIF89a')
    if i >= 0:
        j = g.find(b'\x00\x3b', i); open(os.path.join(a.out, 'p2klogo.gif'), 'wb').write(g[i:j + 2])
    # graphics: animations, stills, service-menu backgrounds, movies
    items = []
    for addr, s in sorted(syms.items()):
        for pat, kind in CATEGORIES:
            m = re.match(pat, s)
            if m:
                items.append((kind, m.group(1), addr)); break
    if only: items = [it for it in items if only.search(it[1])]
    anims = []; cache = {}
    for k, (kind, name, addr) in enumerate(items):
        ptr = struct.unpack_from('<I', g, addr - 0x100000)[0]
        rec = extract_graphic(banks, a, name, kind, ptr, cache, log)
        anims.append(rec)
        if k % 25 == 0 or kind == 'movie':
            log('[%3d/%d] %-5s %-40s %s' % (k, len(items), kind, name, rec.get('status') + (' %dx%d %d fr' % (rec['w'], rec['h'], rec['nframes']) if 'w' in rec else '')))
    # fonts
    fonts = []
    for addr, s in sorted(syms.items()):
        m = re.match(r'font_(.*)_data_ptr$', s)
        if not m or (only and not only.search(m.group(1))): continue
        name = m.group(1); ptr = struct.unpack_from('<I', g, addr - 0x100000)[0]
        rec = dict(name=name, ptr='%08x' % ptr)
        try:
            f = parse_font(banks, ptr)
            glyphs, W, H, top = font_sheet(banks, f, os.path.join(a.out, 'fonts', name + '.png'))
            rec.update(status='ok', sheet='fonts/%s.png' % name, nchars=f['nchars'], height=f['height'], max_w=f['max_w'], colors=f['ncolors'],
                       spacing=f['spacing'], cell_h=H, top=top, glyphs=glyphs)
        except Exception as e:
            rec.update(status='unreadable', error=str(e))
        fonts.append(rec)
    log('%d fonts' % len(fonts))
    sounds = []
    if not a.no_sounds:
        labels = acd_labels(game_rom, syms)
        sounds = extract_sounds(os.path.join(a.roms, 'rfm_sound.bin'), os.path.join(a.out, 'sounds'), labels)
    json.dump(dict(game='Revenge From Mars 1.6', generated=time.strftime('%Y-%m-%d %H:%M'), animations=anims, fonts=fonts, sounds=sounds),
              open(os.path.join(a.out, 'index.json'), 'w'), indent=1)
    ok = sum(1 for x in anims if x.get('status') == 'ok')
    for x in anims:
        if x.get('status') != 'ok': log('  not decoded: %s %s (%s %s)' % (x['kind'], x['name'], x.get('status'), x.get('error', x.get('formats'))))
    log("done: %d/%d graphics decoded, %d fonts, %d sounds" % (ok, len(anims), len(fonts), len(sounds)))

if __name__ == '__main__':
    main()
