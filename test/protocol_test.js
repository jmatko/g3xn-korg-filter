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
const zd2Path = path.join(__dirname, '..', 'files', 'XXTRVL_g3xn.ZD2');
if (fs.existsSync(zd2Path)) {
  const h = P.parseZd2Header(new Uint8Array(fs.readFileSync(zd2Path)));
  t('ZD2 header (Traveler / group 0x02 / id 0x02001010)',
    h.name === 'Traveler' && h.group === 0x02 && h.id === 0x02001010);
} else {
  console.log('  SKIP ZD2 header (file not found)');
}

// 4. fromU35 (35-bit little-endian)
t('fromU35([0,0,0,0,1])=128^4', P.fromU35(new Uint8Array([0, 0, 0, 0, 1])) === Math.pow(128, 4));
t('fromU35([5,2,0,0,0])=261', P.fromU35(new Uint8Array([5, 2, 0, 0, 0])) === 261);

// 5. SysEx frame round-trip
const body = new Uint8Array([0x60, 0x05, 0x00]);
const msg = P.buildSysEx(body);
const back = P.parseSysEx(msg);
t('buildSysEx/parseSysEx round-trip',
  msg[0] === 0xF0 && msg[msg.length - 1] === 0xF7 && back.length === 3 && back[0] === 0x60);

// 6. checksum5 is 5 bytes
t('checksum5 length 5', P.checksum5(new Uint8Array([1, 2, 3, 4, 5])).length === 5);

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