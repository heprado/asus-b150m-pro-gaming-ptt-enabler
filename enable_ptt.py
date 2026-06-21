#!/usr/bin/env python3
"""
PTT Enabler — ASUS B150M Pro Gaming
Enables Intel PTT (TPM 2.0) by patching the setupdata in the firmware CAP file.

Compatible with Windows, Linux and macOS.

Usage:
    python patch_ptt.py <file.CAP>
    python patch_ptt.py <file.CAP> --uefi-replace /path/to/UEFIReplace
    python patch_ptt.py <file.CAP> -o output.CAP

Requirements:
    - Python 3.x
    - UEFIReplace (from the UEFITool NE package) in PATH or passed via --uefi-replace
      Windows : UEFIReplace.exe
      Linux   : UEFIReplace (build from https://github.com/LongSoft/UEFITool)
      macOS   : UEFIReplace (build or use Homebrew)
"""

import sys
import os
import platform
import shutil
import subprocess
import tempfile
import argparse

SETUP_GUID   = "FE612B72-203C-47B1-8560-A66D946EB371"
SECTION_TYPE = "18"   # Freeform subtype GUID (0x18)
PTT_OFFSET   = 0x389
PTT_ENABLE   = 0x01
PTT_DISABLE  = 0x00

IS_WINDOWS = platform.system() == "Windows"
IS_MACOS   = platform.system() == "Darwin"
IS_LINUX   = platform.system() == "Linux"


def uefi_replace_candidates():
    if IS_WINDOWS:
        return ["UEFIReplace.exe", "UEFIReplace"]
    return ["UEFIReplace", "uefireplace"]


def _find_tool(name_candidates, tool_name, custom_path=None):
    if custom_path:
        if os.path.isfile(custom_path):
            if not IS_WINDOWS:
                os.chmod(custom_path, 0o755)
            return custom_path
        print(f"[ERROR] {tool_name} not found at: {custom_path}")
        sys.exit(1)

    for name in name_candidates:
        found = shutil.which(name)
        if found:
            return found

    script_dir = os.path.dirname(os.path.abspath(__file__))
    for name in name_candidates:
        local = os.path.join(script_dir, name)
        if os.path.isfile(local):
            if not IS_WINDOWS:
                os.chmod(local, 0o755)
            return local

    return None


def find_uefi_replace(custom_path=None):
    candidates = ["UEFIReplace.exe", "UEFIReplace"] if IS_WINDOWS else ["UEFIReplace", "uefireplace"]
    result = _find_tool(candidates, "UEFIReplace", custom_path)
    if result:
        return result

    print("[ERROR] UEFIReplace not found.")
    print()
    print("Download UEFITool 0.28 from: https://github.com/LongSoft/UEFITool/releases/tag/0.28.0")
    print("Extract UEFIReplace.exe into the same folder as this script.")
    sys.exit(1)


def find_uefi_extract(custom_path=None):
    candidates = ["UEFIExtract.exe", "UEFIExtract"] if IS_WINDOWS else ["UEFIExtract", "uefiextract"]
    result = _find_tool(candidates, "UEFIExtract", custom_path)
    if result:
        return result

    print("[ERROR] UEFIExtract not found.")
    print()
    print("Download UEFITool NE from: https://github.com/LongSoft/UEFITool/releases")
    if IS_WINDOWS:
        print("  Download UEFITool_NE_AXX_win64.zip and extract UEFIExtract.exe here.")
    elif IS_MACOS:
        print("  Download the mac zip and extract UEFIExtract here.")
    else:
        print("  Download the linux zip and extract UEFIExtract here.")
    sys.exit(1)


