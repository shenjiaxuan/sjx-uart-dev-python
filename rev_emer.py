import base64
from PIL import Image
import io
import json
import serial
import time

class UART:
    def __init__(self, port="COM4", baudrate=38400):
        self.uartport = serial.Serial(
            port=port,
            baudrate=baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=0.1)

        self.uartport.reset_input_buffer()
        self.uartport.reset_output_buffer()
        time.sleep(1)

    def send_serial(self, cmd):
        cmd = str(cmd).rstrip()
        print(time.strftime("%B-%d-%Y %H:%M:%S") + f"  ->: {cmd}")
        self.uartport.write((cmd + "\n").encode("utf_8"))

    def receive_serial(self):
        return self.uartport.readline()

def fix_base64_padding(data):
    missing_padding = len(data) % 4
    if missing_padding != 0:
        data += '=' * (4 - missing_padding)
    return data

def save_image(image_data_base64, filename):
    image_binary = base64.b64decode(image_data_base64)
    image = Image.open(io.BytesIO(image_binary))
    image.save(filename, format='BMP')
    print(f"Saved image to {filename}")

def main():
    uart = UART()

    while True:
        # Query EmergencyMode
        uart.send_serial("REACT|")
        time.sleep(0.5)

        emer_mode = None
        response = uart.receive_serial()
        if response:
            response_str = response.decode("utf-8", "ignore").strip()
            print(time.strftime("%B-%d-%Y %H:%M:%S") + f"  <-: {response_str}")
            try:
                response_json = json.loads(response_str)
                if "EmergencyMode" in response_json:
                    emer_mode = int(response_json["EmergencyMode"])
            except json.JSONDecodeError:
                pass

        if emer_mode is None:
            print("No EmergencyMode response, retry in 5s")
            time.sleep(5)
            continue

        if emer_mode == 1:
            print("EmergencyMode is 1, start receiving image blocks ?PS1-?PS30")
            image_blocks = []
            
            for block_num in range(5, 25):
                cmd = f"?PS{block_num}"
                uart.send_serial(cmd)
                time.sleep(0.5)
                
                response = uart.receive_serial()
                if not response:
                    continue
                    
                response_str = response.decode("utf-8", "ignore").strip()
                print(time.strftime("%B-%d-%Y %H:%M:%S") + f"  <-: {response_str}")

                try:
                    resp_json = json.loads(response_str)
                    block_key = f"Block{block_num - 4}"
                    if block_key in resp_json:
                        block_data = resp_json[block_key]
                        image_blocks.append(block_data)
                except json.JSONDecodeError:
                    pass

            if len(image_blocks) == 20:
                print("All 20 image blocks received, assembling image...")
                full_base64 = ''.join(image_blocks)
                full_base64 = fix_base64_padding(full_base64)
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                save_image(full_base64, f"emerg_mode_image_{timestamp}.bmp")
            else:
                print(f"Received {len(image_blocks)} blocks, incomplete image.")

            time.sleep(2)

        else:
            print("EmergencyMode is 0, wait 5 seconds before next query.")
            time.sleep(5)

if __name__ == '__main__':
    main()
