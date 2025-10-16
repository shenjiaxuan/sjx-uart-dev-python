import os
import base64
from PIL import Image
import io
import json
import re
import serial
import time
import logging
from datetime import datetime

class UART:
    def __init__(self):
        self.uartport = serial.Serial(
                port="COM3",
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

def setup_logging():
    """设置日志记录"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('uart_test.log', encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

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

def validate_image(image_data, logger):
    """校验图片是否正常"""
    try:
        # 检查base64数据是否为空
        if not image_data:
            logger.error("图片校验失败：base64数据为空")
            return False, "base64数据为空"
        
        # 尝试解码base64
        try:
            image_binary = base64.b64decode(image_data)
        except Exception as e:
            logger.error(f"图片校验失败：base64解码错误 - {str(e)}")
            return False, f"base64解码错误: {str(e)}"
        
        # 检查解码后的数据大小
        if len(image_binary) == 0:
            logger.error("图片校验失败：解码后数据为空")
            return False, "解码后数据为空"
        
        # 尝试打开为PIL图片
        try:
            image = Image.open(io.BytesIO(image_binary))
            width, height = image.size
            format_type = image.format
        except Exception as e:
            logger.error(f"图片校验失败：PIL打开图片错误 - {str(e)}")
            return False, f"PIL打开图片错误: {str(e)}"
        
        # 检查图片尺寸是否合理（假设最小10x10，最大10000x10000）
        if width < 10 or height < 10:
            logger.error(f"图片校验失败：图片尺寸过小 ({width}x{height})")
            return False, f"图片尺寸过小: {width}x{height}"
        
        if width > 10000 or height > 10000:
            logger.error(f"图片校验失败：图片尺寸过大 ({width}x{height})")
            return False, f"图片尺寸过大: {width}x{height}"
        
        # 检查文件大小是否合理（假设最小1KB，最大50MB）
        data_size = len(image_binary)
        if data_size < 1024:  # 小于1KB
            logger.warning(f"图片校验警告：文件大小较小 ({data_size} bytes)")
        
        if data_size > 50 * 1024 * 1024:  # 大于50MB
            logger.error(f"图片校验失败：文件大小过大 ({data_size / (1024*1024):.2f} MB)")
            return False, f"文件大小过大: {data_size / (1024*1024):.2f} MB"
        
        logger.info(f"图片校验成功：尺寸 {width}x{height}，格式 {format_type}，大小 {data_size / 1024:.2f} KB")
        return True, f"尺寸 {width}x{height}，格式 {format_type}，大小 {data_size / 1024:.2f} KB"
        
    except Exception as e:
        logger.error(f"图片校验异常：{str(e)}")
        return False, f"校验异常: {str(e)}"

if __name__ == '__main__':
    # 设置日志
    logger = setup_logging()

    # 创建debug_img目录（如果不存在）
    if not os.path.exists("debug_img"):
        os.makedirs("debug_img")
        logger.info("Created debug_img directory")

    # Delete recv_test.json file if it exists
    if os.path.exists("recv_test.json"):
        os.remove("recv_test.json")
        logger.info("Deleted recv_test.json")

    commands = [
        "?Asset",
        # "@|600",
        # "@|",
        # "?Order",
        # "Profile|",
        # "WiFi|1",
        # "WiFi|",
        # "?ERR",
        # "REACT|1",
        # "REACT|",
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
    run_count = 0

    logger.info("开始无限循环UART测试...")
    
    try:
        while True:
            run_count += 1
            logger.info(f"==================== 开始第 {run_count} 次运行 ====================")
            print(f"Running test iteration {run_count}")
            
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
                                logger.warning(f"Failed to decode JSON for command: {command}")
                            if command == "?OBdata":
                                time.sleep(2) # delay for esp32 image processing
                    else:
                        break

            # 处理图片数据
            if image_data_list:
                combined_image_data = ''.join(image_data_list)
                combined_image_data = fix_base64_padding(combined_image_data)
                
                # 校验图片
                is_valid, validation_msg = validate_image(combined_image_data, logger)
                
                if is_valid:
                    # 图片校验通过，保存图片到debug_img目录
                    try:
                        save_image(combined_image_data, f"debug_img/combined_image_{run_count}.bmp")
                        logger.info(f"第 {run_count} 次运行：图片保存成功 - {validation_msg}")
                    except Exception as e:
                        logger.error(f"第 {run_count} 次运行：图片保存失败 - {str(e)}")
                else:
                    logger.error(f"第 {run_count} 次运行：图片校验失败 - {validation_msg}")
            else:
                logger.warning(f"第 {run_count} 次运行：未收到图片数据")

            logger.info(f"第 {run_count} 次运行完成，等待10分钟后开始下一次运行...")
            print(f"Test iteration {run_count} completed. Waiting 10 minutes for next run...")
            
            # 等待10分钟（600秒）
            time.sleep(120)
            
    except KeyboardInterrupt:
        logger.info(f"程序被用户中断，总共完成了 {run_count} 次运行")
        print(f"Program interrupted by user. Completed {run_count} runs.")
    except Exception as e:
        logger.error(f"程序异常退出：{str(e)}")
        print(f"Program error: {str(e)}")
    finally:
        if 'uart' in locals():
            uart.uartport.close()
            logger.info("UART端口已关闭")