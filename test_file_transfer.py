#!/usr/bin/env python3
"""
Test script for file transfer functionality
Creates a test ZIP file and sends it via UART
"""

import os
import zipfile
import tempfile
import random
import string

def create_test_zip(size_kb=10):
    """Create a test ZIP file with random content"""
    # Create temporary directory
    temp_dir = tempfile.mkdtemp()

    # Create some test files
    files = []
    for i in range(3):
        filename = os.path.join(temp_dir, f"test_file_{i}.txt")
        with open(filename, 'w') as f:
            # Write random content
            content_size = (size_kb * 1024) // 3
            content = ''.join(random.choices(string.ascii_letters + string.digits, k=content_size))
            f.write(content)
        files.append(filename)

    # Create ZIP file
    zip_path = os.path.join(os.getcwd(), f"test_{size_kb}kb.zip")
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file in files:
            zipf.write(file, os.path.basename(file))

    # Cleanup temp files
    for file in files:
        os.remove(file)
    os.rmdir(temp_dir)

    actual_size = os.path.getsize(zip_path)
    print(f"✓ Created test ZIP: {zip_path}")
    print(f"  Size: {actual_size:,} bytes ({actual_size/1024:.1f} KB)")

    return zip_path

def main():
    print("="*60)
    print("File Transfer Test Script")
    print("="*60)
    print()

    # Ask user for test file size
    print("Select test file size:")
    print("  1. Small (10 KB) - ~15 blocks, ~30 seconds")
    print("  2. Medium (100 KB) - ~140 blocks, ~2 minutes")
    print("  3. Large (500 KB) - ~680 blocks, ~5 minutes")
    print("  4. Custom size")

    choice = input("\nEnter choice (1-4): ").strip()

    size_map = {
        '1': 10,
        '2': 100,
        '3': 500
    }

    if choice in size_map:
        size_kb = size_map[choice]
    elif choice == '4':
        size_kb = int(input("Enter size in KB: "))
    else:
        print("Invalid choice, using 10 KB")
        size_kb = 10

    print()
    print(f"Creating {size_kb} KB test file...")
    zip_path = create_test_zip(size_kb)

    print()
    print("Test file created successfully!")
    print()
    print("Next steps:")
    print("─"*60)
    print("1. Ensure uart_control.py is running on the device")
    print("2. Run the following command to send the file:")
    print()
    print(f"   python send_file_uart.py {zip_path} --port COM3")
    print()
    print("   (Replace COM3 with your actual port)")
    print("─"*60)
    print()

    # Ask if user wants to send now
    send_now = input("Send file now? (y/n): ").strip().lower()

    if send_now == 'y':
        port = input("Enter UART port (default: COM3): ").strip() or "COM3"

        print()
        print("Attempting to send file...")
        print()

        import subprocess
        try:
            cmd = [
                "python",
                "send_file_uart.py",
                zip_path,
                "--port",
                port
            ]
            subprocess.run(cmd)
        except KeyboardInterrupt:
            print("\n\nTransfer cancelled by user")
        except Exception as e:
            print(f"\nError: {e}")
    else:
        print("Test file ready for manual transfer.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nTest cancelled by user")
    except Exception as e:
        print(f"\nError: {e}")
