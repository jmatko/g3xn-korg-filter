#!/usr/bin/env python3
"""
Test MIDI communication with G3Xn via python-rtmidi (ALSA seq path).
"""
import rtmidi
import time
import sys

def hexdump(b, n=100):
    return " ".join(f"{x:02x}" for x in b[:n]) + ("..." if len(b) > n else "")

def main():
    # Create a MIDI in and out port
    mi = rtmidi.MidiIn()
    mo = rtmidi.MidiOut()
    
    # List ports
    print("Available MIDI ports:")
    for i in range(mi.get_port_count()):
        print(f"  IN  [{i}]: {mi.get_port_name(i)}")
    for i in range(mo.get_port_count()):
        print(f"  OUT [{i}]: {mo.get_port_name(i)}")
    
    if mi.get_port_count() == 0 or mo.get_port_count() == 0:
        print("No MIDI ports available!")
        return
    
    # Find the ZOOM port
    zoom_in = zoom_out = None
    for i in range(mi.get_port_count()):
        name = mi.get_port_name(i)
        if "ZOOM" in name.upper() or "G SERIES" in name.upper():
            zoom_in = i
            print(f"Found ZOOM IN port: [{i}] {name}")
    for i in range(mo.get_port_count()):
        name = mo.get_port_name(i)
        if "ZOOM" in name.upper() or "G SERIES" in name.upper():
            zoom_out = i
            print(f"Found ZOOM OUT port: [{i}] {name}")
    
    if zoom_in is None or zoom_out is None:
        print("ZOOM port not found!")
        return
    
    # Open ports
    mi.open_port(zoom_in)
    mo.open_port(zoom_out)
    mi.set_callback(lambda msg: print(f"  RX: {hexdump(msg)}", file=sys.stderr))
    
    print(f"\nConnected to ZOOM G Series")
    print("Sending list request: F0 52 00 6E 60 25 00 00 2A 00 F7")
    
    # Send list request
    msg = [0xF0, 0x52, 0x00, 0x6E, 0x60, 0x25, 0x00, 0x00, 0x2A, 0x00, 0xF7]
    mo.send_message(msg)
    
    # Wait for response
    time.sleep(2)
    
    # Try to read any pending messages
    while True:
        msg = mi.get_message()
        if msg is None:
            break
        print(f"  RX: {hexdump(msg)}")
    
    print("\nDone.")
    mi.close_port()
    mo.close_port()

if __name__ == "__main__":
    main()