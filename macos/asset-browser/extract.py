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
    def __init__(self, roms):
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

# ---------------------------------------------------------------- PNG output
LUT = [None] * 65536
def _lut():
    for v in range(32768):
        r = (v >> 10) & 31; g = (v >> 5) & 31; b = v & 31
        LUT[v] = bytes((r << 3 | r >> 2, g << 3 | g >> 2, b << 3 | b >> 2, 255))
    LUT[TRANSPARENT] = b'\0\0\0\0'
_lut()

def png_from_rgba_rows(rows, w, h, path):
    def ch(t, b): return struct.pack('>I', len(b)) + t + b + struct.pack('>I', zlib.crc32(t + b) & 0xffffffff)
    raw = b''.join(b'\0' + r for r in rows)
    open(path, 'wb').write(b'\x89PNG\r\n\x1a\n' + ch(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0)) + ch(b'IDAT', zlib.compress(raw, 6)) + ch(b'IEND', b''))

def sheet(frames_pix, sizes, w, h, path, max_w=2048):
    n = len(frames_pix)
    cols = max(1, min(n, max_w // max(w, 1)))
    rows = (n + cols - 1) // cols
    SW, SH = cols * w, rows * h
    lines = [bytearray(SW * 4) for _ in range(SH)]
    for i, pix in enumerate(frames_pix):
        fw, fh = sizes[i]
        cx, cy = (i % cols) * w, (i // cols) * h
        for y in range(fh):
            line = lines[cy + y]; row = pix[y * fw:(y + 1) * fw]
            line[cx * 4:(cx + fw) * 4] = b''.join(LUT[v] for v in row)
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
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(HERE, 'assets'))
    ap.add_argument('--roms', default=os.path.join(REPO, 'roms'))
    ap.add_argument('--update', default=os.path.join(REPO, 'updates', 'pin2000_50070_0160_09222003_B_10000000', '50070'))
    ap.add_argument('--limit', type=int, default=0, help='only first N animations (testing)')
    a = ap.parse_args()
    os.makedirs(os.path.join(a.out, 'gfx'), exist_ok=True)
    t0 = time.time()
    banks = Banks(a.roms)
    game_rom = os.path.join(a.update, 'pin2000_50070_0160_game.rom')
    syms = load_symbols(os.path.join(a.update, 'pin2000_50070_0160_symbols.rom'))
    g = open(game_rom, 'rb').read()
    # logo gif served by the game's http server
    i = g.find(b'GIF89a')
    if i >= 0:
        j = g.find(b'\x00\x3b', i); open(os.path.join(a.out, 'p2klogo.gif'), 'wb').write(g[i:j + 2])
    anims = []
    names = sorted((addr, s) for addr, s in syms.items() if re.match(r'anim_.*_ptr$', s))
    if a.limit: names = names[:a.limit]
    cache = {}
    for k, (addr, sym) in enumerate(names):
        name = sym[5:-4]
        ptr = struct.unpack_from('<I', g, addr - 0x100000)[0]
        rec = dict(name=name, ptr='%08x' % ptr, bank=(ptr - 0x14000000) >> 24 if 0x14000000 <= ptr < 0x18000000 else None)
        try:
            an = parse_anim(banks, ptr)
        except Exception as e:
            rec.update(status='unreadable', error=str(e)); anims.append(rec); continue
        fmts = sorted(set(f[0] for f in an['frames']))
        rec.update(nframes=an['nframes'], fps=an['rate'], w=an['w'], h=an['h'], colors=an['pal_count'], formats=fmts)
        if not all(f in DICT_FORMATS or f in LRLE_FORMATS for f in fmts):
            rec.update(status='unsupported'); anims.append(rec); continue
        pix = []; warn = 0; sizes = []
        for i in range(an['nframes']):
            fmt, fw, fh = an['frames'][i][:3]
            p, err = decode_frame(banks, an, i, cache); pix.append(p); sizes.append((fw, fh)); warn += bool(err)
        cw = max(sz[0] for sz in sizes); chh = max(sz[1] for sz in sizes)
        cols, rows = sheet(pix, sizes, cw, chh, os.path.join(a.out, 'gfx', name + '.png'))
        rec.update(status='ok', sheet='gfx/' + name + '.png', cols=cols, rows=rows, warnings=warn, w=cw, h=chh)
        if any(sz != (cw, chh) for sz in sizes): rec['frame_sizes'] = sizes
        anims.append(rec)
        if k % 20 == 0:
            print("[%3d/%d] %-40s %4dx%-4d %4d frames %.0fs" % (k, len(names), name, an['w'], an['h'], an['nframes'], time.time() - t0), flush=True)
    labels = acd_labels(game_rom, syms)
    sounds = extract_sounds(os.path.join(a.roms, 'rfm_sound.bin'), os.path.join(a.out, 'sounds'), labels)
    json.dump(dict(game='Revenge From Mars 1.6', generated=time.strftime('%Y-%m-%d %H:%M'), animations=anims, sounds=sounds),
              open(os.path.join(a.out, 'index.json'), 'w'), indent=1)
    ok = sum(1 for x in anims if x.get('status') == 'ok')
    print("done: %d/%d animations decoded, %d sounds, %.0fs" % (ok, len(anims), len(sounds), time.time() - t0))

if __name__ == '__main__':
    main()
