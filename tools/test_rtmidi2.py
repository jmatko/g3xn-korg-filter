#!/usr/bin/env python3
"""
Test MIDI communication with G3Xn via python-rtmidi (ALSA seq path).
No callback - poll for messages.
"""
import rtmidi
import time
import sys

def hexdump(b, n=100):
    return " ".join(f"{x:02x}" for x in b[:n]) + ("..." if len(b) > n else "")

def main():
    mi = rtmidi.MidiIn()
    mo = rtmidi.MidiOut()
    
    # Find the ZOOM port
    zoom_in = zoom_out = None
    for i in range(mi.get_port_count()):
        name = mi.get_port_name(i)
        if "ZOOM" in name.upper():
            zoom_in = i
    for i in range(mo.get_port_count()):
        name = mo.get_port_name(i)
        if "ZOOM" in name.upper():
            zoom_out = i
    
    if zoom_in is None or zoom_out is None:
        print("ZOOM port not found!")
        return
    
    mi.open_port(zoom_in)
    mo.open_port(zoom_out)
    
    print(f"Connected to ZOOM G Series")
    
    # Send list request: F0 52 00 6E 60 25 00 00 2A 00 F7
    print("Sending: F0 52 00 6E 60 25 00 00 2A 00 F7 (list start)")
    msg = [0xF0, 0x52, 0x00, 0x6E, 0x60, 0x25, 0x00, 0x00, 0x2A, 0x00, 0xF7]
    mo.send_message(msg)
    
    # Poll for response
    deadline = time.time() + 3.0
    got_response = False
    while time.time() < deadline:
        m = mi.get_message()
        if m is not None:
            data = m[0]
            print(f"  RX: {hexdump(data)}")
            got_response = True
            # If we got a response, continue reading for a bit more
            deadline = time.time() + 1.0
        else:
            time.sleep(0.01)
    
    if not got_response:
        print("  (no response received)")
    
    # Try a simple status query
    print("\nSending: F0 52 00 6E 60 09 F7 (term)")
    msg = [0xF0, 0x52, 0x00, 0x6E, 0x60, 0x09, 0xF7]
    mo.send_message(msg)
    deadline = time.time() + 2.0
    while time.time() < deadline:
        m = mi.get_message()
        if m is not None:
            data = m[0]
            print(f"  RX: {hexdump(data)}")
        else:
            time.sleep(0.01)
    
    print("\nDone.")
    mi.close_port()
    mo.close_port()

if __name__ == "__main__":
    main()