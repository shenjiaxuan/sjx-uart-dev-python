import os
import base64
import cv2
import numpy as np
import serial
import time

class UART:
    def __init__(self):
        self.uartport = serial.Serial(
                port="COM4",
                baudrate=115200,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=1)

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

def fix_base64_padding(data):
    missing_padding = len(data) % 4
    if missing_padding != 0:
        data += '=' * (4 - missing_padding)
    return data

def display_image(base64_data):
    try:
        print("Decoding Base64 data...")
        image_data = base64.b64decode(base64_data)
        
        print("Converting to NumPy array...")
        nparr = np.frombuffer(image_data, np.uint8).reshape((480, 480, 3))
        image_bgr = cv2.cvtColor(nparr, cv2.COLOR_BGR2RGB)
        # print("Decoding image using OpenCV...")
        # img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        # if img is None:
        #     print("Failed to decode image. Please ensure Base64 data is correct.")
        #     return

        # 保存图像到文件
        print("Saving image to tmp.bmp...")
        cv2.imwrite('tmp.bmp', image_bgr)

        print("Displaying image...")
        cv2.imshow('Received Image', image_bgr)
        cv2.waitKey(0)
        cv2.destroyAllWindows()
    except Exception as e:
        print(f"An error occurred while displaying the image: {e}")


def receive_image_data(uart):
    base64_output = ""
    receiving = False
    
    while True:
        response = uart.receive_serial()
        if not response:
            print("No response received.")
            continue
        
        response_str = response.decode("utf_8", "ignore").strip()
        # print(time.strftime("%B-%d-%Y %H:%M:%S") + "  <-: {0}".format(response_str))
        
        if response_str == "START":
            receiving = True
            print("Started receiving image data")
            continue
        
        if response_str == "END":
            receiving = False
            print("Finished receiving image data")
            break
        
        if receiving:
            base64_output += response_str
            print(f"Received image data. Length: {len(response_str)}")
    
    print(f"Received image data. Length: {len(base64_output)}")
    return base64_output

def save_image_to_file(image_data, file_path='tmp.bmp'):
    try:
        print("Saving decoded image data to file...")
        with open(file_path, 'wb') as f:
            f.write(image_data)
        print(f"Image successfully saved to {file_path}")
    except Exception as e:
        print(f"An error occurred while saving the image: {e}")
        
if __name__ == '__main__':
    uart = UART()

    # 发送 ?PS3 命令
    uart.send_serial("?PS3")
    # time.sleep(1)

    # 接收图像数据
    base64_output = receive_image_data(uart)

    # 检查接收到的 base64 数据
    if base64_output:
        print("Received Base64 data. Length:", len(base64_output))
        base64_output = fix_base64_padding(base64_output)
        try:
            # 检查 base64 是否解码成功
            decoded_data = base64.b64decode(base64_output)
            print("Base64 decoded data length:", len(decoded_data))
            # 保存解码后的数据到文件
            save_image_to_file(decoded_data, 'tmp.jpg')
        except Exception as e:
            print(f"Base64 decoding failed: {e}")
        
        # 显示图像
        display_image(base64_output)
    else:
        print("No image data received.")
