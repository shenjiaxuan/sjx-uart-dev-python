import os
import base64
from PIL import Image
import io
import json
import re
import serial
import time

TEST_RUN_COUNT = 1
send_max_length = 980
# max_image_blocks = 80  # 预设最大值，实际以空块判断为准

class UART:
    def __init__(self):
        self.uartport = serial.Serial(
                port="COM3",
                baudrate=38400, # 115200
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
    try:
        data = json.loads(response_str)
        for key, value in data.items():
            if isinstance(value, str):
                return value
    except json.JSONDecodeError:
        print("Error decoding JSON:", response_str)
    return None

if __name__ == '__main__':
    # Delete recv_test.json file if it exists
    if os.path.exists("recv_test.json"):
        os.remove("recv_test.json")
        print("Deleted recv_test.json")

    commands = [
        "?Asset",
        "@|600",
        "@|",
        "?Order",
        # "Profile|3",
        "Profile|",
        "WiFi|1",
        "WiFi|",
        "?ERR",
        # "REACT|1",
        "REACT|",
        "BLK|20",      # 设置图像块数量
        "?OBdata",
        "?PS1",
        "?PS2",
        "?PS3",
        "?PS4"
        # ?PS5 开始的图像块将动态请求
    ]

    uart = UART()

    for run in range(TEST_RUN_COUNT):
        print(f"Running test iteration {run + 1}/{TEST_RUN_COUNT}")
        image_data_list = []

        for command in commands:
            uart.send_serial(command)
            time.sleep(0.5)
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
                        if command == "?OBdata":
                            time.sleep(2) # delay for esp32 image processing
                else:
                    break

        # 动态请求图像块（?PS5 开始），直到收到空块
        print("开始动态请求图像块...")
        image_block_start_time = time.time()
        total_sleep_time = 0  # 累计 sleep 时间
        ps_index = 5
        max_attempts = 100  # 安全上限，防止无限循环
        while ps_index < max_attempts:
            command = f"?PS{ps_index}"
            uart.send_serial(command)
            sleep_duration = 0.5
            time.sleep(sleep_duration)
            total_sleep_time += sleep_duration

            response_received = False
            while True:
                response = uart.receive_serial()
                if response:
                    response_str = response.decode("utf_8", "ignore").rstrip()
                    print(time.strftime("%B-%d-%Y %H:%M:%S") + "  <-: {0}".format(response_str))
                    response_received = True

                    if response_str.startswith('{"Block'):
                        try:
                            json_data = json.loads(response_str)
                            block_key = f"Block{ps_index - 4}"

                            # 检查是否是空块
                            if block_key in json_data:
                                if json_data[block_key] == "":
                                    image_block_end_time = time.time()
                                    total_elapsed = image_block_end_time - image_block_start_time
                                    actual_processing_time = total_elapsed - total_sleep_time
                                    print(f"收到空块 {block_key}，图像读取完成，共接收 {ps_index - 5} 个图像块")
                                    print(f"图像块接收统计：总耗时 {total_elapsed:.2f}秒，纯处理时间 {actual_processing_time:.2f}秒")
                                    ps_index = max_attempts  # 退出外层循环
                                    break
                                else:
                                    # 有数据，添加到列表
                                    image_data_list.append(json_data[block_key])
                                    append_response_to_file(command, {"image_data_received": True})
                                    ps_index += 1
                                    break
                        except json.JSONDecodeError:
                            print(f"Failed to decode JSON for {command}")
                            break
                    else:
                        break
                else:
                    break

            # 如果没有收到响应，停止请求
            if not response_received:
                image_block_end_time = time.time()
                total_elapsed = image_block_end_time - image_block_start_time
                actual_processing_time = total_elapsed - total_sleep_time
                print(f"未收到 {command} 的响应，停止请求")
                print(f"图像块接收统计：总耗时 {total_elapsed:.2f}秒，纯处理时间 {actual_processing_time:.2f}秒")
                break

        if image_data_list:
            combined_image_data = ''.join(image_data_list)
            combined_image_data = fix_base64_padding(combined_image_data)
            save_image(combined_image_data, f"combined_image_{run + 1}.bmp")

        time.sleep(1)
