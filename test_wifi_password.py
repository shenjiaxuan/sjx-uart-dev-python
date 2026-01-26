"""
WiFi Password Control Test Script
Test WiFi password setting via UART by sending WFPW|xxxx command
"""

import serial
import base64
import json
import time


def encode_password(password: str) -> str:
    """Encode password to Base64"""
    return base64.b64encode(password.encode('utf-8')).decode('utf-8')


def decode_password(encoded_password: str) -> str:
    """Decode Base64 encoded password"""
    return base64.b64decode(encoded_password.encode('utf-8')).decode('utf-8')


def test_wifi_password(port: str, baudrate: int, password: str = None, timeout: float = 5.0) -> bool:
    """
    Test WiFi password setting/query function

    Args:
        port: Serial port number, e.g., 'COM10'
        baudrate: Baud rate
        password: WiFi password to set (plaintext), if None then query current password
        timeout: Timeout for waiting response (seconds)

    Returns:
        bool: Whether the test passed
    """
    # Determine whether to set or query password
    if password:
        # Set password mode
        encoded_password = encode_password(password)
        command = f"WFPW|{encoded_password}\r\n"
        print(f"[INFO] Mode: Set password")
        print(f"[INFO] Original password: {password}")
        print(f"[INFO] Base64 encoded: {encoded_password}")
    else:
        # Query password mode
        command = "WFPW|\r\n"
        print(f"[INFO] Mode: Query password")

    print(f"[INFO] Sending command: {command.strip()}")

    try:
        # Open serial port
        ser = serial.Serial(
            port=port,
            baudrate=baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=timeout
        )

        print(f"[INFO] Serial port {port} opened, baudrate: {baudrate}")

        # Clear buffers
        ser.reset_input_buffer()
        ser.reset_output_buffer()

        # Send command
        ser.write(command.encode('utf-8'))
        print("[INFO] Command sent, waiting for response...")

        # Wait and read response
        start_time = time.time()
        response_data = b""

        while time.time() - start_time < timeout:
            if ser.in_waiting > 0:
                response_data += ser.read(ser.in_waiting)
                # Check if complete JSON response is received
                try:
                    response_str = response_data.decode('utf-8').strip()
                    if response_str.startswith('{') and response_str.endswith('}'):
                        break
                except:
                    pass
            time.sleep(0.1)

        ser.close()

        if not response_data:
            print("[FAIL] No response received")
            return False

        response_str = response_data.decode('utf-8').strip()
        print(f"[INFO] Response received: {response_str}")

        # Parse JSON response
        try:
            response_json = json.loads(response_str)
        except json.JSONDecodeError as e:
            print(f"[FAIL] JSON parsing failed: {e}")
            return False

        # Check Password field
        if "Password" not in response_json:
            print("[FAIL] Password field missing in response")
            return False

        received_password = response_json["Password"]

        # Check if empty (indicates failure)
        if not received_password:
            print("[FAIL] Returned password is empty, operation failed")
            return False

        # Decode returned password
        try:
            decoded_received = decode_password(received_password)
            print(f"[INFO] Returned password (Base64): {received_password}")
            print(f"[INFO] Returned password (decoded): {decoded_received}")

            if password:
                # Set password mode: verify returned password matches the one set
                if decoded_received == password:
                    print("[PASS] Password set successfully, verification passed!")
                    return True
                else:
                    print(f"[FAIL] Password mismatch! Expected: {password}, Actual: {decoded_received}")
                    return False
            else:
                # Query password mode: directly print password
                print(f"[PASS] Current WiFi password: {decoded_received}")
                return True
        except Exception as e:
            print(f"[FAIL] Failed to decode returned password: {e}")
            return False

    except serial.SerialException as e:
        print(f"[ERROR] Serial port error: {e}")
        return False
    except Exception as e:
        print(f"[ERROR] Exception occurred: {e}")
        return False


def main():
    import argparse

    parser = argparse.ArgumentParser(description="WiFi Password Control Test")
    parser.add_argument("password", nargs="?", default=None, help="WiFi password to set (plaintext), if not provided then query current password")
    parser.add_argument("-p", "--port", default="COM10", help="Serial port number (default: COM10)")
    parser.add_argument("-b", "--baudrate", type=int, default=38400, help="Baud rate (default: 38400)")
    parser.add_argument("-t", "--timeout", type=float, default=5.0, help="Timeout in seconds (default: 5.0)")

    args = parser.parse_args()

    print("=" * 50)
    print("WiFi Password Control Test")
    print("=" * 50)
    print(f"Serial Port: {args.port}")
    print(f"Baud Rate: {args.baudrate}")
    if args.password:
        print(f"Operation: Set password -> {args.password}")
    else:
        print(f"Operation: Query password")
    print("=" * 50)

    result = test_wifi_password(args.port, args.baudrate, args.password, args.timeout)

    if result:
        print("\n[Result] Operation successful!")
    else:
        print("\n[Result] Operation failed!")


if __name__ == "__main__":
    main()
