#!/usr/bin/env python3
"""
UART File Transfer Tool - Sender Side
Sends files (typically ZIP archives) to a device via UART with CRC32 and MD5 verification.

Usage:
    python send_file_uart.py <file_path> [--port COM3] [--baudrate 38400]

Example:
    python send_file_uart.py firmware.zip --port COM3
"""

import serial
import time
import json
import base64
import hashlib
import zlib
import math
import sys
import os
from pathlib import Path
import argparse

# Configuration
BLOCK_SIZE = 650  # Bytes per block (before Base64 encoding, ~867 after, ensures JSON < 1000 bytes)
MAX_RETRIES = 3  # Maximum retries per block
TIMEOUT_SECONDS = 5  # Response timeout
CONSECUTIVE_ERRORS_LIMIT = 5  # Abort if this many consecutive errors

class UARTFileSender:
    def __init__(self, port, baudrate=38400, timeout=TIMEOUT_SECONDS):
        """Initialize UART connection"""
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.uart = None
        self.consecutive_errors = 0

    def connect(self):
        """Connect to UART port"""
        try:
            self.uart = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=self.timeout
            )
            self.uart.reset_input_buffer()
            self.uart.reset_output_buffer()
            time.sleep(1)
            print(f"✓ Connected to {self.port} at {self.baudrate} baud")
            return True
        except Exception as e:
            print(f"✗ Failed to connect to {self.port}: {e}")
            return False

    def disconnect(self):
        """Disconnect UART"""
        if self.uart:
            self.uart.close()
            print("✓ Disconnected")

    def send_command(self, cmd_dict):
        """Send JSON command via UART"""
        try:
            cmd_json = json.dumps(cmd_dict)
            self.uart.write((cmd_json + "\n").encode("utf-8"))
            self.uart.flush()
            return True
        except Exception as e:
            print(f"✗ Send error: {e}")
            return False

    def receive_response(self, timeout=None):
        """Receive JSON response from UART"""
        if timeout is None:
            timeout = self.timeout

        original_timeout = self.uart.timeout
        self.uart.timeout = timeout

        try:
            line = self.uart.readline()
            if line:
                response_str = line.decode("utf-8", "ignore").rstrip()
                try:
                    return json.loads(response_str)
                except json.JSONDecodeError:
                    print(f"✗ Invalid JSON response: {response_str}")
                    return None
            else:
                print("✗ Response timeout")
                return None
        except Exception as e:
            print(f"✗ Receive error: {e}")
            return None
        finally:
            self.uart.timeout = original_timeout

    def calculate_md5(self, file_path):
        """Calculate MD5 hash of file"""
        md5_hash = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                md5_hash.update(chunk)
        return md5_hash.hexdigest()

    def send_file(self, file_path):
        """Send file via UART with verification"""
        if not os.path.exists(file_path):
            print(f"✗ File not found: {file_path}")
            return False

        file_size = os.path.getsize(file_path)
        filename = os.path.basename(file_path)
        total_blocks = math.ceil(file_size / BLOCK_SIZE)

        print(f"\n{'='*60}")
        print(f"File Transfer Information")
        print(f"{'='*60}")
        print(f"File: {filename}")
        print(f"Size: {file_size:,} bytes ({file_size / 1024 / 1024:.2f} MB)")
        print(f"Blocks: {total_blocks}")
        print(f"Block size: {BLOCK_SIZE} bytes")
        print(f"{'='*60}\n")

        # Calculate MD5
        print("⏳ Calculating MD5 hash...")
        md5_hash = self.calculate_md5(file_path)
        print(f"✓ MD5: {md5_hash}\n")

        # Step 1: Send file_start command
        print("📤 Step 1: Initiating file transfer...")
        start_cmd = {
            "cmd": "file_start",
            "name": filename,
            "size": file_size,
            "blocks": total_blocks,
            "md5": md5_hash
        }

        if not self.send_command(start_cmd):
            return False

        response = self.receive_response(timeout=10)
        if not response:
            print("✗ No response to file_start command")
            return False

        if response.get("status") != "ready":
            print(f"✗ Device not ready: {response.get('reason', 'unknown')}")
            return False

        print(f"✓ Device ready\n")

        # Step 2: Send file blocks
        print("📤 Step 2: Transferring file blocks...")
        print(f"{'─'*60}")

        with open(file_path, "rb") as f:
            for block_index in range(total_blocks):
                # Read block data
                f.seek(block_index * BLOCK_SIZE)
                block_data = f.read(BLOCK_SIZE)

                # Calculate CRC32
                crc32_value = format(zlib.crc32(block_data) & 0xffffffff, '08x')

                # Base64 encode
                base64_data = base64.b64encode(block_data).decode('ascii')

                # Send block with retries
                success = False
                for retry in range(MAX_RETRIES):
                    block_cmd = {
                        "cmd": "file_block",
                        "index": block_index,
                        "crc32": crc32_value,
                        "data": base64_data
                    }

                    # Check JSON size to ensure it's under 1000 bytes
                    cmd_json = json.dumps(block_cmd)
                    json_size = len(cmd_json)
                    if json_size >= 1000:
                        print(f"  ⚠ WARNING: Block {block_index} JSON size is {json_size} bytes (>= 1000 bytes limit!)")
                        print(f"    Block data size: {len(block_data)} bytes")
                        print(f"    Base64 size: {len(base64_data)} bytes")

                    # Optional: Print size for first block as reference
                    if block_index == 0 and retry == 0:
                        print(f"  ℹ First block JSON size: {json_size} bytes (limit: 1000 bytes)")

                    if not self.send_command(block_cmd):
                        continue

                    response = self.receive_response()
                    if not response:
                        print(f"  ⚠ Block {block_index}: Timeout (retry {retry + 1}/{MAX_RETRIES})")
                        continue

                    if response.get("status") == "ok":
                        success = True
                        self.consecutive_errors = 0
                        break
                    else:
                        reason = response.get("reason", "unknown")
                        if response.get("retry"):
                            print(f"  ⚠ Block {block_index}: {reason} (retry {retry + 1}/{MAX_RETRIES})")
                        else:
                            print(f"  ✗ Block {block_index}: {reason} (not retryable)")
                            return False

                if not success:
                    print(f"✗ Failed to send block {block_index} after {MAX_RETRIES} retries")
                    self.consecutive_errors += 1
                    if self.consecutive_errors >= CONSECUTIVE_ERRORS_LIMIT:
                        print(f"✗ Too many consecutive errors ({self.consecutive_errors}), aborting")
                        return False
                    return False

                # Progress indicator
                progress = (block_index + 1) / total_blocks * 100
                blocks_sent = block_index + 1

                if blocks_sent % 50 == 0 or blocks_sent == total_blocks:
                    print(f"  Progress: {blocks_sent}/{total_blocks} blocks ({progress:.1f}%)")

        print(f"{'─'*60}")
        print(f"✓ All {total_blocks} blocks sent successfully\n")

        # Step 3: Send file_end command
        print("📤 Step 3: Finalizing transfer...")
        end_cmd = {
            "cmd": "file_end"
        }

        if not self.send_command(end_cmd):
            return False

        response = self.receive_response(timeout=30)  # MD5 calculation may take time
        if not response:
            print("✗ No response to file_end command")
            return False

        if response.get("status") == "success":
            print(f"✓ Transfer completed successfully!")
            print(f"  Path: {response.get('path')}")
            print(f"  Size: {response.get('size'):,} bytes")
            print(f"  MD5: {response.get('md5')}")
            return True
        else:
            reason = response.get("reason", "unknown")
            print(f"✗ Transfer failed: {reason}")
            if reason == "md5_mismatch":
                print(f"  Expected: {response.get('expected')}")
                print(f"  Actual: {response.get('actual')}")
            return False

    def cancel_transfer(self):
        """Cancel ongoing transfer"""
        print("\n⚠ Cancelling transfer...")
        cancel_cmd = {
            "cmd": "file_cancel"
        }
        self.send_command(cancel_cmd)
        response = self.receive_response()
        if response and response.get("status") == "cancelled":
            print("✓ Transfer cancelled")
        return True


