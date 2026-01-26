#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tapconet Protocol Test Tool
Send commands to ESP32-P4 device and receive/parse responses
"""

import serial
import time
import sys
import argparse
from typing import Optional, Dict

# #------------------  Protocol Constants  ------------------

# Group definition
TAPCONET_GROUP_READ = 0x01

# Command ID definition
TAPCONET_CMD_ALARM = 0x01      # Query alarm status
TAPCONET_CMD_PEOPLE = 0x02     # Query people count increment
TAPCONET_CMD_PROTECT = 0x03    # Query property protection

# Command name mapping
CMD_NAMES = {
    TAPCONET_CMD_ALARM: "ALARM",
    TAPCONET_CMD_PEOPLE: "PEOPLE",
    TAPCONET_CMD_PROTECT: "PROTECT"
}

# Packet length
PACKET_LENGTH = 5

# #------------------  Protocol Handler Class  ------------------

class TapconetProtocol:
    """Tapconet protocol encoding/decoding handler"""

    def __init__(self, port: str, baudrate: int = 38400, timeout: float = 0.2):
        """
        Initialize serial connection

        Args:
            port: Serial port (e.g. COM10 or /dev/ttyUSB0)
            baudrate: Baud rate (default 38400)
            timeout: Timeout in seconds (default 0.2)
        """
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.ser = None

    def connect(self) -> bool:
        """Connect to serial port"""
        try:
            self.ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=self.timeout
            )
            # Clear buffers
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
            return True
        except serial.SerialException as e:
            print(f"✗ Serial connection failed: {e}")
            print(f"  Please check:")
            print(f"  - Port name is correct ({self.port})")
            print(f"  - Device is connected")
            print(f"  - Port is not occupied by other programs")
            return False

    def calculate_checksum(self, group: int, subgroup: int, value: int) -> int:
        """
        Calculate checksum

        Args:
            group: Group field
            subgroup: Subgroup field
            value: 16-bit value

        Returns:
            Checksum (8-bit)
        """
        value_h = (value >> 8) & 0xFF  # High byte
        value_l = value & 0xFF          # Low byte
        return (group + subgroup + value_h + value_l) & 0xFF

    def pack_request(self, subgroup: int, value: int = 0) -> bytes:
        """
        Pack request packet

        Args:
            subgroup: Command ID
            value: 16-bit value (default 0)

        Returns:
            5-byte packet
        """
        group = TAPCONET_GROUP_READ
        value_h = (value >> 8) & 0xFF
        value_l = value & 0xFF
        checksum = self.calculate_checksum(group, subgroup, value)

        return bytes([group, subgroup, value_h, value_l, checksum])

    def parse_response(self, data: bytes) -> Optional[Dict]:
        """
        Parse response packet

        Args:
            data: 5-byte response data

        Returns:
            Parsed result dict, None if parsing fails
            {
                'valid': True/False,
                'group': int,
                'subgroup': int,
                'value': int,
                'checksum': int,
                'expected_checksum': int,
                'error': str (optional)
            }
        """
        if len(data) != PACKET_LENGTH:
            return {
                'valid': False,
                'error': f'Invalid packet length (expected {PACKET_LENGTH} bytes, got {len(data)} bytes)'
            }

        group = data[0]
        subgroup = data[1]
        value = (data[2] << 8) | data[3]  # Big-endian
        checksum = data[4]

        # Verify checksum
        expected_checksum = self.calculate_checksum(group, subgroup, value)

        result = {
            'valid': checksum == expected_checksum,
            'group': group,
            'subgroup': subgroup,
            'value': value,
            'checksum': checksum,
            'expected_checksum': expected_checksum
        }

        if not result['valid']:
            result['error'] = f'Checksum mismatch (expected 0x{expected_checksum:02X}, got 0x{checksum:02X})'

        return result

    def send_command(self, subgroup: int, value: int = 0) -> Optional[Dict]:
        """
        Send command and wait for response

        Args:
            subgroup: Command ID
            value: 16-bit value (default 0)

        Returns:
            Response parse result, None if timeout
        """
        if not self.ser or not self.ser.is_open:
            print("✗ Error: Serial port not connected")
            return None

        # Pack and send request
        request = self.pack_request(subgroup, value)

        cmd_name = CMD_NAMES.get(subgroup, f"UNKNOWN(0x{subgroup:02X})")
        print(f"\n→ Send command: {cmd_name}")
        print(f"  Raw data: {' '.join(f'{b:02X}' for b in request)}")
        print(f"  Checksum: 0x{request[4]:02X} ✓")

        # Clear receive buffer
        self.ser.reset_input_buffer()

        # Send data
        start_time = time.time()
        self.ser.write(request)

        # Wait for response
        response = self.ser.read(PACKET_LENGTH)
        elapsed_ms = (time.time() - start_time) * 1000

        if len(response) == 0:
            print(f"✗ Error: Response timeout ({int(self.timeout * 1000)}ms)")
            print(f"  No response from device, please check:")
            print(f"  - Serial connection is OK")
            print(f"  - Device is running")
            print(f"  - Baud rate matches ({self.baudrate} bps)")
            return None

        # Parse response
        result = self.parse_response(response)

        print(f"← Receive response (elapsed: {int(elapsed_ms)}ms)")
        print(f"  Raw data: {' '.join(f'{b:02X}' for b in response)}")

        if result and result['valid']:
            print(f"  Parse result:")
            print(f"    - Group: 0x{result['group']:02X} (READ)")
            print(f"    - Subgroup: 0x{result['subgroup']:02X} ({CMD_NAMES.get(result['subgroup'], 'UNKNOWN')})")
            print(f"    - Value: 0x{result['value']:04X} ({result['value']})")
            print(f"    - Checksum: 0x{result['checksum']:02X} ✓")
        else:
            print(f"✗ Parse error: {result.get('error', 'Unknown error') if result else 'No response data'}")

        return result

    def close(self):
        """Close serial connection"""
        if self.ser and self.ser.is_open:
            self.ser.close()
            print("\nSerial port closed")

# #------------------  Tester Class  ------------------

class TapconetTester:
    """Tapconet tester interface"""

    def __init__(self, protocol: TapconetProtocol):
        """Initialize tester"""
        self.protocol = protocol

    def query_alarm(self) -> Optional[int]:
        """
        Query alarm status

        Returns:
            0=no person, 1=person detected, None=query failed
        """
        result = self.protocol.send_command(TAPCONET_CMD_ALARM)

        if result and result['valid']:
            alarm_status = result['value']
            if alarm_status == 0:
                print(f"  Status: No person ✓")
            elif alarm_status == 1:
                print(f"  Status: Person detected 🚨")
            else:
                print(f"  Status: Unknown value ({alarm_status})")
            return alarm_status

        return None

    def query_people(self) -> Optional[int]:
        """
        Query people count increment

        Returns:
            Increment value, None=query failed
        """
        result = self.protocol.send_command(TAPCONET_CMD_PEOPLE)

        if result and result['valid']:
            delta = result['value']
            print(f"  People increment: {delta}")
            return delta

        return None

    def query_protect(self) -> Optional[int]:
        """
        Query property protection

        Returns:
            Protection status value, None=query failed
        """
        result = self.protocol.send_command(TAPCONET_CMD_PROTECT)

        if result and result['valid']:
            protect_status = result['value']
            print(f"  Property protection: 0x{protect_status:04X}")
            return protect_status

        return None

    def continuous_monitor(self, interval: float = 1.0, duration: float = 60.0):
        """
        Continuous monitoring mode

        Args:
            interval: Query interval in seconds
            duration: Duration in seconds
        """
        print(f"\nStart continuous monitoring (Press Ctrl+C to stop)")
        print(f"Interval: {interval}s | Duration: {duration}s")
        print("=" * 50)

        start_time = time.time()

        try:
            while True:
                elapsed = time.time() - start_time

                if elapsed >= duration:
                    print(f"\nMonitoring ended (ran for {int(elapsed)}s)")
                    break

                # Query alarm and people count
                alarm_result = self.protocol.send_command(TAPCONET_CMD_ALARM)
                people_result = self.protocol.send_command(TAPCONET_CMD_PEOPLE)

                alarm_str = "Unknown"
                people_str = "Unknown"

                if alarm_result and alarm_result['valid']:
                    alarm_str = "Person" if alarm_result['value'] == 1 else "No person"

                if people_result and people_result['valid']:
                    people_str = str(people_result['value'])

                print(f"[{int(elapsed):05d}s] ALARM={alarm_str} | PEOPLE={people_str}")

                time.sleep(interval)

        except KeyboardInterrupt:
            print(f"\n\nMonitoring stopped (ran for {int(time.time() - start_time)}s)")

# #------------------  Interactive Menu  ------------------

def print_menu(port: str, baudrate: int, connected: bool):
    """Print interactive menu"""
    print("\n" + "=" * 50)
    print("    Tapconet Protocol Test Tool")
    print("=" * 50)
    print(f"Current connection: {port} @ {baudrate} bps")
    print(f"Connection status: {'Connected ✓' if connected else 'Disconnected ✗'}")
    print("\nSelect test command:")
    print("  1. Query alarm status (ALARM)")
    print("  2. Query people count increment (PEOPLE)")
    print("  3. Query property protection (PROTECT)")
    print("  4. Continuous monitoring mode")
    print("  5. Send raw packet (Advanced debug)")
    print("  0. Exit")
    print()

def handle_user_input(tester: TapconetTester, protocol: TapconetProtocol):
    """Handle user input"""
    choice = input("Enter option [0-5]: ").strip()

    if choice == '1':
        tester.query_alarm()

    elif choice == '2':
        tester.query_people()

    elif choice == '3':
        tester.query_protect()

    elif choice == '4':
        try:
            interval_str = input("Enter interval(seconds) [default 1.0]: ").strip()
            interval = float(interval_str) if interval_str else 1.0

            duration_str = input("Enter duration(seconds) [default 60]: ").strip()
            duration = float(duration_str) if duration_str else 60.0

            tester.continuous_monitor(interval, duration)
        except ValueError:
            print("✗ Invalid input format, please enter a number")

    elif choice == '5':
        try:
            hex_input = input("Enter 5 bytes (hex, space separated): ").strip()
            bytes_list = [int(b, 16) for b in hex_input.split()]

            if len(bytes_list) != PACKET_LENGTH:
                print(f"✗ Error: Need {PACKET_LENGTH} bytes")
                return

            raw_data = bytes(bytes_list)
            print(f"\n→ Send raw data: {' '.join(f'{b:02X}' for b in raw_data)}")

            # Clear buffer and send
            protocol.ser.reset_input_buffer()
            protocol.ser.write(raw_data)

            # Receive response
            response = protocol.ser.read(PACKET_LENGTH)

            if len(response) > 0:
                result = protocol.parse_response(response)
                print(f"← Receive response:")
                print(f"  Raw data: {' '.join(f'{b:02X}' for b in response)}")

                if result and result['valid']:
                    cmd_name = CMD_NAMES.get(result['subgroup'], 'UNKNOWN')
                    print(f"  Parse: {cmd_name} = 0x{result['value']:04X} ({result['value']})")
                else:
                    print(f"  ✗ Parse failed: {result.get('error', 'Unknown error') if result else 'No data'}")
            else:
                print("✗ No response received")

        except ValueError:
            print("✗ Invalid input format, please enter hex digits (e.g.: 01 01 00 00 02)")

    elif choice == '0':
        return False

    else:
        print("✗ Invalid option, please try again")

    return True

# #------------------  Main Function  ------------------

def main():
    """Main function"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Tapconet Protocol Test Tool')
    parser.add_argument('--port', default='COM10', help='Serial port (default: COM10)')
    parser.add_argument('--baudrate', type=int, default=38400, help='Baud rate (default: 38400)')
    parser.add_argument('--timeout', type=float, default=0.2, help='Response timeout in seconds (default: 0.2)')

    args = parser.parse_args()

    # Create protocol handler object
    protocol = TapconetProtocol(args.port, args.baudrate, args.timeout)

    # Connect to serial port
    if not protocol.connect():
        return 1

    print(f"✓ Serial connection successful: {args.port} @ {args.baudrate} bps")

    # Create tester
    tester = TapconetTester(protocol)

    # Interactive menu loop
    try:
        while True:
            print_menu(args.port, args.baudrate, protocol.ser.is_open)

            if not handle_user_input(tester, protocol):
                break

    except KeyboardInterrupt:
        print("\n\nInterrupted, exiting...")

    finally:
        protocol.close()

    return 0

# #------------------  Entry Point  ------------------

if __name__ == "__main__":
    sys.exit(main())