def run(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout, result.stderr, result.returncode


def find_extracted_bin(directory):
    bins = [f for f in os.listdir(directory) if f.endswith(".bin")]
    if bins:
        return os.path.join(directory, bins[0])
    return None




def patch_and_replace(cap_file, uefi_extract_path, uefi_replace_path, output_file):
    print(f"[*] OS detected   : {platform.system()} {platform.machine()}")
    print(f"[*] Input file    : {cap_file}")
    print(f"[*] Output file   : {output_file}")
    print(f"[*] UEFIExtract   : {uefi_extract_path}")
    print(f"[*] UEFIReplace   : {uefi_replace_path}")
    print()

    tmpdir       = tempfile.mkdtemp(prefix="ptt_patch_")
    body_orig    = os.path.join(tmpdir, "setupBody.bin")
    body_patched = os.path.join(tmpdir, "setupBody_patched.bin")

    try:

        print("[1/4] Extracting setupdata via UEFIExtract...")

        stdout, stderr, rc = run([
            uefi_extract_path, cap_file,
            SETUP_GUID, "-m", "body", "-t", SECTION_TYPE
        ])

        dump_dir = cap_file + ".dump"
        body_dump = None
        if os.path.isdir(dump_dir):
            for root, dirs, files in os.walk(dump_dir):
                for fname in files:
                    if fname == "body.bin":
                        body_dump = os.path.join(root, fname)
                        break
                if body_dump:
                    break

        if not body_dump or not os.path.isfile(body_dump):
            print("[ERROR] Failed to extract setupdata.")
            print("stdout:", stdout)
            print("stderr:", stderr)
            sys.exit(1)

        shutil.copy2(body_dump, body_orig)
        size = os.path.getsize(body_orig)
        print(f"      OK — {size} bytes extracted.")

        print("[2/4] Applying PTT patch...")
        with open(body_orig, "rb") as f:
            body = bytearray(f.read())

        if PTT_OFFSET >= len(body):
            print(f"[ERROR] Offset 0x{PTT_OFFSET:03X} is out of bounds (body size: {len(body)} bytes).")
            sys.exit(1)

        current_value = body[PTT_OFFSET]
        print(f"      Offset 0x{PTT_OFFSET:03X}: 0x{current_value:02X} → ", end="")

        if current_value == PTT_ENABLE:
            print("PTT is already enabled! No changes needed.")
        else:
            if current_value != PTT_DISABLE:
                print(f"\n[WARNING] Unexpected value: 0x{current_value:02X}")
                resp = input("      Continue anyway? [y/N]: ").strip().lower()
                if resp != "y":
                    print("Aborted.")
                    sys.exit(0)
            body[PTT_OFFSET] = PTT_ENABLE
            print(f"0x{PTT_ENABLE:02X} ✓")

        with open(body_patched, "wb") as f:
            f.write(body)

        print("[3/4] Re-injecting into CAP...")
        stdout, stderr, rc = run([
            uefi_replace_path, cap_file,
            SETUP_GUID, SECTION_TYPE,
            body_patched, "-o", output_file
        ])

        if not os.path.isfile(output_file):
            print("[ERROR] Failed to generate patched CAP.")
            print("stdout:", stdout)
            print("stderr:", stderr)
            sys.exit(1)

        # ── 4. Verify output ───────────────────────────────────────────────
        print("[4/4] Verifying output CAP...")
        sz_orig    = os.path.getsize(cap_file)
        sz_patched = os.path.getsize(output_file)
        print(f"      Original : {sz_orig:,} bytes")
        print(f"      Patched  : {sz_patched:,} bytes")

        if abs(sz_orig - sz_patched) > 1024:
            print("[WARNING] Unexpected size difference — verify the CAP before flashing!")
        else:
            print("      Size looks good ✓")

        print()
        print(f"✅  Patched CAP saved to: {output_file}")
        print()
        print("Next steps:")
        print("  1. Copy the CAP file to a FAT32 USB drive")
        print("  2. Enter BIOS (Del) → Tool → ASUS EZ Flash")
        print("  3. Select the file and confirm the flash")
        print("  4. After reboot: Advanced → PCH-FW Configuration → Firmware TPM")

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(
        description="Enable PTT/TPM 2.0 on the ASUS B150M Pro Gaming by patching the CAP file",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument("cap",
        help="Original ASUS CAP file")
    parser.add_argument("--uefi-extract", metavar="PATH",
        help="Path to UEFIExtract executable (optional if it is in PATH)",
        default=None)
    parser.add_argument("--uefi-replace", metavar="PATH",
        help="Path to UEFIReplace executable (optional if it is in PATH)",
        default=None)
    parser.add_argument("--output", "-o", metavar="OUTPUT.CAP",
        help="Output CAP file (default: <input>_PTT.CAP)",
        default=None)
    args = parser.parse_args()

    if not os.path.isfile(args.cap):
        print(f"[ERROR] File not found: {args.cap}")
        sys.exit(1)

    # Always resolve to absolute paths so native tools (e.g. UEFIReplace.exe)
    # can find the files regardless of how the script was invoked (Git Bash, CMD, etc.)
    cap_abs = os.path.abspath(args.cap)

    if args.output:
        output = os.path.abspath(args.output)
    else:
        base, ext = os.path.splitext(cap_abs)
        output = f"{base}_PTT{ext}"

    uefi_extract = find_uefi_extract(args.uefi_extract)
    uefi_replace = find_uefi_replace(args.uefi_replace)

    print("=" * 52)
    print("   PTT Enabler — ASUS B150M Pro Gaming")
    print("=" * 52)
    print()

    patch_and_replace(cap_abs, uefi_extract, uefi_replace, output)


if __name__ == "__main__":
    main()