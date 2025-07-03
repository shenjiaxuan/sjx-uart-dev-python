import socket
import serial
import base64
import time
import math
from PIL import Image
import json
import subprocess
from datetime import datetime
import numpy as np
from pathlib import Path
import mmap
import posix_ipc
import os
from threading import Thread
import threading
from socket_def import *
import random
import signal
import sys

import logging
from logging.handlers import RotatingFileHandler

# ================================
# SPEED CALCULATION CONFIGURATION
# ================================
# Choose speed calculation method:
# True:  Weighted Average - (previous_average * count + new_speed) / (count + 1)
# False: Sliding Average  - (current_average + new_speed) / 2
USE_WEIGHTED_AVERAGE = True
# ================================

CAMERA1_DIAGNOSE_INFO_PATH = "/home/root/AglaiaSense/resource/share_config/diagnose_info_1.json"
CAMERA2_DIAGNOSE_INFO_PATH = "/home/root/AglaiaSense/resource/share_config/diagnose_info_2.json"
LOG_FOLDER = "log"
CONFIG_PATH = '/home/root/AglaiaSense/resource/share_config/gs501.json'
CAM1_ID = 1
CAM2_ID = 2

# Event Server Configuration (for receiving speed data from SDK)
EVENT_SERVER_IP = "127.0.0.1"
EVENT_SERVER_PORT = 1780  # Port for receiving speed events from SDK
event_server_socket = None
event_server_thread = None

# SDK config
SDK_SERVER_IP = '127.0.0.1'
SDK_JSON_PORT = 1880
SDK_BINARY_PORT = 1881
SDK_USER_NAME = "sdk_user"
SDK_USER_PASSWD = "sdk_password"
sdk_token = None
sdk_token_lock = threading.Lock()

# define pic size
IMAGE_CHANNELS = 3
IMAGE_HEIGHT = 300
IMAGE_WIDTH = 300

# AppNumber definitions
APP_NUMBER_EMERGENCY = "698"
APP_NUMBER_TRAFFIC = "699"

send_max_length = 980
count_interval = "300"
profile_index = 3
emer_mode = 0  # corrected from ener_mode
str_image = []
emer_imgage_send = 0

dnn_default_dirct = {"spdunit":"KPH","incar":-1,"incarspd":-1,"inbus":-1,"inbusspd":-1,"inped":-1,"inpedspd":-1,"incycle":-1,"incyclespd":-1,"intruck":-1,"intruckspd":-1,"outcar":-1,"outcarspd":-1,"outbus":-1,"outbusspd":-1,"outped":-1,"outpedspd":-1,"outcycle":-1,"outcyclespd":-1,"outtruck":-1,"outtruckspd":-1}

sockets = {
    'cam1_info_sock': None,
    'cam2_info_sock': None,
    'cam1_dnn_sock': None,
    'cam2_dnn_sock': None
}


# Declare globals for shared memory pointers and cam_in_use to be accessible in other functions
cam1_image_shm_ptr = None
cam2_image_shm_ptr = None
cam_in_use = 1

# CDS related globals
previous_counting_data_left = {}
previous_counting_data_right = {}
cds_alerts_received = False

# Speed data globals
speed_data_left = {}  # {direction_class: [speed_values]}
speed_data_right = {}
speed_averages_left = {}  # {direction_class: average_speed}
speed_averages_right = {}
speed_counts_left = {}  # {direction_class: count}
speed_counts_right = {}
speed_data_lock = threading.Lock()

def setup_logger():
    log_folder_path = Path(LOG_FOLDER)
    log_folder_path.mkdir(parents=True, exist_ok=True)
    log_file_path = log_folder_path.joinpath("uart_log.txt")

    logger = logging.getLogger("uart_logger")
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter(fmt="%(asctime)s [%(levelname)s]: %(message)s",
                                  datefmt="%m/%d/%Y %H:%M:%S")

    file_handler = RotatingFileHandler(log_file_path, maxBytes=10*1024*1024, backupCount=3)
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.DEBUG)

    if not logger.hasHandlers():
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

    return logger

# Global logger
logger = setup_logger()

def connect_socket(server_address, socket_key):
    while True:
        if sockets[socket_key] is not None:
            time.sleep(1)  # If the connection exists, wait briefly
            continue

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect(server_address)
            sockets[socket_key] = sock
            logger.info(f"Connected to server at {server_address} for {socket_key}")
                
        except socket.error as e:
            logger.error(f"Failed to connect to {server_address} for {socket_key}: {e}. Retrying in 5 seconds...")
            time.sleep(5)  # Wait 5 seconds and try again

