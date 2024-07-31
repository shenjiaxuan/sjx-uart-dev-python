import os
import base64
from PIL import Image
import io
import json
import re
import serial
import time

class UART:
    def __init__(self):
        self.uartport = serial.Serial(
                port="COM18",
                baudrate=38400,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.1)

        self.uartport.reset_input_buffer()
        self.uartport.reset_output_buffer()
        time.sleep(1)

    def send_serial(self, cmd): 
        cmd = str(cmd).rstrip()
        print(time.strftime("%B-%d-%Y %H:%M:%S") + "  ->: {0}".format(cmd))
        self.uartport.write((cmd + "\n").encode("utf_8"))

    def receive_serial(self):
        rcvdata = self.uartport.readline()
        return rcvdata

def append_response_to_file(command, response):
    filename = "recv_test.json"
    try:
        with open(filename, 'r') as file:
            data = json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}

    if command in data:
        if isinstance(data[command], list):
            data[command].append(response)
        else:
            data[command] = [data[command], response]
    else:
        data[command] = [response]

    with open(filename, 'w') as file:
        json.dump(data, file, indent=4)
    print(f"Appended response to {filename}")

def save_image(image_data, filename):
    image_binary = base64.b64decode(image_data)
    image = Image.open(io.BytesIO(image_binary))
    image.save(filename, format='BMP')
    print(f"Saved image to {filename}")

def fix_base64_padding(data):
    missing_padding = len(data) % 4
    if missing_padding != 0:
        data += '=' * (4 - missing_padding)
    return data

def extract_base64_data(response_str):
    match = re.search(r'\{"Block\d+:([^}]+)\}', response_str)
    if match:
        return match.group(1)
    return None

if __name__ == '__main__':
    # Delete recv_test.json file if it exists
    if os.path.exists("recv_test.json"):
        os.remove("recv_test.json")
        print("Deleted recv_test.json")

    commands = [
        "?Asset",
        "@|300",
        "?Order",
        "Profile|1",
        "WiFi|1",
        "?ERR",
        "REACT|1",
        "?OBdata",
        "?PS1",
        "?PS2",
        "?PS3",
        "?PS4",
        "?PS5",
        "?PS6",
        "?PS7",
        "?PS8",
        "?PS9",
        "?PS10",
        "?PS11",
        "?PS12",
        "?PS13",
        "?PS14",
        "?PS15",
        "?PS16",
        "?PS17",
        "?PS18",
        "?PS19",
        "?PS20",
        "?PS21",
        "?PS22",
        "?PS23",
        "?PS24"
    ]

    uart = UART()

    image_data_list = []

    for command in commands:
        uart.send_serial(command)
        while True:
            response = uart.receive_serial()
            if response:
                response_str = response.decode("utf_8", "ignore").rstrip()
                print(time.strftime("%B-%d-%Y %H:%M:%S") + "  <-: {0}".format(response_str))

                if response_str.startswith('{"Block'):
                    base64_data = extract_base64_data(response_str)
                    if base64_data:
                        image_data_list.append(base64_data)
                    append_response_to_file(command, {"image_data_received": True})
                else:
                    try:
                        response_json = json.loads(response_str)
                        append_response_to_file(command, response_json)
                    except json.JSONDecodeError:
                        print(f"Failed to decode JSON for command: {command}")
            else:
                break

    if image_data_list:
        combined_image_data = ''.join(image_data_list)
        combined_image_data = fix_base64_padding(combined_image_data)
        save_image(combined_image_data, "combined_image.bmp")

    time.sleep(1)