#!/usr/bin/env node
/*
 * test/protocol_test.js — offline unit tests for web/zoom_protocol.js
 * Run: node test/protocol_test.js
 */
const P = require('../web/zoom_protocol.js');
const fs = require('fs');
const path = require('path');

let pass = 0, fail = 0;
function t(name, ok) {
  if (ok) { pass++; console.log('  PASS', name); }
  else { fail++; console.log('  FAIL', name); }
}

// 1. pack7/unpack7 round-trip on many sizes
let allOk = true;
for (const n of [1, 2, 3, 5, 6, 7, 8, 512, 8017, 12345]) {
  const data = new Uint8Array(n);
  for (let i = 0; i < n; i++) data[i] = (i * 31 + 7) & 0xFF;
  const up = P.unpack7(P.pack7(data), n);
  let ok = up.length === n;
  for (let i = 0; i < n && ok; i++) if (up[i] !== data[i]) ok = false;
  if (!ok) allOk = false;
}
t('pack7/unpack7 round-trip (1..12345)', allOk);

// 2. crc32 known vector (CRC32 of "123456789" = 0xCBF43926)
t('crc32("123456789")=0xcbf43926', P.crc32(new TextEncoder().encode('123456789')) === 0xCBF43926);

// 3. ZD2 header parse on the real Traveler file
const zd2Path = path.join(__dirname, '..', 'files', 'g3xn', 'XXTRVL.ZD2');
if (fs.existsSync(zd2Path)) {
  const h = P.parseZd2Header(new Uint8Array(fs.readFileSync(zd2Path)));
  t('ZD2 header (Traveler / group 0x0b PEDAL / id 0x0b001010)',
    h.name === 'Traveler' && h.group === 0x0b && h.id === 0x0b001010);
} else {
  console.log('  SKIP ZD2 header (file not found)');
}

// 4. fromU35 (disk-usage value, verified on real G3Xn reply)
//    max bytes 08 00 02 51 24  ->  0x2451020008 = 155977908232
t('fromU35 disk-max = 155977908232', P.fromU35(new Uint8Array([0x08, 0x00, 0x02, 0x51, 0x24])) === 155977908232);
t('fromU35 avail = 3', P.fromU35(new Uint8Array([0x03, 0x00, 0x00, 0x00, 0x00])) === 3);
t('fromU35([5,2,0,0,0])=517', P.fromU35(new Uint8Array([5, 2, 0, 0, 0])) === (5 | (2 << 8)));

// 5. SysEx frame round-trip
const body = new Uint8Array([0x60, 0x05, 0x00]);
const msg = P.buildSysEx(body);
const back = P.parseSysEx(msg);
t('buildSysEx/parseSysEx round-trip',
  msg[0] === 0xF0 && msg[msg.length - 1] === 0xF7 && back.length === 3 && back[0] === 0x60);

// 6. checksum5 is 5 bytes
t('checksum5 length 5', P.checksum5(new Uint8Array([1, 2, 3, 4, 5])).length === 5);

// 6b. listName — decode a real G3Xn list reply (from the captured log):
//     < f0 52 00 6e 60 04 25 00 00 17 00 00 00 00 00 46 ...
//     body = 60 04 25 00 00 17 00 00 00 00 00 46 ...  -> name starts at body[11] = 'F'
{
  const body = new Uint8Array([0x60,0x04,0x25,0x00,0x00,0x17,0x00,0x00,0x00,0x00,0x00,
    0x46,0x4c,0x53,0x54,0x5f,0x53,0x45,0x51,0x00,0x00,0x00]); // 'FLST_SEQ\0'
  const n = P.listName(body);
  t('listName real reply -> FLST_SEQ', n === 'FLST_SEQ');
  // a non-entry reply (status 03) must return null
  const noentry = new Uint8Array([0x60,0x03,0x00,0x00,0x00,0x00,0x00]);
  t('listName non-entry -> null', P.listName(noentry) === null);
}

// 6c. ZT2 (FLST_SEQ) round-trip against the real mungewell EMPTY.ZT2 sample.
//     This is the safety check for the uninstall flow: if parse->rebuild is not
//     byte-for-byte identical, we would corrupt the pedal's effect sequence.
{
  const fs = require('fs');
  const path = require('path');
  const raw = new Uint8Array(fs.readFileSync(path.join(__dirname, 'fixtures', 'EMPTY.ZT2')));
  const z = P.parseZt2(raw);
  t('ZT2 header filename = BYPASS.ZD2', z.header.filename === 'BYPASS.ZD2');
  t('ZT2 has >0 groups', z.groups.length >= 10);
  t('ZT2 EMPTY sample has 0 effects', z.groups.reduce((a, g) => a + g.entries.length, 0) === 0);
  const rebuilt = P.rebuildZt2(z);
  let diff = 0;
  for (let i = 0; i < raw.length; i++) if (raw[i] !== rebuilt[i]) diff++;
  t('ZT2 parse->rebuild is byte-for-byte identical', diff === 0);
  // add an effect, rebuild, confirm it appears and size stays 8502
  const z2 = P.zt2AddEffect(z, { filename: 'XXTRVL.ZD2', version: '1.00', id: 0x02001010 });
  const r2 = P.rebuildZt2(z2);
  t('ZT2 add-effect keeps size 8502', r2.length === 8502);
  t('ZT2 added effect present', z2.groups.some(g => g.entries.some(e => e.filename === 'XXTRVL.ZD2')));
  // remove it again -> back to original
  const z3 = P.zt2RemoveEffect(z2, 'XXTRVL.ZD2');
  const r3 = P.rebuildZt2(z3);
  let diff3 = 0;
  for (let i = 0; i < raw.length; i++) if (raw[i] !== r3[i]) diff3++;
  t('ZT2 add->remove restores original bytes', diff3 === 0);
}

// 7. pack7 matches mungewell reference on random data (inline reference)
function mwPack(data) {
  // Faithful port of mungewell/zoom-zt2 pack(): encode is a 1-indexed buffer,
  // so the high-bit shift is >> len(encode) (2 for the 1st byte, 3 for the 2nd, ...).
  const packet = [];
  let encode = [0];
  for (const byte of data) {
    encode[0] = encode[0] + ((byte & 0x80) >> encode.length);
    encode.push(byte & 0x7f);
    if (encode.length > 7) { packet.push(...encode); encode = [0]; }
  }
  if (encode.length > 1) packet.push(...encode);
  return packet;
}
let packOk = true;
for (let trial = 0; trial < 100; trial++) {
  const n = 1 + Math.floor(Math.random() * 512);
  const data = new Uint8Array(n);
  for (let i = 0; i < n; i++) data[i] = Math.floor(Math.random() * 256);
  const mine = Array.from(P.pack7(data));
  const ref = mwPack(Array.from(data));
  if (mine.length !== ref.length || mine.some((b, i) => b !== ref[i])) packOk = false;
}
t('pack7 matches mungewell reference (100 random)', packOk);

console.log('');
console.log(`${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);