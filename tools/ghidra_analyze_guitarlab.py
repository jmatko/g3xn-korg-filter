#!/usr/bin/env python3
"""
Ghidra Headless Analysis Script for Guitar Lab.exe
Run from Ghidra's Python console or via:
  /home/user/ghidra_12.2_PUBLIC/ghidraRun -postScript analyze_guitarlab.py

This script:
1. Finds the AVSysExMessage class and analyzes its methods
2. Finds the AVZoomDevice class and analyzes command flow
3. Looks for CRC calculation functions
4. Identifies timing constants used in MIDI communication
"""

# This is a Ghidra headless script
# It runs in the Ghidra Python environment

from ghidra.app.decompiler import DecompInterface
from ghidra.program.model.listing import Function
from ghidra.program.model.symbol import ReferenceManager
import re

def find_class_by_name(class_name):
    """Find a class by name in the program"""
    monitor = currentProgram.getMonitor()
    fm = currentProgram.getFunctionManager()
    
    # Search for methods that reference the class name
    results = []
    for ref in currentProgram.getReferenceManager().getReferencesTo(
        currentProgram.getSymbolTable().findSymbol(class_name)
    ):
        func = fm.getFunctionAt(ref.getFromAddress())
        if func:
            results.append(func)
    
    return results

def analyze_function(func):
    """Decompile and analyze a function"""
    decomp = DecompInterface()
    decomp.openProgram(currentProgram)
    result = decomp.decompileFunction(func, 30, monitor)
    
    if result is not None:
        ccode = result.getDecompiledFunction().getC()
        return ccode
    
    return None

def main():
    print("=" * 70)
    print("Guitar Lab.exe Ghidra Analysis")
    print("=" * 70)
    
    # 1. Find key classes
    classes = [
        "AVSysExMessage",
        "AVMidiManager", 
        "AVZoomDevice",
        "AVGuitarLabDeviceDelegate",
        "Win32MidiService",
        "CommandManager",
    ]
    
    for cls in classes:
        print(f"\n--- {cls} ---")
        funcs = find_class_by_name(cls)
        print(f"  Found {len(funcs)} functions referencing this class")
        for func in funcs[:5]:
            print(f"  - {func.getName()} at {func.getEntryPoint()}")
    
    # 2. Look for CRC functions
    print("\n--- CRC Functions ---")
    fm = currentProgram.getFunctionManager()
    for func in fm.getFunctions(True):
        name = func.getName().lower()
        if 'crc' in name or 'checksum' in name or 'xor' in name:
            print(f"  {func.getName()} at {func.getEntryPoint()}")
            ccode = analyze_function(func)
            if ccode:
                print(f"  Decompiled:")
                for line in ccode.split('\n')[:20]:
                    print(f"    {line}")
    
    # 3. Look for MIDI send/receive functions
    print("\n--- MIDI Functions ---")
    for func in fm.getFunctions(True):
        name = func.getName().lower()
        if any(x in name for x in ['midi', 'sysex', 'send', 'receive', 'transmit']):
            print(f"  {func.getName()} at {func.getEntryPoint()}")
    
    # 4. Look for timing constants
    print("\n--- Timing Constants ---")
    # Look for Sleep() calls
    for func in fm.getFunctions(True):
        ccode = analyze_function(func)
        if ccode and 'Sleep(' in ccode:
            matches = re.findall(r'Sleep\((\d+)\)', ccode)
            if matches:
                print(f"  {func.getName()}: Sleep({', '.join(matches[:5])}ms)")

if __name__ == "__main__":
    main()