def main():
    parser = argparse.ArgumentParser(
        description="Send files to device via UART with verification",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python send_file_uart.py firmware.zip
  python send_file_uart.py update.zip --port COM5 --baudrate 115200
  python send_file_uart.py data.zip --port /dev/ttyUSB0
        """
    )

    parser.add_argument("file", help="File to send (e.g., firmware.zip)")
    parser.add_argument("--port", default="COM3", help="UART port (default: COM3)")
    parser.add_argument("--baudrate", type=int, default=38400, help="Baud rate (default: 38400)")
    parser.add_argument("--timeout", type=int, default=5, help="Timeout in seconds (default: 5)")

    args = parser.parse_args()

    # Validate file
    if not os.path.exists(args.file):
        print(f"✗ Error: File not found: {args.file}")
        sys.exit(1)

    # Create sender
    sender = UARTFileSender(args.port, args.baudrate, args.timeout)

    try:
        # Connect
        if not sender.connect():
            sys.exit(1)

        # Send file
        print(f"\n🚀 Starting file transfer...\n")
        start_time = time.time()

        success = sender.send_file(args.file)

        elapsed_time = time.time() - start_time

        if success:
            print(f"\n{'='*60}")
            print(f"✓ File transfer completed successfully!")
            print(f"  Total time: {elapsed_time:.1f} seconds")
            file_size = os.path.getsize(args.file)
            throughput = file_size / elapsed_time / 1024
            print(f"  Throughput: {throughput:.1f} KB/s")
            print(f"{'='*60}\n")
            sys.exit(0)
        else:
            print(f"\n{'='*60}")
            print(f"✗ File transfer failed after {elapsed_time:.1f} seconds")
            print(f"{'='*60}\n")
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n\n⚠ Transfer interrupted by user")
        sender.cancel_transfer()
        sys.exit(1)

    finally:
        sender.disconnect()


if __name__ == "__main__":
    main()
