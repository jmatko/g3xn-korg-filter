#!/usr/bin/env python3
"""
write_test.py — Systematic write protocol test against the G3Xn.

Tries multiple variations of the file-write command sequence to find
what the G3Xn actually accepts. Logs every exchange.

Usage: python3 write_test.py
"""
import sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) if (os := __import__('os')) else '.')
from g3xn_raw import RawG3Xn, hexdump, u14, pack7, crc5

LOG = []
def log(msg):
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    LOG.append(line)

def save_log(path="write_test.log"):
    with open(path, "w") as f:
        f.write("\n".join(LOG) + "\n")
    print(f"\nLog saved to {path}")

def try_write(g, label, create_cmd, open_cmd, data=b"\x00" * 16):
    """Try a write sequence and report the result."""
    name = b'WRTEST.ZD2\x00'
    log(f"--- {label} ---")
    
    # Create
    g.send(create_cmd + name)
    r = g.read_reply(3.0)
    log(f"  create: {hexdump(r, 40)}")
    if not r or r[0] != 0x60:
        log("  -> NO REPLY")
        return False
    if r[1] == 0x04:
        log("  -> CREATE ACCEPTED!")
    else:
        log(f"  -> create rejected (status={r[1]:02x})")
        return False
    time.sleep(0.3)
    
    # Open for write
    g.send(open_cmd + name)
    r = g.read_reply(3.0)
    log(f"  open:   {hexdump(r, 40)}")
    if not r or r[0] != 0x60:
        log("  -> NO REPLY")
        return False
    if r[1] == 0x04:
        log("  -> OPEN ACCEPTED!")
    else:
        log(f"  -> open rejected (status={r[1]:02x})")
        return False
    time.sleep(0.3)
    
    # Ack
    g.send(bytes([0x60, 0x05, 0x00]))
    r = g.read_reply(2.0)
    log(f"  ack:    {hexdump(r, 40)}")
    time.sleep(0.3)
    
    # Write one block
    body = (bytes([0x60, 0x23, 0x40, 0x00, 0x00, 0x00, 0x00])
            + u14(len(data)) + bytes([0x00, 0x00, 0x00])
            + pack7(data) + crc5(data))
    g.send(body)
    r = g.read_reply(3.0)
    log(f"  write:  {hexdump(r, 40)}")
    if r and r[0] == 0x60 and r[1] == 0x04:
        log("  -> WRITE ACCEPTED!")
    else:
        log(f"  -> write rejected")
    time.sleep(0.3)
    
    # Ack
    g.send(bytes([0x60, 0x05, 0x00]))
    r = g.read_reply(2.0)
    log(f"  ack2:   {hexdump(r, 40)}")
    time.sleep(0.3)
    
    # Close
    g.send(bytes([0x60, 0x21, 0x40, 0x00, 0x00, 0x00, 0x00]))
    r = g.read_reply(2.0)
    log(f"  close:  {hexdump(r, 40)}")
    time.sleep(0.3)
    
    # Term
    g.send(bytes([0x60, 0x09]))
    r = g.read_reply(2.0)
    log(f"  term:   {hexdump(r, 40)}")
    
    # Verify: check if the file exists
    time.sleep(0.5)
    g.send(bytes([0x60, 0x25, 0x00, 0x00]) + name)
    r = g.read_reply(3.0)
    log(f"  verify: {hexdump(r, 40)}")
    if r and r[0] == 0x60 and r[1] == 0x04:
        log("  *** FILE EXISTS — WRITE WORKED! ***")
        return True
    else:
        log("  -> file not found after write")
        return False

def main():
    g = RawG3Xn()
    log("=== G3Xn Write Protocol Test ===")
    
    # First, verify the pedal is alive
    r = g.request(bytes([0x60, 0x25, 0x00, 0x00, 0x2A, 0x00]))
    if not r or r[0] != 0x60:
        log("PEDAL NOT RESPONDING — aborting")
        g.close()
        save_log()
        return
    log(f"Pedal alive: {hexdump(r, 40)}")
    
    # Test 1: Standard mungewell sequence
    try_write(g, "Test 1: mungewell (60 24 create / 60 20 01 open)",
              bytes([0x60, 0x24]),
              bytes([0x60, 0x20, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]))
    
    # Test 2: Create with 00 00 after 60 24
    time.sleep(1)
    try_write(g, "Test 2: 60 24 00 00 create / 60 20 01 open",
              bytes([0x60, 0x24, 0x00, 0x00]),
              bytes([0x60, 0x20, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]))
    
    # Test 3: Open-for-write with different mode bytes
    time.sleep(1)
    for mode in [0x01, 0x02, 0x03, 0x41]:
        try_write(g, f"Test 3: 60 24 create / 60 20 {mode:02x} open (mode={mode:#x})",
                  bytes([0x60, 0x24]),
                  bytes([0x60, 0x20, mode, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]))
        time.sleep(0.5)
    
    # Test 4: Maybe the G3Xn uses a different create command
    time.sleep(1)
    for cmd in [0x28, 0x2C, 0x2D, 0x2E, 0x2F, 0x30]:
        try_write(g, f"Test 4: 60 {cmd:02x} create / 60 20 01 open",
                  bytes([0x60, cmd]),
                  bytes([0x60, 0x20, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]))
        time.sleep(0.5)
    
    # Test 5: Maybe create needs a size parameter
    time.sleep(1)
    try_write(g, "Test 5: 60 24 <size u14> create / 60 20 01 open",
              bytes([0x60, 0x24]) + u14(16),
              bytes([0x60, 0x20, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]))
    
    # Test 6: Maybe the write block format is different
    # Try without the 40 00 00 00 00 prefix
    time.sleep(1)
    log("--- Test 6: alternate write block format ---")
    name = b'WRTEST.ZD2\x00'
    data = b"\x00" * 16
    g.send(bytes([0x60, 0x24]) + name)
    r = g.read_reply(3.0)
    log(f"  create: {hexdump(r, 40)}")
    g.send(bytes([0x60, 0x20, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]) + name)
    r = g.read_reply(3.0)
    log(f"  open:   {hexdump(r, 40)}")
    g.send(bytes([0x60, 0x05, 0x00]))
    r = g.read_reply(2.0)
    log(f"  ack:    {hexdump(r, 40)}")
    # Alternate: 60 23 <len u14> <data> <crc5>
    body = bytes([0x60, 0x23]) + u14(len(data)) + pack7(data) + crc5(data)
    g.send(body)
    r = g.read_reply(3.0)
    log(f"  write:  {hexdump(r, 40)}")
    g.send(bytes([0x60, 0x21, 0x40, 0x00, 0x00, 0x00, 0x00]))
    g.read_reply(2.0)
    g.send(bytes([0x60, 0x09]))
    g.read_reply(2.0)
    
    g.close()
    save_log()

if __name__ == "__main__":
    main()