# SDK 相关函数
def send_json_request(request):
    """向 SDK 发送 JSON 请求"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.connect((SDK_SERVER_IP, SDK_JSON_PORT))
            sock.sendall(json.dumps(request).encode('utf-8'))
            response = b""
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                response += chunk
            return json.loads(response.decode('utf-8'))
        except Exception as e:
            logger.error(f"SDK JSON request error: {e}")
            return None

def sdk_login():
    """SDK 登录获取 token"""
    global sdk_token
    request = {"cmd": "user_login_req", "username": SDK_USER_NAME, "passwd": SDK_USER_PASSWD}
    response = send_json_request(request)
    if response and response.get("cmd") == "user_login_rsp" and response.get("ret_code") == 0:
        with sdk_token_lock:
            sdk_token = response.get("token")
        logger.info("SDK login successful")
        return sdk_token
    else:
        logger.error(f"SDK login failed: {response}")
        return None

def sdk_logout():
    """SDK 登出"""
    global sdk_token
    with sdk_token_lock:
        if sdk_token:
            request = {"cmd": "user_logout_req", "token": sdk_token}
            response = send_json_request(request)
            logger.info(f"SDK logout response: {response}")
            sdk_token = None

def sdk_get_counting_data(camera_id):
    """从 SDK 获取计数数据"""
    global sdk_token
    
    with sdk_token_lock:
        current_token = sdk_token
    
    if not current_token:
        current_token = sdk_login()
        if not current_token:
            return None
    
    # 根据 camera_id 确定使用的摄像头标识
    if camera_id == CAM1_ID:
        camera_name = "left"
    elif camera_id == CAM2_ID:
        camera_name = "right"
    else:
        logger.error(f"Invalid camera_id for SDK counting: {camera_id}")
        return None
    
    request = {"cmd": "get_dnn_counting_req", "camera_id": camera_name, "token": current_token}
    response = send_json_request(request)
    logger.info(f"-----------SDK counting data: {response}")
    return response

def sdk_heartbeat():
    """发送心跳保持连接"""
    global sdk_token
    
    with sdk_token_lock:
        current_token = sdk_token
    
    if current_token:
        request = {"cmd": "heartbeat_req", "token": current_token}
        response = send_json_request(request)
        if response and response.get("ret_code") != 0:
            logger.warning("SDK heartbeat failed, may need to re-login")
            return False
        return True
    return False

def sdk_heartbeat_thread():
    """心跳线程，定期发送心跳"""
    while True:
        try:
            sdk_heartbeat()
            time.sleep(60)  # 每60秒发送一次心跳
        except Exception as e:
            logger.error(f"SDK heartbeat thread error: {e}")
            time.sleep(60)

def sdk_set_event_server_info(server_ip, server_port):
    """设置事件服务器信息"""
    global sdk_token
    
    with sdk_token_lock:
        current_token = sdk_token
    
    if not current_token:
        current_token = sdk_login()
        if not current_token:
            return False
    
    request = {
        "cmd": "set_event_server_info_req",
        "token": current_token,
        "server_ip": server_ip,
        "server_port": server_port
    }
    
    response = send_json_request(request)
    if response and response.get("cmd") == "set_event_server_info_rsp" and response.get("ret_code") == 0:
        logger.info(f"Successfully set event server info: {server_ip}:{server_port}")
        return True
    else:
        logger.error(f"Failed to set event server info: {response}")
        return False

def calculate_speed_weighted_average(direction_class, new_speed, speed_averages, speed_counts):
    """
    Calculate speed using weighted average method:
    (previous_average * count + new_speed) / (count + 1)
    """
    current_count = speed_counts.get(direction_class, 0)
    current_avg = speed_averages.get(direction_class, 0.0)
    
    if current_count == 0:
        # First speed value
        new_avg = new_speed
        new_count = 1
    else:
        # Weighted average calculation
        new_avg = (current_avg * current_count + new_speed) / (current_count + 1)
        new_count = current_count + 1
    
    speed_averages[direction_class] = new_avg
    speed_counts[direction_class] = new_count
    
    return new_avg

def calculate_speed_sliding_average(direction_class, new_speed, speed_averages, speed_data):
    """
    Calculate speed using original sliding average method:
    (current_average + new_speed) / 2
    """
    # Add speed to data list for tracking
    if direction_class not in speed_data:
        speed_data[direction_class] = []
    
    speed_data[direction_class].append(new_speed)
    
    if len(speed_data[direction_class]) == 1:
        # First value
        new_avg = new_speed
    else:
        # Calculate sliding average
        current_avg = speed_averages.get(direction_class, new_speed)
        new_avg = (current_avg + new_speed) / 2.0
    
    speed_averages[direction_class] = new_avg
    
    return new_avg

def process_speed_data(speed_event, camera_side):
    """Process speed event data and update speed averages"""
    global speed_data_left, speed_data_right, speed_averages_left, speed_averages_right
    global speed_counts_left, speed_counts_right
    
    try:
        if not speed_event or "event" not in speed_event:
            return
            
        event_data = speed_event["event"]
        if "shapes" not in event_data:
            return
            
        with speed_data_lock:
            # Select the appropriate speed data dictionary
            if camera_side == "left":
                speed_data = speed_data_left
                speed_averages = speed_averages_left
                speed_counts = speed_counts_left
            elif camera_side == "right":
                speed_data = speed_data_right
                speed_averages = speed_averages_right
                speed_counts = speed_counts_right
            else:
                logger.error(f"Invalid camera_side: {camera_side}")
                return
            
            # Process each shape
            for shape in event_data["shapes"]:
                label = shape.get("label", "")
                counters = shape.get("counters", [])
                
                # Determine direction from label
                direction = "in"  # default
                if label.endswith("_out"):
                    direction = "out"
                elif label.endswith("_in"):
                    direction = "in"
                elif "_" in label:
                    # For labels like "lane_0", assume "in" for now
                    direction = "in"
                
                # Process each counter
                for counter in counters:
                    vehicle_class = counter.get("class", "")
                    speed = counter.get("speed", 0.0)
                    
                    if vehicle_class and speed > 0:
                        # Map vehicle class names
                        vehicle_mapping = {
                            'car': 'car',
                            'truck': 'truck',
                            'bus': 'bus',
                            'pedestrian': 'ped',
                            'cycle': 'cycle'
                        }
                        
                        mapped_class = vehicle_mapping.get(vehicle_class, vehicle_class)
                        direction_class = f"{direction}{mapped_class}"
                        
                        # Calculate speed average using selected method
                        if USE_WEIGHTED_AVERAGE:
                            new_avg = calculate_speed_weighted_average(
                                direction_class, speed, speed_averages, speed_counts
                            )
                            count_info = f"count: {speed_counts.get(direction_class, 0)}"
                        else:
                            new_avg = calculate_speed_sliding_average(
                                direction_class, speed, speed_averages, speed_data
                            )
                            count_info = f"samples: {len(speed_data.get(direction_class, []))}"
                        
                        logger.info(f"{camera_side} camera: Updated speed for {direction_class}: {speed} "
                                  f"(avg: {new_avg:.2f}, {count_info})")
            
            # Update global speed data
            if camera_side == "left":
                speed_data_left = speed_data
                speed_averages_left = speed_averages
                speed_counts_left = speed_counts
            elif camera_side == "right":
                speed_data_right = speed_data
                speed_averages_right = speed_averages
                speed_counts_right = speed_counts
                
    except Exception as e:
        logger.error(f"Error processing speed data: {e}")

def reset_speed_data():
    """Reset speed data and averages for new cycle"""
    global speed_data_left, speed_data_right, speed_averages_left, speed_averages_right
    global speed_counts_left, speed_counts_right
    
    with speed_data_lock:
        speed_data_left.clear()
        speed_data_right.clear()
        speed_averages_left.clear()
        speed_averages_right.clear()
        speed_counts_left.clear()
        speed_counts_right.clear()

def get_speed_data_for_uart(camera_side):
    """Get speed averages for UART response"""
    global speed_averages_left, speed_averages_right
    
    with speed_data_lock:
        if camera_side == "left":
            return dict(speed_averages_left)
        elif camera_side == "right":
            return dict(speed_averages_right)
        else:
            return {}

def process_coordinates_response(coordinates_data):
    """
    处理coordinates数据，将所有坐标值转换为整数
    """
    try:
        if not coordinates_data:
            return json.dumps({})
            
        # 解析coordinates数据
        coordinates = json.loads(coordinates_data.decode('utf-8'))
        processed_coordinates = {}
        
        for key, coord_list in coordinates.items():
            if isinstance(coord_list, list):
                processed_coord_list = []
                for coord in coord_list:
                    if isinstance(coord, dict) and 'x' in coord and 'y' in coord:
                        processed_coord = {
                            'x': int(coord['x']),
                            'y': int(coord['y'])
                        }
                        processed_coord_list.append(processed_coord)
                    else:
                        processed_coord_list.append(coord)
                processed_coordinates[key] = processed_coord_list
            else:
                processed_coordinates[key] = coord_list
        
        # 返回处理后的coordinates数据
        return json.dumps(processed_coordinates)
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to decode coordinates data: {e}")
        return json.dumps({})
    except Exception as e:
        logger.error(f"Error processing coordinates data: {e}")
        return json.dumps({})

def send_data(socket_key, data):
    sock = sockets[socket_key]
    if sock is None:
        logger.error("No active socket connection. Cannot send data.")
        return
    
    try:
        sock.sendall(data)
    except socket.error as e:
        logger.error(f"Send error: {e}. Setting {socket_key} to None.")
        sockets[socket_key] = None

def receive_data(socket_key, buffer_size):
    sock = sockets[socket_key]
    if sock is None:
        logger.error("No active socket connection. Cannot receive data.")
        return None
    
    try:
        response = sock.recv(buffer_size)
        if not response:
            logger.error(f"Receive None: Setting {socket_key} to None.")
            sockets[socket_key] = None
        return response
    except socket.error as e:
        logger.error(f"Receive error: {e}. Setting {socket_key} to None.")
        sockets[socket_key] = None
        return None

def send_cds_command(socket_key, command):
    """发送命令到CDS服务器 - 只使用命令socket"""
    sock = sockets[socket_key]
    if sock is None:
        logger.error(f"No CDS command socket connection for {socket_key}")
        return None
        
    try:
        command_json = json.dumps(command)
        sock.send(command_json.encode('utf-8'))
        
        response = sock.recv(4096)
        if response:
            return json.loads(response.decode('utf-8'))
        return None
        
    except Exception as e:
        logger.error(f"CDS command error for {socket_key}: {e}")
        sockets[socket_key] = None
        return None

def get_cds_counting_data():
    """从SDK获取计数数据"""
    left_counting_data = {}
    right_counting_data = {}
    
    if cam_in_use == 1 or cam_in_use == 3:  # 左摄像头
        response = sdk_get_counting_data(CAM1_ID)
        if response and 'counting_results' in response:
            counting_results = response.get("counting_results", {})
            left_counting_data = counting_results
    
    if cam_in_use == 2 or cam_in_use == 3:  # 右摄像头
        response = sdk_get_counting_data(CAM2_ID)
        if response and 'counting_results' in response:
            counting_results = response.get("counting_results", {})
            right_counting_data = counting_results
    
    return left_counting_data, right_counting_data

def process_cumulative_counting(current_data, camera_side):
    """Process cumulative counting data by subtracting previous values"""
    global previous_counting_data_left, previous_counting_data_right
    
    # Select the appropriate previous data dictionary based on camera side
    if camera_side == "left":
        previous_counting_data = previous_counting_data_left
    elif camera_side == "right":
        previous_counting_data = previous_counting_data_right
    else:
        logger.error(f"Invalid camera_side: {camera_side}")
        return {}
    
    period_data = {}
    
    for boundary, counts in current_data.items():
        if boundary not in previous_counting_data:
            previous_counting_data[boundary] = {}
            
        period_data[boundary] = {}
        
        for vehicle_type, count in counts.items():
            prev_count = previous_counting_data[boundary].get(vehicle_type, 0)
            period_count = max(0, count - prev_count)  # Ensure non-negative
            period_data[boundary][vehicle_type] = period_count
            previous_counting_data[boundary][vehicle_type] = count
    
    # Update the global dictionary based on camera side
    if camera_side == "left":
        previous_counting_data_left = previous_counting_data
    elif camera_side == "right":
        previous_counting_data_right = previous_counting_data
    
    return period_data

def reformat_counting_for_uart(counting_results, speed_averages):
    """Reformat counting data for UART and integrate speed averages"""
    uart_data = dnn_default_dirct.copy()
    
    try:
        # Process single camera counting results
        for boundary, counts in counting_results.items():
            # Check if boundary name ends with _in or _out
            if boundary.endswith('_in'):
                direction = 'in'
            elif boundary.endswith('_out'):
                direction = 'out'
            else:
                # For boundaries like boundary_1, boundary_2, assume 'in' for now
                direction = 'in'
            
            # Map vehicle types to UART format
            vehicle_mapping = {
                'car': 'car',
                'truck': 'truck', 
                'bus': 'bus',
                'pedestrian': 'ped',
                'cycle': 'cycle'
            }
            
            for vehicle_type, count in counts.items():
                if vehicle_type in vehicle_mapping:
                    uart_key = direction + vehicle_mapping[vehicle_type]
                    speed_key = uart_key + "spd"
                    
                    if uart_key in uart_data:
                        uart_data[uart_key] = count  # Single camera data
                        
                        # Set speed from averages or -1 if no data/count is 0
                        direction_class = direction + vehicle_mapping[vehicle_type]
                        if count > 0 and direction_class in speed_averages:
                            uart_data[speed_key] = int(round(speed_averages[direction_class]))
                        elif count == 0:
                            uart_data[speed_key] = 0
                        else:
                            uart_data[speed_key] = -1
                        
    except Exception as e:
        logger.error(f"Error reformatting counting data: {e}")
        
    return uart_data

def open_shared_memory(shm_name):
    try:
        shm = posix_ipc.SharedMemory(shm_name, posix_ipc.O_RDWR)
        return shm
    except posix_ipc.Error:
        return None

def map_shared_memory(shm):
    shm_ptr = mmap.mmap(shm.fd, SHM_BMP_SIZE, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE)
    if shm_ptr == -1:
        os.close(shm.fd)
        return None
    return shm_ptr

def get_pic_from_socket(shm_ptr, cam_id):
    shm_ptr.seek(0)
    image_data = shm_ptr.read(IMAGE_WIDTH * IMAGE_HEIGHT * IMAGE_CHANNELS)
    image_array = np.frombuffer(image_data, dtype=np.uint8)
    image_array = image_array.reshape((IMAGE_HEIGHT, IMAGE_WIDTH, IMAGE_CHANNELS))
    image_array = image_array[..., ::-1]
    image = Image.fromarray(image_array)
    tmp_image_path = Path(f'./tmp/tmp_{cam_id}.bmp').resolve()
    tmp_image_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(tmp_image_path)

def get_dnn_date(socket_key):
    dnn_data_request = DnnDataYolo(cmd=DNN_GET)
    send_data(socket_key, dnn_data_request.to_bytes())
    response = receive_data(socket_key, SOCK_COMM_LEN)
    if response:
        try:
            json_response = response.decode('utf-8')
            dnn_dict = DnnDataYolo.from_json(json_response)
            return dnn_dict
        except Exception as e:
            logger.error(f"Failed to decode or parse DNN data: {e}")
            return None
    else:
        return None

def camera_control_process(socket_key, command, contol_val):
    try:
        if command == GET_GAIN:
            gain_data_g = GainData(command)
            send_data(socket_key, gain_data_g.to_bytes())
            response = receive_data(socket_key, SOCK_COMM_LEN)
            if response:
                gain_data_g = GainData.from_bytes(response)
            return gain_data_g.val

        elif command == GET_EXPOSURE:
            exposure_data_g = ExposureData(command)
            send_data(socket_key, exposure_data_g.to_bytes())
            response = receive_data(socket_key, SOCK_COMM_LEN)
            if response:
                exposure_data_g = ExposureData.from_bytes(response)
            return exposure_data_g.val

        elif command == GET_AE_MODE:
            ae_mode_data_g = AeModeData(command)
            send_data(socket_key, ae_mode_data_g.to_bytes())
            response = receive_data(socket_key, SOCK_COMM_LEN)
            if response:
                ae_mode_data_g = AeModeData.from_bytes(response)
            return ae_mode_data_g.val

        elif command == GET_AWB_MODE:
            awb_mode_data_g = AwbModeData(command)
            send_data(socket_key, awb_mode_data_g.to_bytes())
            response = receive_data(socket_key, SOCK_COMM_LEN)
            if response:
                awb_mode_data_g = AwbModeData.from_bytes(response)
            return awb_mode_data_g.val
        elif command == CAM_EN:
            cam_en = CamEn(command, contol_val)
            send_data(socket_key, cam_en.to_bytes())
        elif command == ENERGENCY_MODE:
            energency_mode = EnergencyMode(command, contol_val)
            send_data(socket_key, energency_mode.to_bytes())
        else:
            logger.error(f"Camera command error: {hex(command)}")
    except socket.timeout:
        logger.error(f"Socket timed out waiting for response for command: {hex(command)}")
    except socket.error as e:
        logger.error(f"Socket error for command: {hex(command)}, error: {e}")
    except Exception as e:
        logger.error(f"Unexpected error for command: {hex(command)}, error: {e}")

def load_config(path):
    with open(path, 'r') as file:
        return json.load(file)

def get_wifi_status():
    result = subprocess.run(['nmcli', '-t', '-f', 'WIFI', 'radio'], capture_output=True, text=True)
    return result.stdout.strip()

def check_camera_errors(path):
    config = load_config(path)
    if all(value == "True" for value in config.values()):
        return "0"
    else:
        return "1"

class UART:
    def __init__(self):
        self.uartport = serial.Serial(
                port="/dev/ttymxc2",
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
        logger.debug(f"UART send ->: {cmd}")
        self.uartport.write((cmd+"\n").encode("utf_8"))

    def receive_serial(self):
        rcvdata = self.uartport.readline()
        return rcvdata

def save_image_with_target_size(image, cam_in_use):
    target_size = 12800 #12800 #10240 # 15360 #Bytes
    filepath = './tmp/converted-jpg-image.jpg'
    #quality = 20 & 35 is an experience value
    quality = 20 if cam_in_use == 3 else 35
    while quality > 0:
        logger.debug(f"*******************Quality: {quality}")
        # save image to tmp_file. One cycle takes about 8ms
        temp_filepath = filepath.replace('.jpg', '_temp.jpg')
        image.save(temp_filepath, format='JPEG', quality=quality)
        # check image size
        if os.path.getsize(temp_filepath) <= target_size:
            os.rename(temp_filepath, filepath)
            return
        if quality <= 10:
            quality -= 2
        else:
            quality -= 5
    os.rename(temp_filepath, filepath)

def update_sim_attribute(cam_in_use):
    global str_image
    if emer_imgage_send == 1:
        return
    if cam_in_use == 1:
        image = Image.open('./tmp/tmp_1.bmp')
    elif cam_in_use == 2:
        image = Image.open('./tmp/tmp_2.bmp')
    elif cam_in_use == 3:
        image1 = Image.open('./tmp/tmp_1.bmp')
        image2 = Image.open('./tmp/tmp_2.bmp')
        image = Image.new('RGB', (image1.width + image2.width, max(image1.height, image2.height)))
        image.paste(image1, (0, 0))
        image.paste(image2, (image1.width, 0))

    save_image_with_target_size(image, cam_in_use)

    with open('./tmp/converted-jpg-image.jpg', 'rb') as image2string:
        converted_string = base64.b64encode(image2string.read()).decode()
    
    str_len = len(converted_string)
    send_time = math.ceil(str_len / send_max_length)
    str_image = []
    for x in range(send_time):
        str_image.append(converted_string[x * send_max_length:(x + 1) * send_max_length])

def handle_sdk_client_connection(client_socket, client_address):
    """处理来自SDK的单个客户端连接"""
    logger.info(f"SDK client connected from {client_address}")
    global cds_alerts_received, emer_mode, cam1_image_shm_ptr, cam2_image_shm_ptr, cam_in_use
    try:
        while True:
            data = client_socket.recv(40960)
            if not data:
                break
                
            try:
                message = json.loads(data.decode('utf-8'))
                # logger.info(f"Received data from SDK client {client_address}: {message}")
                event_type = message.get("event_type")
                camera_id = message.get("camera_id", "unknown")

                if event_type == "speed":
                    data_part = message.get("cds_data", {})
                    speed_event = data_part.get("speed_event", {})
                    process_speed_data(speed_event, camera_id)
                elif event_type == "pedestrian":
                    logger.info(f"Received CDS alert from {client_address}: {message}")
                    cds_alerts_received = True
                    # Set emergency mode when alert received
                    emer_mode = 1
                    logger.info(f"emer_mode set to {emer_mode} by CDS alert")
                    
                    # Save images to buffer when emer_mode is set to 1
                    if cam_in_use == 1 or cam_in_use == 3:
                        get_pic_from_socket(cam1_image_shm_ptr, CAM1_ID)
                    if cam_in_use == 2 or cam_in_use == 3:
                        get_pic_from_socket(cam2_image_shm_ptr, CAM2_ID)
                    update_sim_attribute(cam_in_use)
                elif event_type == "parking":
                    logger.info(f"Received parking event: {message}")
                else:
                    logger.info(f"Received unknown event type '{event_type}': {message}")
                    
            except json.JSONDecodeError as e:
                logger.error(f"Failed to decode JSON from SDK client {client_address}: {e}")
            except Exception as e:
                logger.error(f"Error processing data from SDK client {client_address}: {e}")
                
    except Exception as e:
        logger.error(f"Error handling SDK client {client_address}: {e}")
    finally:
        client_socket.close()
        logger.info(f"SDK client {client_address} disconnected")

def start_event_server():
    """启动事件服务器接收SDK发送的速度数据"""
    global event_server_socket
    
    try:
        event_server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        event_server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        event_server_socket.bind((EVENT_SERVER_IP, EVENT_SERVER_PORT))
        event_server_socket.listen(5)
        
        logger.info(f"Event server started on {EVENT_SERVER_IP}:{EVENT_SERVER_PORT}")
        
        while True:
            try:
                client_socket, client_address = event_server_socket.accept()
                # 为每个客户端连接创建新线程
                client_thread = threading.Thread(
                    target=handle_sdk_client_connection, 
                    args=(client_socket, client_address),
                    daemon=True
                )
                client_thread.start()
                
            except socket.error as e:
                if event_server_socket:  # 检查socket是否仍然有效
                    logger.error(f"Error accepting client connection: {e}")
                else:
                    break  # socket已关闭，退出循环
                    
    except Exception as e:
        logger.error(f"Error starting event server: {e}")
    finally:
        if event_server_socket:
            event_server_socket.close()
            event_server_socket = None

def stop_event_server():
    """停止事件服务器"""
    global event_server_socket
    if event_server_socket:
        event_server_socket.close()
        event_server_socket = None
        logger.info("Event server stopped")

def main():
    """
    Main function to initialize logger, UART, load config, start socket connection
    and handle UART commands.
    """
    global count_interval, profile_index, emer_mode
    global IMAGE_HEIGHT, IMAGE_WIDTH, cam_in_use
    global cam1_image_shm_ptr, cam2_image_shm_ptr
    global emer_imgage_send

    uart = UART()
    config = load_config(CONFIG_PATH)
    IMAGE_HEIGHT = int(config.get('InputTensorHeith'))
    IMAGE_WIDTH = int(config.get('InputTensorWidth'))
    # cam_in_use: left = 1, right =2, all = 3. note:left is cam1, right is cam2
    # Load cam_in_use from config.json instead of CONFIG_PATH
    local_config = load_config("config.json")
    sensor_num = local_config["cam_in_use"]
    if sensor_num in ["1", "left"]:
        cam_in_use = 1
        profile_index = 1
    elif sensor_num in ["2", "right"]:
        cam_in_use = 2
        profile_index = 2
    elif sensor_num in ["3", "dual"]:
        cam_in_use = 3
        profile_index = 3
    else:
        logger.error(f"Invalid SensorNum value: {sensor_num}")
        cam_in_use = 1

    # Initialize SDK connection
    logger.info("Initializing SDK connection...")
    initial_token = sdk_login()
    if not initial_token:
        logger.error("Failed to login to SDK, but continuing...")
    
    # Start SDK heartbeat thread
    heartbeat_thread = Thread(target=sdk_heartbeat_thread)
    heartbeat_thread.daemon = True
    heartbeat_thread.start()

    # Start event server to receive event data from SDK
    logger.info("Starting event server for SDK event data...")
    event_server_thread = Thread(target=start_event_server)
    event_server_thread.daemon = True
    event_server_thread.start()

    # Set event server info in SDK
    if not sdk_set_event_server_info(EVENT_SERVER_IP, EVENT_SERVER_PORT):
        logger.warning("Failed to set event server info in SDK, but continuing...")

    # Connect to camera sockets (keeping original camera connections)
    if cam_in_use == 1 or cam_in_use == 3:
        # Original camera connections
        cam1_info_address = ("localhost", CAMERA1_PORT)
        cam1_dnn_address = ("localhost", CAMERA1_DNN_PORT)
        cam1_info_thread = Thread(target=connect_socket, args=(cam1_info_address, 'cam1_info_sock'))
        cam1_dnn_thread = Thread(target=connect_socket, args=(cam1_dnn_address, 'cam1_dnn_sock'))
        cam1_info_thread.daemon = True
        cam1_dnn_thread.daemon = True
        cam1_info_thread.start()
        cam1_dnn_thread.start()
        
    if cam_in_use == 2 or cam_in_use == 3:
        # Original camera connections
        cam2_info_address = ("localhost", CAMERA2_PORT)
        cam2_dnn_address = ("localhost", CAMERA2_DNN_PORT)
        cam2_info_thread = Thread(target=connect_socket, args=(cam2_info_address, 'cam2_info_sock'))
        cam2_dnn_thread = Thread(target=connect_socket, args=(cam2_dnn_address, 'cam2_dnn_sock'))
        cam2_info_thread.daemon = True
        cam2_dnn_thread.daemon = True
        cam2_info_thread.start()
        cam2_dnn_thread.start()

    # Open camera1 shared_memory
    if cam_in_use == 1 or cam_in_use == 3:
        shm_name = CAMERA1_SHM_BMP_NAME
        cam1_image_shm = open_shared_memory(shm_name)
        if cam1_image_shm is None:
            logger.error("Failed to open shared memory for cam1")
            return
        cam1_image_shm_ptr = map_shared_memory(cam1_image_shm)
        if cam1_image_shm_ptr is None:
            logger.error("Failed to map shared memory for cam1")
            cam1_image_shm.close_fd()
            return
        get_pic_from_socket(cam1_image_shm_ptr, CAM1_ID)
    if cam_in_use == 2 or cam_in_use == 3:
        shm_name = CAMERA2_SHM_BMP_NAME
        cam2_image_shm = open_shared_memory(shm_name)
        if cam2_image_shm is None:
            logger.error("Failed to open shared memory for cam2")
            return
        cam2_image_shm_ptr = map_shared_memory(cam2_image_shm)
        if cam2_image_shm_ptr is None:
            logger.error("Failed to map shared memory for cam2")
            cam2_image_shm.close_fd()
            return
        get_pic_from_socket(cam2_image_shm_ptr, CAM2_ID)

    update_sim_attribute(cam_in_use)

    while True:
        raw_data = uart.receive_serial()
        if raw_data:
            start_time = time.time()
            string = raw_data.decode("utf_8", "ignore").rstrip()
            logger.debug(f"UART recv <-: {string}")
            if string == "?Asset":
                # Set AppNumber based on emergency mode status
                app_number = APP_NUMBER_EMERGENCY if emer_mode == 1 else APP_NUMBER_TRAFFIC
                
                asset_data = {
                    "MfrName": config["MfrName"],
                    "ModelNumber": config["ModelNumber"],
                    "SerialNumber": config["SerialNumber"],
                    "MfgDate": config["MfgDate"],
                    "FWVersion": config["FWVersion"],
                    "HWVersion": config["HWVersion"],
                    "AppNumber": app_number
                }
                response = json.dumps(asset_data)
                uart.send_serial(response)
            elif string[:2] == "@|":
                if string[2:]:
                    count_interval = str(string[2:])
                response = json.dumps({"NICFrequency": int(count_interval)})
                uart.send_serial(response)
            elif string == "?Order":
                response = json.dumps(config["Order"])
                uart.send_serial(response)
            elif string[:8] == "Profile|":
                if string[8:] and int(string[8:]) in [1, 2, 3]:
                    profile_index = int(string[8:])
                response = json.dumps({"CamProfile": int(profile_index)})
                uart.send_serial(response)
                if int(profile_index) != cam_in_use:
                    cam_in_use = int(profile_index)
                    # Update cam_in_use in config.json instead of CONFIG_PATH
                    local_config = load_config("config.json")
                    if int(profile_index) == 1:
                        local_config["cam_in_use"] = "left"
                    elif int(profile_index) == 2:
                        local_config["cam_in_use"] = "right"
                    elif int(profile_index) == 3:
                        local_config["cam_in_use"] = "dual"
                    with open("config.json", "w", encoding="utf-8") as file:
                        json.dump(local_config, file, indent=4)

            elif string[:5] == "WiFi|":
                if get_wifi_status() == 'enabled':
                    wifi_cur_config = 1
                else:
                    wifi_cur_config = 0
                if string[5:] and int(string[5:]) in [0, 1]:
                    wifi_status = str(string[5:])
                    if wifi_cur_config != int(wifi_status):
                        if int(wifi_status) == 1:
                            subprocess.run(['nmcli', 'radio', 'wifi', 'on'])
                        else:
                            subprocess.run(['nmcli', 'radio', 'wifi', 'off'])
                else:
                    wifi_status = wifi_cur_config
                response = json.dumps({"WiFiEnable": int(wifi_status)})
                uart.send_serial(response)
            elif string == "?ERR":
                cam1_error_code = check_camera_errors(CAMERA1_DIAGNOSE_INFO_PATH)
                cam2_error_code = check_camera_errors(CAMERA2_DIAGNOSE_INFO_PATH)
                response = json.dumps({"Cam1ErrCode": cam1_error_code,"Cam2ErrCode": cam2_error_code})
                uart.send_serial(response)
            elif string[:6] == "REACT|":
                # Just return current emer_mode, no modification
                response = json.dumps({"EmergencyMode": int(emer_mode)})
                uart.send_serial(response)
            elif string == "?OBdata":
                # If emer_mode == 1, skip image save and update_sim_attribute
                if emer_mode == 1:
                    logger.warning("emer_mode==1, skip image save and update_sim_attribute on ?OBdata")
                else:
                    # save image to str_image, wait str
                    if cam_in_use == 1 or cam_in_use == 3:
                        get_pic_from_socket(cam1_image_shm_ptr, CAM1_ID)
                    if cam_in_use == 2 or cam_in_use == 3:
                        get_pic_from_socket(cam2_image_shm_ptr, CAM2_ID)
                    update_sim_attribute(cam_in_use)
                
                # 获取交通类别信息
                left_traffic_data = {}
                right_traffic_data = {}
                
                # 获取左摄像头交通类别信息
                if cam_in_use == 1 or cam_in_use == 3:
                    # 选择左摄像头的socket
                    cam_info_socket = 'cam1_info_sock'
                    # 发送JSON格式的请求获取交通类别信息
                    traffic_request = {"cmd": "traffic_category"}
                    traffic_request_json = json.dumps(traffic_request)
                    send_data(cam_info_socket, traffic_request_json.encode('utf-8'))
                    response = receive_data(cam_info_socket, 4096)
                    
                    if response:
                        try:
                            # 检查响应是否为有效的JSON
                            left_traffic_data = json.loads(response.decode('utf-8'))
                            logger.info(f"Left camera traffic category data: {left_traffic_data}")
                        except json.JSONDecodeError as e:
                            logger.error(f"Failed to decode left traffic category response: {e}")
                        except Exception as e:
                            logger.error(f"Error processing left traffic category response: {e}")
                
                # 获取右摄像头交通类别信息
                if cam_in_use == 2 or cam_in_use == 3:
                    # 选择右摄像头的socket
                    cam_info_socket = 'cam2_info_sock'
                    # 发送JSON格式的请求获取交通类别信息
                    traffic_request = {"cmd": "traffic_category"}
                    traffic_request_json = json.dumps(traffic_request)
                    send_data(cam_info_socket, traffic_request_json.encode('utf-8'))
                    response = receive_data(cam_info_socket, 4096)
                    
                    if response:
                        try:
                            # 检查响应是否为有效的JSON
                            right_traffic_data = json.loads(response.decode('utf-8'))
                            logger.info(f"Right camera traffic category data: {right_traffic_data}")
                        except json.JSONDecodeError as e:
                            logger.error(f"Failed to decode right traffic category response: {e}")
                        except Exception as e:
                            logger.error(f"Error processing right traffic category response: {e}")
                
                # Get counting data from CDS - returns separate left and right data
                left_counting_data, right_counting_data = get_cds_counting_data()
                
                # Process left camera data (cam1)
                if cam_in_use == 1 or cam_in_use == 3:
                    if left_counting_data:
                        # Process cumulative data to get period counts for left camera
                        left_period_data = process_cumulative_counting(left_counting_data, "left")
                        # Get speed averages for left camera
                        left_speed_averages = get_speed_data_for_uart("left")
                        # Reformat for UART with speed integration
                        uart_data = reformat_counting_for_uart(left_period_data, left_speed_averages)
                        
                        # 合并交通类别信息到uart_data
                        if left_traffic_data:
                            # 根据实际的交通类别数据结构进行合并
                            # 这里假设left_traffic_data可以直接与uart_data合并
                            uart_data.update(left_traffic_data)
                            
                        response = json.dumps(uart_data)
                        uart.send_serial(response)
                    else:
                        # 如果没有计数数据但有交通类别数据，则使用交通类别数据
                        if left_traffic_data:
                            uart_data = dnn_default_dirct.copy()
                            uart_data.update(left_traffic_data)
                            response = json.dumps(uart_data)
                        else:
                            response = json.dumps(dnn_default_dirct)
                        uart.send_serial(response)
                
                # Process right camera data (cam2)
                if cam_in_use == 2 or cam_in_use == 3:
                    if right_counting_data:
                        # Process cumulative data to get period counts for right camera
                        right_period_data = process_cumulative_counting(right_counting_data, "right")
                        # Get speed averages for right camera
                        right_speed_averages = get_speed_data_for_uart("right")
                        # Reformat for UART with speed integration
                        uart_data = reformat_counting_for_uart(right_period_data, right_speed_averages)
                        
                        # 合并交通类别信息到uart_data
                        if right_traffic_data:
                            # 根据实际的交通类别数据结构进行合并
                            # 这里假设right_traffic_data可以直接与uart_data合并
                            uart_data.update(right_traffic_data)
                            
                        response = json.dumps(uart_data)
                        uart.send_serial(response)
                    else:
                        # 如果没有计数数据但有交通类别数据，则使用交通类别数据
                        if right_traffic_data:
                            uart_data = dnn_default_dirct.copy()
                            uart_data.update(right_traffic_data)
                            response = json.dumps(uart_data)
                        else:
                            response = json.dumps(dnn_default_dirct)
                        uart.send_serial(response)
                
                # Reset speed data for next cycle
                reset_speed_data()

            elif string[:3] == "?PS":
                index = int(string[3:])
                if index in [1, 2]:
                    # 处理PS1和PS2命令
                    if (index == 1 and (cam_in_use == 1 or cam_in_use == 3)) or (index == 2 and (cam_in_use == 2 or cam_in_use == 3)):
                        # 选择正确的socket
                        if index == 1:
                            cam_info_socket = 'cam1_info_sock'
                        else:  # index == 2
                            cam_info_socket = 'cam2_info_sock'
                        
                        current_time = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                        gain = camera_control_process(cam_info_socket, GET_GAIN, 0)
                        exposure = camera_control_process(cam_info_socket, GET_EXPOSURE, 0)
                        ae_model = camera_control_process(cam_info_socket, GET_AE_MODE, 0)
                        awb_model = camera_control_process(cam_info_socket, GET_AWB_MODE, 0)
                        ae_status = "auto" if ae_model == 0 else "manual"
                        awb_status = "enable" if awb_model == 0 else "disable"
                        ps_data = {
                            "CameraFPS": config["CameraFPS"],
                            "ImageSize": f"{config['InputTensorWidth']}*{config['InputTensorHeith']}",
                            "PixelDepth": config["PixelDepth"],
                            "PixelOrder": config["PixelOrder"],
                            "DNNModel": config["DNNModel"],
                            "PostProcessingLogic": config["PostProcessingLogic"],
                            "SendImageQuality": config["SendImageQuality"],
                            "SendImageSizePercent": config["SendImageSizePercent"],
                            "AEModel": ae_status,
                            "Exposure": exposure,
                            "Gain": gain,
                            "AWBMode": awb_status,
                            "Heating": config["Heating"],
                            "Time": current_time
                        }
                        response = json.dumps(ps_data)
                    else:
                        # 不符合条件时发送空字典
                        response = json.dumps({})
                    uart.send_serial(response)
                elif index in [3, 4]:
                    # 处理PS3和PS4命令
                    if (index == 3 and (cam_in_use == 1 or cam_in_use == 3)) or (index == 4 and (cam_in_use == 2 or cam_in_use == 3)):
                        # 选择正确的socket
                        if index == 3:
                            cam_info_socket = 'cam1_info_sock'
                        else:  # index == 4
                            cam_info_socket = 'cam2_info_sock'
                        # 发送JSON格式的drawing命令
                        roi_request = {"cmd": "drawing"}
                        roi_request_json = json.dumps(roi_request)
                        send_data(cam_info_socket, roi_request_json.encode('utf-8'))
                        response = receive_data(cam_info_socket, 4096)
                        # 解析响应，只提取coordinates部分传给处理函数
                        if response:
                            try:
                                json_response = json.loads(response.decode('utf-8'))
                                coordinates_data = json_response.get('coordinates', {})
                                # 将coordinates数据编码为bytes传给处理函数
                                coordinates_bytes = json.dumps(coordinates_data).encode('utf-8')
                                response = process_coordinates_response(coordinates_bytes)
                            except Exception as e:
                                logger.error(f"Error extracting coordinates: {e}")
                                response = json.dumps({})
                        else:
                            response = json.dumps({})
                    else:
                        # 不符合条件时发送空字典
                        response = json.dumps({})
                    print("----------len(response)", len(response))
                    uart.send_serial(response)
                elif (index - 5) < len(str_image):
                    if index == 5 and emer_mode == 1:
                        emer_imgage_send = 1
                    response = "{\"Block" + str(index - 4) + "\":\"" + str_image[index - 5] + "\"}"
                    uart.send_serial(response)
                    if index == 24 and emer_imgage_send == 1:
                        emer_imgage_send = 0
                        emer_mode = 0
                elif index < 25:
                    response = "{\"Block" + str(index - 4) + "\":\"" + "\"}"
                    uart.send_serial(response)
                    if index == 24 and emer_imgage_send == 1:
                        emer_imgage_send = 0
                        emer_mode = 0
                else:
                    logger.error(f"out of Block -> ?PS{index}")

            logger.debug(f"--- {time.time() - start_time} seconds ---")

def signal_handler(sig, frame):
    """信号处理函数，用于优雅地关闭程序"""
    logger.info("Received signal to shut down...")
    stop_event_server()
    sdk_logout()
    sys.exit(0)

if __name__ == '__main__':
    # 注册信号处理器
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, shutting down...")
        stop_event_server()
        sdk_logout()
    except Exception as e:
        logger.error(f"Unexpected error in main: {e}")
        stop_event_server()
        sdk_logout()
        raise