/*
 * zoom_protocol.js — G3Xn / Zoom Z-series file + patch protocol, pure logic.
 *
 * Shared by the web UI (web/index.html) and the Node test harness (test/).
 * No DOM, no WebMIDI — just byte-level protocol primitives so the tricky
 * parts (7-bit packing, CRC, ZD2/ZT2 parsing) can be unit-tested offline.
 *
 * Protocol references (both MIT):
 *   - cwoodard1121/zoom-g3xn-agent-skill  (G3Xn-verified, fw 2.20)
 *   - mungewell/zoom-zt2                  (G1Four/MS Plus write path)
 *
 * Every SysEx message is framed:  F0 52 00 6E <body...> F7
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.ZoomProtocol = factory();
  }
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  // ---------------------------------------------------------------------------
  // CRC-32 (IEEE, as used by zlib / binascii.crc32). Table-driven.
  // ---------------------------------------------------------------------------
  const CRC_TABLE = (() => {
    const t = new Uint32Array(256);
    for (let n = 0; n < 256; n++) {
      let c = n;
      for (let k = 0; k < 8; k++) c = (c & 1) ? (0xEDB88320 ^ (c >>> 1)) : (c >>> 1);
      t[n] = c >>> 0;
    }
    return t;
  })();

  function crc32(data) {
    // data: Uint8Array | number[]
    let c = 0xFFFFFFFF;
    for (let i = 0; i < data.length; i++) {
      c = CRC_TABLE[(c ^ data[i]) & 0xFF] ^ (c >>> 8);
    }
    return (c ^ 0xFFFFFFFF) >>> 0;
  }

  // Zoom's 5-byte checksum: inverted CRC-32 of the RAW 8-bit payload,
  // emitted as five 7-bit bytes, low group first.
  function checksum5(data) {
    const crc = crc32(data); // already inverted (>>> 0)
    const out = new Uint8Array(5);
    for (let i = 0; i < 5; i++) out[i] = (crc >>> (7 * i)) & 0x7F;
    return out;
  }

  // ---------------------------------------------------------------------------
  // 7-bit packing — the "high-bit-byte" scheme.
  //   For each group of up to 7 bytes: emit ONE header byte (bit j of header =
  //   bit 7 of byte j) followed by the 7 low bytes (b & 0x7F).
  //   7 bytes -> 8 packed bytes. Packed length = ceil(n/7) * 8.
  // ---------------------------------------------------------------------------
  function pack7(data) {
    // High-bit-byte scheme, matching mungewell/zoom-zt2 pack():
    //   each full group of 7 bytes -> 8 bytes (1 high-bit byte + 7 low bytes).
    //   the LAST group is NOT padded to 8 bytes (mungewell omits the trailing pad).
    const n = data.length;
    const out = [];
    for (let i = 0; i < n; i += 7) {
      const end = Math.min(i + 7, n);
      let high = 0;
      for (let j = i; j < end; j++) if (data[j] & 0x80) high |= 0x40 >> (j - i);
      out.push(high);
      for (let j = i; j < end; j++) out.push(data[j] & 0x7F);
    }
    return new Uint8Array(out);
  }

  function unpack7(packed, length) {
    // length = number of original 8-bit bytes (pack7 pads the last group to a
    // full 8-byte frame, so the caller must tell us how many bytes are real).
    const out = [];
    for (let i = 0; i < packed.length; i += 8) {
      const high = packed[i];
      const avail = Math.min(7, packed.length - i - 1); // data bytes in this frame
      for (let j = 0; j < avail; j++) {
        const b = packed[i + 1 + j];
        out.push(b | ((high & (0x40 >> j)) ? 0x80 : 0));
      }
    }
    return new Uint8Array(out.slice(0, length));
  }

  // ---------------------------------------------------------------------------
  // SysEx framing
  // ---------------------------------------------------------------------------
  const SYSEX = { F0: 0xF0, F7: 0xF7, MANUFACTURER: [0x52, 0x00, 0x6E] };

  // Build a full SysEx message: F0 52 00 6E <body> F7
  function buildSysEx(body) {
    // F0 52 00 6E <body> F7  =>  5 framing bytes total
    const out = new Uint8Array(body.length + 5);
    out[0] = 0xF0;
    out[1] = 0x52; out[2] = 0x00; out[3] = 0x6E;
    out.set(body, 4);
    out[out.length - 1] = 0xF7;
    return out;
  }

  // Strip F0 52 00 6E ... F7 -> body bytes. Returns null if not a matching
  // Zoom SysEx (so callers can ignore unrelated traffic).
  function parseSysEx(msg) {
    if (!msg || msg.length < 6) return null;
    if (msg[0] !== 0xF0 || msg[msg.length - 1] !== 0xF7) return null;
    if (msg[1] !== 0x52 || msg[2] !== 0x00 || msg[3] !== 0x6E) return null;
    return msg.slice(4, msg.length - 1);
  }

  // A file-family reply starts with body[0]==0x60. Status byte is body[4]
  // (==0x04 means "entry/data follows").
  function isFileReply(msg) {
    const b = parseSysEx(msg);
    return b ? b[0] === 0x60 : false;
  }

  // ---------------------------------------------------------------------------
  // ZD2 container header parse
  // ---------------------------------------------------------------------------
  // Layout (see notes/05-webmidi-handoff.md section 4):
  //   0x00 magic "ZDLF"
  //   0x04 length   u32le  (NOT the file size; semantics unknown)
  //   0x08 checksum u32le
  //   0x0C target   u32le  (bitfield)
  //   0x10 unknown (73 bytes)
  //   0x59 version (4 ASCII)
  //   0x5D 00 00
  //   0x5F group    u8
  //   0x60 id       u32le  (top byte == group)
  //   0x64 name     (11 bytes)
  //   0x6D groupname(11 bytes)
  function parseZd2Header(data) {
    const d = data;
    const magic = String.fromCharCode(d[0], d[1], d[2], d[3]);
    if (magic !== 'ZDLF') return null;
    const u32 = off => (d[off] | (d[off + 1] << 8) | (d[off + 2] << 16) | (d[off + 3] << 24)) >>> 0;
    const ascii = (off, n) => {
      let s = '';
      for (let i = 0; i < n; i++) { const c = d[off + i]; if (c === 0) break; s += String.fromCharCode(c); }
      return s;
    };
    return {
      magic,
      lengthField: u32(0x04),
      checksum: u32(0x08),
      target: u32(0x0C),
      version: ascii(0x59, 4),
      group: d[0x5F],
      id: u32(0x60),
      name: ascii(0x64, 11),
      groupname: ascii(0x6D, 11),
      size: d.length,
    };
  }

  // ---------------------------------------------------------------------------
  // ZT2 (FLST_SEQ) parse + rebuild + add/remove effect
  // ---------------------------------------------------------------------------
  // Total 8502 bytes, zero-padded.
  //   Header (78 bytes): 0x00 ">>>\0" ... 0x18 filename(12) ... 0x32 "<<\0" ...
  //   Groups: ">>>\0" + group u8 + pad21 (26B)
  //           entries (26B each): filename(12) + 00 + version(4) + 00 + installed(1) + id u32le + 00 00 00
  //           "<<\0" + group u8 + pad21 (26B)
  const ZT2_SIZE = 8502;
  const ZT2_HEADER = 78;
  const ZT2_GROUP_HDR = 26;
  const ZT2_ENTRY = 26;

  function zt2ReadName(d, off, n) {
    let s = '';
    for (let i = 0; i < n; i++) { const c = d[off + i]; if (c === 0) break; s += String.fromCharCode(c); }
    return s;
  }

  function parseZt2(data) {
    if (data.length < ZT2_SIZE) throw new Error('ZT2 too small: ' + data.length);
    const d = data;
    const header = {
      magic: zt2ReadName(d, 0, 3),
      filename: zt2ReadName(d, 0x18, 12),
    };
    const groups = [];
    let off = ZT2_HEADER;
    while (off + ZT2_GROUP_HDR <= ZT2_SIZE) {
      if (zt2ReadName(d, off, 3) !== '>>>') break;
      const group = d[off + 4];
      off += ZT2_GROUP_HDR;
      const entries = [];
      while (off + ZT2_ENTRY <= ZT2_SIZE) {
        const fname = zt2ReadName(d, off, 12);
        if (fname === '') break; // empty entry = end of group
        const version = zt2ReadName(d, off + 13, 4);
        const installed = d[off + 18];
        const id = (d[off + 19] | (d[off + 20] << 8) | (d[off + 21] << 16) | (d[off + 22] << 24)) >>> 0;
        entries.push({ filename: fname, version, installed, id });
        off += ZT2_ENTRY;
      }
      // group footer
      if (off + ZT2_GROUP_HDR <= ZT2_SIZE && zt2ReadName(d, off, 3) === '<<<') off += ZT2_GROUP_HDR;
      groups.push({ group, entries });
    }
    return { header, groups, size: data.length };
  }

  function zt2WriteName(buf, off, str, n) {
    for (let i = 0; i < n; i++) buf[off + i] = i < str.length ? str.charCodeAt(i) & 0xFF : 0;
  }

  function rebuildZt2(z) {
    const buf = new Uint8Array(ZT2_SIZE); // zero-padded
    // header
    zt2WriteName(buf, 0, '>>>', 3); buf[3] = 0;
    zt2WriteName(buf, 0x18, z.header.filename, 12);
    buf[0x2A] = 1;
    zt2WriteName(buf, 0x32, '<<<', 3); buf[0x35] = 0;
    // groups
    let off = ZT2_HEADER;
    for (const g of z.groups) {
      zt2WriteName(buf, off, '>>>', 3); buf[off + 3] = 0; buf[off + 4] = g.group;
      off += ZT2_GROUP_HDR;
      for (const e of g.entries) {
        zt2WriteName(buf, off, e.filename, 12);
        buf[off + 12] = 0;
        zt2WriteName(buf, off + 13, e.version, 4);
        buf[off + 17] = 0;
        buf[off + 18] = e.installed ? 1 : 0;
        buf[off + 19] = e.id & 0xFF;
        buf[off + 20] = (e.id >> 8) & 0xFF;
        buf[off + 21] = (e.id >> 16) & 0xFF;
        buf[off + 22] = (e.id >> 24) & 0xFF;
        buf[off + 23] = 0; buf[off + 24] = 0; buf[off + 25] = 0;
        off += ZT2_ENTRY;
      }
      zt2WriteName(buf, off, '<<<', 3); buf[off + 3] = 0; buf[off + 4] = g.group;
      off += ZT2_GROUP_HDR;
    }
    return buf;
  }

  // Add an effect entry. Returns a NEW z object (does not mutate input).
  function zt2AddEffect(z, entry) {
    const zc = cloneZt2(z);
    const groupNew = (entry.id >> 24) & 0xFF;
    let g = zc.groups.find(g => g.group === groupNew);
    if (!g) { g = { group: groupNew, entries: [] }; zc.groups.push(g); }
    // remove any existing entry with the same filename
    g.entries = g.entries.filter(e => e.filename !== entry.filename);
    g.entries.push({ filename: entry.filename, version: entry.version, installed: 1, id: entry.id });
    return zc;
  }

  function zt2RemoveEffect(z, filename) {
    const zc = cloneZt2(z);
    for (const g of zc.groups) g.entries = g.entries.filter(e => e.filename !== filename);
    return zc;
  }

  function cloneZt2(z) {
    return {
      header: { ...z.header },
      groups: z.groups.map(g => ({ group: g.group, entries: g.entries.map(e => ({ ...e })) })),
      size: z.size,
    };
  }

  // ---------------------------------------------------------------------------
  // u35 little-endian (for disk usage reply)
  // ---------------------------------------------------------------------------
  function fromU35(b) {
    // 35-bit little-endian: b0 + b1*128 + b2*128^2 + b3*128^3 + b4*128^4 (b4 low nibble only)
    return b[0] + b[1] * 128 + b[2] * 16384 + b[3] * 2097152 + (b[4] & 0x0F) * 268435456;
  }

  return {
    crc32, checksum5,
    pack7, unpack7,
    SYSEX, buildSysEx, parseSysEx, isFileReply,
    parseZd2Header,
    ZT2_SIZE, parseZt2, rebuildZt2, zt2AddEffect, zt2RemoveEffect,
    fromU35,
  };
});