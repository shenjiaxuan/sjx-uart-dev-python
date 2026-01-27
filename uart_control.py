import socket
import serial
import base64
import time
import math
from PIL import Image
import json
from datetime import datetime
import numpy as np
from pathlib import Path
import mmap
import posix_ipc
import os
from threading import Thread
import threading
import signal
import sys
import logging
from logging.handlers import RotatingFileHandler
import subprocess
import hashlib
import zlib
import shutil

# ================================
# VERSION INFORMATION
# ================================
VERSION = "3.3.1"

# ================================
# CAMERA CONFIGURATION LOGIC
# ================================
# cam_in_use_actual: 实际硬件配置，从gs501.json读取，程序运行期间不变
#   1 = 仅左摄像头可用
#   2 = 仅右摄像头可用  
#   3 = 双摄像头可用
#
# cam_in_use: 当前输出模式，可通过UART命令或config.json配置
#   1 = 输出左摄像头数据
#   2 = 输出右摄像头数据
#   3 = 输出双摄像头数据
#
# 验证规则: cam_in_use必须被cam_in_use_actual支持
#   - 如果actual=3，则in_use可以是1,2,3
#   - 如果actual=1，则in_use只能是1
#   - 如果actual=2，则in_use只能是2
# ================================

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
CAMERA1_PORT = 10808
CAMERA2_PORT = 10809
CAMERA1_SHM_BMP_NAME = "/left_imx501_bmp_shm"
CAMERA2_SHM_BMP_NAME = "/right_imx501_bmp_shm"
SHM_BMP_SIZE = 36936000

# Event Server Configuration (for receiving speed data from SDK)
EVENT_SERVER_IP = "127.0.0.1"
EVENT_SERVER_PORT = 1780  # Port for receiving speed events from SDK
event_server_socket = None
event_server_thread = None

# SDK config
SDK_SERVER_IP = '127.0.0.1'
SDK_JSON_PORT = 1880
SDK_USER_NAME = "sdk_user"
SDK_USER_PASSWD = "sdk_password"
sdk_token = None
sdk_token_lock = threading.Lock()

# Firmware update config
UNIT_CONFIG_PATH = '/home/root/AglaiaSense/resource/share_config/gs501.json'
HOST_DEVM_UPDATE = 'localhost'
PORT_DEVM_UPDATE = 20808

# define pic size
IMAGE_CHANNELS = 3
IMAGE_HEIGHT = 300
IMAGE_WIDTH = 300

# AppNumber definitions
APP_NUMBER_ASSET = "698"
APP_NUMBER_TRAFFIC = "699"

send_max_length = 980
max_image_blocks = 20  # 最大图像块数量，默认20，最大80
count_interval = "300"
profile_index = 3
emer_mode = 0  # corrected from ener_mode
str_image = []
emer_imgage_send = 0

dnn_default_dirct = {"spdunit":"KPH","incar":-1,"incarspd":-1,"inbus":-1,"inbusspd":-1,"inped":-1,"inpedspd":-1,"incycle":-1,"incyclespd":-1,"intruck":-1,"intruckspd":-1,"outcar":-1,"outcarspd":-1,"outbus":-1,"outbusspd":-1,"outped":-1,"outpedspd":-1,"outcycle":-1,"outcyclespd":-1,"outtruck":-1,"outtruckspd":-1}

sockets = {
    'cam1_info_sock': None,
    'cam2_info_sock': None
}


# Declare globals for shared memory pointers and cam_in_use to be accessible in other functions
cam1_image_shm_ptr = None
cam2_image_shm_ptr = None
cam_in_use = 1
cam_in_use_actual = 1  # Actual hardware configuration from gs501.json

# CDS related globals
previous_counting_data_left = {}
previous_counting_data_right = {}
cds_alerts_received = False

# 新增：缓存从SDK推送过来的counting数据
latest_counting_data_left = {}
latest_counting_data_right = {}
counting_data_lock = threading.Lock()

# Speed data globals
speed_data_left = {}  # {direction_class: [speed_values]}
speed_data_right = {}
speed_averages_left = {}  # {direction_class: average_speed}
speed_averages_right = {}
speed_counts_left = {}  # {direction_class: count}
speed_counts_right = {}
speed_data_lock = threading.Lock()

# File transfer globals
FILE_RECV_BLOCK_SIZE = 650  # Bytes per block (before Base64 encoding, ensures JSON < 1000 bytes)
file_recv_state = {
    "active": False,
    "filename": "",
    "total_blocks": 0,
    "received_blocks": set(),
    "expected_md5": "",
    "temp_file": None,
    "temp_path": ""
}

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

def kill_main_processes():
    """杀掉所有./main进程"""
    try:
        # 查找所有./main进程
        result = subprocess.run(['ps', '-aux'], capture_output=True, text=True)
        processes = result.stdout.split('\n')

        killed_count = 0
        for process in processes:
            if './main' in process and 'grep' not in process:
                # 提取PID（第二列）
                parts = process.split()
                if len(parts) >= 2:
                    pid = parts[1]
                    try:
                        subprocess.run(['kill', '-9', pid], check=True)
                        logger.info(f"Killed ./main process with PID: {pid}")
                        killed_count += 1
                    except subprocess.CalledProcessError as e:
                        logger.error(f"Failed to kill process {pid}: {e}")

        logger.info(f"Total ./main processes killed: {killed_count}")
        return killed_count > 0
    except Exception as e:
        logger.error(f"Error killing main processes: {e}")
        return False

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
        sdk_token = response.get("token")
        logger.info("SDK login successful")
        return sdk_token
    else:
        logger.error(f"SDK login failed: {response}")
        sdk_token = None
        return None

def sdk_logout():
    """SDK 登出"""
    global sdk_token
    if sdk_token:
        request = {"cmd": "user_logout_req", "token": sdk_token}
        response = send_json_request(request)
        logger.info(f"SDK logout response: {response}")
        sdk_token = None

# 注释掉：SDK不再校验token，不需要心跳机制
# def sdk_heartbeat():
#     """发送心跳保持连接"""
#     global sdk_token
#
#     if sdk_token:
#         request = {"cmd": "heartbeat_req", "token": sdk_token}
#         response = send_json_request(request)
#         if response and response.get("ret_code") != 0:
#             logger.warning("SDK heartbeat failed, need to re-login")
#             # 心跳失败，尝试重新登录
#             if sdk_login():  # sdk_login() 会直接设置全局 sdk_token
#                 logger.info("SDK re-login successful after heartbeat failure")
#                 return True
#             else:
#                 logger.error("SDK re-login failed after heartbeat failure")
#                 return False
#         return True
#     else:
#         # Token不存在，尝试登录
#         if sdk_login():  # sdk_login() 会直接设置全局 sdk_token
#             logger.info("SDK login successful in heartbeat")
#             return True
#         return False
#
# def sdk_heartbeat_thread():
#     """心跳线程，定期发送心跳"""
#     while True:
#         try:
#             sdk_heartbeat()
#             time.sleep(30)  # 每30秒发送一次心跳
#         except Exception as e:
#             logger.error(f"SDK heartbeat thread error: {e}")
#             time.sleep(30)

def sdk_set_event_server_info(server_ip, server_port):
    """设置事件服务器信息"""
    if not sdk_token:
        logger.warning("No valid token available for set_event_server_info")
        return False

    request = {
        "cmd": "set_event_server_info_req",
        "token": sdk_token,
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

def sdk_get_camera_param(camera_id):
    """从 SDK 获取摄像头参数"""
    if not sdk_token:
        logger.warning("No valid token available for get_camera_param")
        return None

    # 根据 camera_id 确定使用的摄像头标识
    if camera_id == CAM1_ID:
        camera_name = "left"
    elif camera_id == CAM2_ID:
        camera_name = "right"
    else:
        logger.error(f"Invalid camera_id for SDK camera param: {camera_id}")
        return None

    request = {"cmd": "get_camera_param_req", "camera_id": camera_name, "token": sdk_token}
    response = send_json_request(request)
    if response and response.get("cmd") == "get_camera_param_rsp" and response.get("ret_code") == 0:
        logger.info(f"SDK camera param data: {response}")
        return response
    else:
        logger.error(f"Failed to get camera param from SDK: {response}")
        return None

def sdk_get_hardware_status(modules=None):
    """从SDK获取硬件状态"""
    if not sdk_token:
        logger.warning("No valid token available for get_hardware_status")
        return None

    request = {"cmd": "get_hardware_status_req", "token": sdk_token}
    if modules:
        request["modules"] = modules
    response = send_json_request(request)
    if response and response.get("cmd") == "get_hardware_status_rsp" and response.get("ret_code") == 0:
        return response
    else:
        logger.error(f"Failed to get hardware status from SDK: {response}")
        return None

def sdk_set_hardware_status(module, status):
    """通过SDK设置硬件状态"""
    if not sdk_token:
        logger.warning("No valid token available for set_hardware_status")
        return False

    request = {
        "cmd": "set_hardware_status_req",
        "token": sdk_token,
        "module": module,
        "status": status
    }
    response = send_json_request(request)

    if response and response.get("cmd") == "set_hardware_status_rsp" and response.get("ret_code") == 0:
        logger.info(f"Successfully set hardware status: {module}={status}")
        return True
    else:
        logger.error(f"Failed to set hardware status: {response}")
        return False

def get_wifi_status_from_sdk():
    """通过SDK获取WiFi状态"""
    modules = ["wifi"]
    hardware_status = sdk_get_hardware_status(modules)
    if hardware_status:
        wifi_status = hardware_status.get("wifi_status", "disabled")
        return wifi_status
    return None

def set_wifi_status_via_sdk(enable):
    """通过SDK设置WiFi状态"""
    status = "open" if enable else "close"
    return sdk_set_hardware_status("wifi", status)

def get_lte_status_from_sdk():
    """通过SDK获取LTE状态"""
    modules = ["lte"]
    hardware_status = sdk_get_hardware_status(modules)
    if hardware_status:
        lte_status = hardware_status.get("lte_status", "disabled")
        return lte_status
    return "disabled"

def set_lte_status_via_sdk(enable):
    """通过SDK设置LTE状态"""
    status = "open" if enable else "close"
    return sdk_set_hardware_status("lte", status)

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

def get_cds_counting_data():
    """从缓存获取计数数据（不再主动调用SDK，而是使用推送的数据）"""
    left_counting_data = {}
    right_counting_data = {}

    with counting_data_lock:
        if cam_in_use == 1 or cam_in_use == 3:  # 左摄像头
            left_counting_data = latest_counting_data_left.copy()

        if cam_in_use == 2 or cam_in_use == 3:  # 右摄像头
            right_counting_data = latest_counting_data_right.copy()

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

def create_uart_data_from_traffic_categories(traffic_data):
    """
    根据交通类别信息创建基础的uart_data
    支持的类别默认值为0，不支持的类别为-1
    """
    # 从默认值开始（所有值都是-1，表示不支持）
    uart_data = dnn_default_dirct.copy()
    
    # 获取line_categories列表
    categories = traffic_data.get("categories", {})
    line_categories = categories.get("line_categories", [])
    
    # 车辆类型映射
    vehicle_mapping = {
        'car': 'car',
        'truck': 'truck', 
        'bus': 'bus',
        'pedestrian': 'ped',
        'cycle': 'cycle'
    }
    
    # 收集所有可能的类型（用于设置基础支持）
    all_supported_types = set()
    for category_str in line_categories:
        categories_list = category_str.split("-")
        for category in categories_list:
            if category in vehicle_mapping:
                all_supported_types.add(vehicle_mapping[category])
    
    # 根据支持的类别设置默认值为0
    for mapped_type in all_supported_types:
        uart_data[f"in{mapped_type}"] = 0
        uart_data[f"in{mapped_type}spd"] = 0
        uart_data[f"out{mapped_type}"] = 0
        uart_data[f"out{mapped_type}spd"] = 0
    
    # 存储line_categories信息用于后续处理
    create_uart_data_from_traffic_categories.line_categories = line_categories
    create_uart_data_from_traffic_categories.vehicle_mapping = vehicle_mapping
    
    return uart_data

def get_supported_types_for_boundary(boundary_name, line_categories, vehicle_mapping):
    """
    根据boundary名称推断其对应的line索引和支持的类型
    boundary命名规则：boundary_<index>_<direction>
    """
    try:
        # 从boundary名称中提取line索引
        # 例如：boundary_1_in -> line_index = 0 (从1开始的索引转换为从0开始)
        parts = boundary_name.split('_')
        if len(parts) >= 2 and parts[1].isdigit():
            line_index = int(parts[1]) - 1  # 转换为从0开始的索引
            
            if 0 <= line_index < len(line_categories):
                supported_categories = line_categories[line_index].split("-")
                supported_types = set()
                for category in supported_categories:
                    if category in vehicle_mapping:
                        supported_types.add(vehicle_mapping[category])
                return supported_types
    except Exception as e:
        logger.debug(f"Error parsing boundary name {boundary_name}: {e}")
    
    # 如果无法解析boundary名称，返回空集合（不支持任何类型）
    return set()

def reformat_counting_for_uart(counting_results, speed_averages, base_uart_data=None):
    """Reformat counting data for UART and integrate speed averages"""
    if base_uart_data is None:
        uart_data = dnn_default_dirct.copy()
    else:
        uart_data = base_uart_data.copy()
    
    # 获取line_categories信息
    line_categories = getattr(create_uart_data_from_traffic_categories, 'line_categories', [])
    vehicle_mapping = getattr(create_uart_data_from_traffic_categories, 'vehicle_mapping', {
        'car': 'car', 'truck': 'truck', 'bus': 'bus', 'pedestrian': 'ped', 'cycle': 'cycle'
    })
    
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
            
            # 获取当前boundary支持的类型
            supported_types = get_supported_types_for_boundary(boundary, line_categories, vehicle_mapping)
            
            # 如果无法确定支持的类型，则处理所有类型（向后兼容）
            if not supported_types:
                logger.debug(f"Could not determine supported types for boundary {boundary}, processing all types")
                supported_types = set(vehicle_mapping.values())
            
            for vehicle_type, count in counts.items():
                if vehicle_type in vehicle_mapping:
                    mapped_type = vehicle_mapping[vehicle_type]
                    
                    # 修复：只处理当前boundary支持的类型
                    if mapped_type not in supported_types:
                        logger.debug(f"Skipping unsupported type {mapped_type} for boundary {boundary}")
                        continue
                    
                    uart_key = direction + mapped_type
                    speed_key = uart_key + "spd"
                    
                    if uart_key in uart_data and uart_data[uart_key] != -1:  # 只处理支持的类别
                        # 修复：累加计数而不是覆盖
                        uart_data[uart_key] += count
                        
                        # Set speed based on count and averages
                        direction_class = direction + mapped_type
                        if count > 0 and direction_class in speed_averages:
                            uart_data[speed_key] = int(round(speed_averages[direction_class]))
                        elif uart_data[uart_key] == 0:
                            uart_data[speed_key] = 0  # 计数为0时速度为0
                        else:
                            # 如果有计数但没有速度数据，保持原有的速度值
                            if uart_data[speed_key] == -1:
                                uart_data[speed_key] = 0
                        
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

def load_config(path):
    with open(path, 'r') as file:
        return json.load(file)

# def save_config(path, config):
#     """保存配置到JSON文件，使用原子写入确保安全"""
#     try:
#         # 先写入临时文件
#         temp_path = path + '.tmp'
#         with open(temp_path, 'w', encoding='utf-8') as file:
#             json.dump(config, file, indent=4, ensure_ascii=False)

#         # 原子性地替换原文件
#         os.replace(temp_path, path)
#         return True
#     except Exception as e:
#         logger.error(f"Failed to save config to {path}: {e}")
#         # 清理临时文件
#         if os.path.exists(temp_path):
#             try:
#                 os.remove(temp_path)
#             except:
#                 pass
#         return False

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
        # 读取gs501.json配置文件来确定UART端口
        try:
            config = load_config(CONFIG_PATH)
            hw_name = config.get("HWName", "")
            
            # 根据HWName决定使用哪个串口
            if hw_name == "AS_8MP":
                uart_port = "/dev/ttymxc3"
            else:
                uart_port = "/dev/ttymxc2"  # 默认端口
            
            logger.info(f"Using UART port {uart_port} for HWName: {hw_name}")
            
        except Exception as e:
            logger.error(f"Failed to read HWName from config, using default port: {e}")
            uart_port = "/dev/ttymxc2"
        
        self.uartport = serial.Serial(
                port=uart_port,
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
    # 根据最大图像块数量动态计算目标大小
    # Base64 编码率 4/3，所以原始数据 = Base64大小 × 0.75
    target_size = int(max_image_blocks * send_max_length * 0.75)
    filepath = './tmp/converted-jpg-image.jpg'

    # 根据 target_size 分段设置初始 quality
    if cam_in_use == 3:  # 双摄像头
        if target_size < 20000:
            quality = 20    # 小容量：低质量
        elif target_size < 40000:
            quality = 60    # 中容量：中等质量
        else:
            quality = 85    # 大容量：高质量
    else:  # 单摄像头
        if target_size < 20000:
            quality = 35    # 小容量：低质量
        elif target_size < 40000:
            quality = 80    # 中容量：中等质量
        else:
            quality = 95    # 大容量：高质量
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
    
    # 打印图像块数信息
    logger.info(f"Image saved and split into {len(str_image)} blocks (total size: {str_len} bytes, block size: {send_max_length} bytes)")

def handle_assetmnt_alert(camera_id):
    """处理ASSETMNT事件（资产评估/行人报警）- 在独立线程中执行"""
    global cds_alerts_received, emer_mode, cam1_image_shm_ptr, cam2_image_shm_ptr, cam_in_use

    # 验证报警来源的相机是否与当前使用的相机配置匹配
    should_process_alert = False
    if camera_id == "left" and (cam_in_use == 1 or cam_in_use == 3):
        should_process_alert = True
        logger.info(f"Processing ASSETMNT alert from left camera (cam_in_use={cam_in_use})")
    elif camera_id == "right" and (cam_in_use == 2 or cam_in_use == 3):
        should_process_alert = True
        logger.info(f"Processing ASSETMNT alert from right camera (cam_in_use={cam_in_use})")
    else:
        logger.info(f"Ignoring ASSETMNT alert from {camera_id} camera (cam_in_use={cam_in_use})")

    if should_process_alert:
        cds_alerts_received = True
        # Set emergency mode when alert received
        emer_mode = 1
        logger.info(f"emer_mode set to {emer_mode} by ASSETMNT alert from {camera_id} camera")

        # Save images to buffer when emer_mode is set to 1
        if cam_in_use == 1 or cam_in_use == 3:
            get_pic_from_socket(cam1_image_shm_ptr, CAM1_ID)
        if cam_in_use == 2 or cam_in_use == 3:
            get_pic_from_socket(cam2_image_shm_ptr, CAM2_ID)
        update_sim_attribute(cam_in_use)

def handle_sdk_client_connection(client_socket, client_address):
    """处理来自SDK的单个客户端连接"""
    logger.info(f"SDK client connected from {client_address}")
    global cds_alerts_received, emer_mode, cam1_image_shm_ptr, cam2_image_shm_ptr, cam_in_use
    global latest_counting_data_left, latest_counting_data_right

    buffer = ""  # 接收缓冲区

    try:
        while True:
            data = client_socket.recv(40960)
            if not data:
                break

            # 累积数据到缓冲区
            buffer += data.decode('utf-8')

            # 按换行符分割处理所有完整的消息
            while '\n' in buffer:
                line, buffer = buffer.split('\n', 1)
                line = line.strip()

                # 跳过空行
                if not line:
                    continue

                try:
                    message = json.loads(line)
                    event_type = message.get("event_type")
                    camera_id = message.get("camera_id", "unknown")

                    # 处理 SPEED 事件
                    if event_type == "TRFFSPED":
                        cds_data = message.get("cds_data", {})
                        outputs = cds_data.get("outputs", [])

                        if outputs and len(outputs) > 0:
                            speed_event = outputs[0].get("speed_event", {})
                            # 在独立线程中处理速度数据，避免阻塞消息接收
                            speed_thread = threading.Thread(
                                target=process_speed_data,
                                args=(speed_event, camera_id),
                                daemon=True
                            )
                            speed_thread.start()

                    # 处理 TRFFCCNT 事件（计数）
                    elif event_type == "TRFFCCNT":
                        cds_data = message.get("cds_data", {})
                        outputs = cds_data.get("outputs", [])

                        if outputs and len(outputs) > 0:
                            counting_results = outputs[0].get("counting_results", {})

                            # 缓存 counting 数据
                            with counting_data_lock:
                                if camera_id == "left":
                                    latest_counting_data_left = counting_results
                                elif camera_id == "right":
                                    latest_counting_data_right = counting_results

                    # 处理 ASSETMNT 事件（资产评估/行人报警）
                    elif event_type == "ASSETMNT":
                        logger.info(f"Received ASSETMNT alert from {client_address}: camera={camera_id}")
                        # 在独立线程中处理报警事件，避免阻塞消息接收
                        alert_thread = threading.Thread(
                            target=handle_assetmnt_alert,
                            args=(camera_id,),
                            daemon=True
                        )
                        alert_thread.start()

                    # 其他事件类型
                    elif event_type == "parking":
                        logger.info(f"Received parking event")
                    else:
                        logger.info(f"Received unknown event type '{event_type}'")

                except json.JSONDecodeError as e:
                    logger.error(f"Failed to decode JSON from SDK client {client_address}: {e}, line: {line}")
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

def validate_cam_in_use(requested_cam_in_use, actual_cam_in_use):
    """
    验证请求的相机配置是否被实际硬件支持

    Args:
        requested_cam_in_use (int): 请求的相机配置 (1=左, 2=右, 3=双摄)
        actual_cam_in_use (int): 实际硬件配置 (1=仅左, 2=仅右, 3=双摄)

    Returns:
        bool: True if supported, False otherwise
    """
    # 双摄硬件支持所有配置
    if actual_cam_in_use == 3:
        return requested_cam_in_use in [1, 2, 3]

    # 单摄硬件只支持对应的配置
    return requested_cam_in_use == actual_cam_in_use

# ================================
# FILE TRANSFER FUNCTIONS
# ================================

# Calculate the md5 value of the file
def calculate_md5(filename, block_size=4096):
    md5 = hashlib.md5()
    with open(filename, 'rb') as f:
        for block in iter(lambda: f.read(block_size), b''):
            md5.update(block)
    return md5.hexdigest()

def has_zip_file(directory_path):
        """Check if there are any ZIP files in the specified directory."""
        try:
            # Validate if the given path is a directory
            if not os.path.isdir(directory_path):
                logger.info(f"The provided path '{directory_path}' is not a directory.\n")
                return False

            # List all files in the directory and check for .zip files
            for item in os.listdir(directory_path):
                if item.lower().endswith('.zip'):
                    logger.error(f"Found ZIP file: {item}\n")
                    return True

            logger.info("No ZIP files found in the directory.\n")
            return False

        except Exception as e:
            logger.error(f"An error occurred while checking for ZIP files: {e}\n")
            return False

def copy_and_verify(src_path, dest_path, src_md5):
    """拷贝文件并验证MD5,成功则删除原文件"""
    src_path = Path(src_path)
    dest_path = Path(dest_path)

    # 检查源文件是否存在
    if not src_path.exists():
        raise FileNotFoundError(f"Source file {src_path} does not exist.")

    # 拷贝文件
    try:
        shutil.copy2(src_path, dest_path)
        logger.info(f"File copied from {src_path} to {dest_path}")
    except Exception as e:
        raise Exception(f"Error copying file: {e}")

    # 校验MD5
    dest_md5 = calculate_md5(dest_path)

    if src_md5 == dest_md5:
        logger.info(f"MD5 match: Copy verified successfully.")
        # 删除源文件
        try:
            # 创建文件并写入 dest_path 的 MD5 值
            md5_file_path = dest_path.with_suffix('.md5')  # 使用与目标文件相同的名称，但扩展名为 .md5
            with open(md5_file_path, 'w') as md5_file:
                md5_file.write(f"{dest_md5}\n")  # 写入 MD5 值
                logger.info(f"MD5 value written to {md5_file_path}")

            src_path.unlink()
            logger.info(f"Source file {src_path} deleted successfully.")
        except Exception as e:
            logger.error(f"Error deleting source file: {e}")
    else:
        logger.error(f"MD5 mismatch: File copy failed.")
        # 删除目标文件
        try:
            dest_path.unlink()
            logger.info(f"Copied file {dest_path} deleted.")
        except Exception as e:
            logger.error(f"Error deleting copied file: {e}")

def start_update_program(file_path):
    try:
        logger.info(f"[start_update_program]: start connect to server {HOST_DEVM_UPDATE}:{PORT_DEVM_UPDATE}\n")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(120)   # time out 120S
            logger.info(f"[start_update_program]: start connect to server localhost:{PORT_DEVM_UPDATE}\n")
            server_address = ("localhost", PORT_DEVM_UPDATE)
            s.connect(server_address)
            logger.info("[start_update_program]: connect to server\n")

    except KeyboardInterrupt:
        logger.error("[start_update_program]: Manual Close...\n")
        return False
    except Exception as e:
        logger.error(f"[start_update_program]: disconnect of server: {e}\n")
        return False
    return True

def handle_json_command(uart, cmd):
    """Handle JSON format commands for file transfer"""
    global file_recv_state

    cmd_type = cmd.get("cmd")

    if cmd_type == "file_start":
        handle_file_start(uart, cmd)
    elif cmd_type == "file_block":
        handle_file_block(uart, cmd)
    elif cmd_type == "file_end":
        handle_file_end(uart)
    elif cmd_type == "file_cancel":
        handle_file_cancel(uart)
    else:
        logger.warning(f"Unknown JSON command: {cmd_type}")

def handle_file_start(uart, cmd):
    """Handle file transfer start command"""
    global file_recv_state

    try:
        # Check if there's already an active transfer
        if file_recv_state["active"]:
            response = {
                "cmd": "file_start",
                "status": "error",
                "reason": "transfer_in_progress"
            }
            uart.send_serial(json.dumps(response))
            return

        # Extract parameters
        filename = cmd.get("name", "unnamed_file")
        total_blocks = cmd.get("blocks", 0)
        expected_md5 = cmd.get("md5", "")
        file_size = cmd.get("size", 0)

        # Check disk space
        temp_dir = "./tmp"
        try:
            # Create temp directory if not exists
            Path(temp_dir).mkdir(parents=True, exist_ok=True)

            stat = os.statvfs(temp_dir)
            free_space = stat.f_bavail * stat.f_frsize
            if free_space < file_size * 1.2:  # Need 1.2x space for safety
                response = {
                    "cmd": "file_start",
                    "status": "error",
                    "reason": "disk_full"
                }
                uart.send_serial(json.dumps(response))
                return
        except Exception as e:
            logger.warning(f"Could not check disk space: {e}")

        # Create temporary file (use fixed name for single session)
        temp_path = f"{temp_dir}/file_recv_current.tmp"
        temp_file = open(temp_path, "wb")

        # Initialize state
        file_recv_state = {
            "active": True,
            "filename": filename,
            "total_blocks": total_blocks,
            "received_blocks": set(),
            "expected_md5": expected_md5,
            "temp_file": temp_file,
            "temp_path": temp_path
        }

        # Return success response
        response = {
            "cmd": "file_start",
            "status": "ready"
        }
        uart.send_serial(json.dumps(response))
        logger.info(f"File transfer started: {filename}, {total_blocks} blocks")

    except Exception as e:
        logger.error(f"Error in file_start: {e}")
        response = {
            "cmd": "file_start",
            "status": "error",
            "reason": str(e)
        }
        uart.send_serial(json.dumps(response))

def handle_file_block(uart, cmd):
    """Handle file data block with CRC32 verification"""
    global file_recv_state

    try:
        if not file_recv_state["active"]:
            response = {
                "cmd": "file_block",
                "status": "error",
                "reason": "no_active_transfer"
            }
            uart.send_serial(json.dumps(response))
            return

        block_index = cmd.get("index", -1)
        expected_crc = cmd.get("crc32", "")
        base64_data = cmd.get("data", "")

        # Base64 decode
        try:
            binary_data = base64.b64decode(base64_data)
        except Exception as e:
            logger.error(f"Base64 decode error at block {block_index}: {e}")
            response = {
                "cmd": "file_block",
                "index": block_index,
                "status": "error",
                "reason": "invalid_base64",
                "retry": True
            }
            uart.send_serial(json.dumps(response))
            return

        # Calculate CRC32
        actual_crc = format(zlib.crc32(binary_data) & 0xffffffff, '08x')

        # Verify CRC32
        if actual_crc != expected_crc:
            logger.warning(f"CRC mismatch at block {block_index}: expected {expected_crc}, got {actual_crc}")
            response = {
                "cmd": "file_block",
                "index": block_index,
                "status": "error",
                "reason": "crc_mismatch",
                "retry": True
            }
            uart.send_serial(json.dumps(response))
            return

        # Verify block order (must be sequential)
        expected_index = len(file_recv_state["received_blocks"])

        if block_index < expected_index:
            # Duplicate block (already received)
            logger.warning(f"Duplicate block {block_index}, already received (expected {expected_index})")
            response = {
                "cmd": "file_block",
                "index": block_index,
                "status": "ok"  # Return ok to avoid sender retrying
            }
            uart.send_serial(json.dumps(response))
            return

        if block_index > expected_index:
            # Missing blocks detected
            logger.error(f"Block order error: received {block_index}, expected {expected_index} (missing blocks!)")
            response = {
                "cmd": "file_block",
                "index": block_index,
                "status": "error",
                "reason": "out_of_order",
                "expected": expected_index,
                "retry": False  # Protocol error, should not retry
            }
            uart.send_serial(json.dumps(response))
            return

        # Write to file sequentially (no seek needed)
        temp_file = file_recv_state["temp_file"]
        bytes_written = temp_file.write(binary_data)
        temp_file.flush()

        # Verify write was successful
        if bytes_written != len(binary_data):
            logger.error(f"Write error at block {block_index}: wrote {bytes_written}, expected {len(binary_data)}")
            response = {
                "cmd": "file_block",
                "index": block_index,
                "status": "error",
                "reason": "write_failed",
                "retry": False
            }
            uart.send_serial(json.dumps(response))
            return

        # Record received block
        file_recv_state["received_blocks"].add(block_index)

        # Return success
        response = {
            "cmd": "file_block",
            "index": block_index,
            "status": "ok"
        }
        uart.send_serial(json.dumps(response))

        # Log progress every 50 blocks
        if block_index % 50 == 0 or block_index == file_recv_state["total_blocks"] - 1:
            progress = len(file_recv_state["received_blocks"])
            total = file_recv_state["total_blocks"]
            percent = progress * 100.0 / total if total > 0 else 0
            logger.info(f"File transfer progress: {progress}/{total} ({percent:.1f}%)")

    except Exception as e:
        logger.error(f"Error in file_block: {e}")
        response = {
            "cmd": "file_block",
            "index": block_index,
            "status": "error",
            "reason": str(e),
            "retry": False
        }
        uart.send_serial(json.dumps(response))

def handle_file_end(uart):
    """Handle file transfer end and verify MD5"""
    global file_recv_state

    try:
        if not file_recv_state["active"]:
            response = {
                "cmd": "file_end",
                "status": "error",
                "reason": "no_active_transfer"
            }
            uart.send_serial(json.dumps(response))
            return

        # Close temporary file
        temp_file = file_recv_state["temp_file"]
        temp_file.close()

        # Verify file size and block count
        temp_file_size = os.path.getsize(file_recv_state["temp_path"])
        received_block_count = len(file_recv_state["received_blocks"])
        expected_block_count = file_recv_state["total_blocks"]

        logger.info(f"Transfer statistics:")
        logger.info(f"  Received blocks: {received_block_count}/{expected_block_count}")
        logger.info(f"  File size: {temp_file_size} bytes")

        # Check for missing blocks
        if received_block_count != expected_block_count:
            missing_blocks = set(range(expected_block_count)) - file_recv_state["received_blocks"]
            logger.error(f"Missing {len(missing_blocks)} blocks: {sorted(list(missing_blocks))[:10]}...")
            response = {
                "cmd": "file_end",
                "status": "error",
                "reason": "incomplete_transfer",
                "received": received_block_count,
                "expected": expected_block_count
            }
            uart.send_serial(json.dumps(response))
            # Clean up temporary file
            try:
                os.remove(file_recv_state["temp_path"])
            except:
                pass
            file_recv_state["active"] = False
            return

        # Calculate MD5
        logger.info(f"Calculating MD5 for {temp_file_size} bytes...")
        with open(file_recv_state["temp_path"], "rb") as f:
            actual_md5 = hashlib.md5(f.read()).hexdigest()

        expected_md5 = file_recv_state["expected_md5"]
        logger.info(f"MD5 comparison:")
        logger.info(f"  Expected: {expected_md5}")
        logger.info(f"  Actual:   {actual_md5}")

        # Verify MD5
        if actual_md5 != expected_md5:
            logger.error(f"MD5 mismatch: expected {expected_md5}, got {actual_md5}")
            response = {
                "cmd": "file_end",
                "status": "error",
                "reason": "md5_mismatch",
                "expected": expected_md5,
                "actual": actual_md5
            }
            uart.send_serial(json.dumps(response))
            # Clean up temporary file
            try:
                os.remove(file_recv_state["temp_path"])
            except:
                pass
            file_recv_state["active"] = False
            return

        # Move to final location
        final_path = f"./tmp/{file_recv_state['filename']}"
        # Remove old file if exists
        if os.path.exists(final_path):
            os.remove(final_path)
        os.rename(file_recv_state["temp_path"], final_path)
        file_size = os.path.getsize(final_path)

        # Return success
        response = {
            "cmd": "file_end",
            "status": "success",
            "md5": actual_md5,
            "path": final_path,
            "size": file_size
        }
        uart.send_serial(json.dumps(response))
        logger.info(f"File transfer completed successfully: {final_path} ({file_size} bytes, MD5: {actual_md5})")

        # Firmware update logic (optional, only for ZIP files)
        try:
            filename = file_recv_state["filename"]
            if filename.lower().endswith('.zip'):
                logger.info(f"ZIP file detected, checking for firmware update...")

                update_res_path = None
                with open(UNIT_CONFIG_PATH, 'r') as file:
                    unit_config = json.load(file)
                    update_res_path = unit_config.get('DEVM_UPDATE_RES_PATH')

                download_path = Path(update_res_path)
                download_path.mkdir(parents=True, exist_ok=True)
                application_dst_path = Path(update_res_path) / filename

                if not has_zip_file(update_res_path):
                    copy_and_verify(final_path, application_dst_path, actual_md5)
                    logger.info(f"update_res_path application_dst_path is {application_dst_path}")
                    start_update_program(application_dst_path)

        except Exception as e:
            logger.error(f"Error during firmware update process: {e}")

        # Reset state
        file_recv_state["active"] = False

    except Exception as e:
        logger.error(f"Error in file_end: {e}")
        response = {
            "cmd": "file_end",
            "status": "error",
            "reason": str(e)
        }
        uart.send_serial(json.dumps(response))
        file_recv_state["active"] = False

def handle_file_cancel(uart):
    """Cancel file transfer and clean up"""
    global file_recv_state

    if file_recv_state["active"]:
        # Close and delete temporary file
        try:
            if file_recv_state["temp_file"]:
                file_recv_state["temp_file"].close()
            if os.path.exists(file_recv_state["temp_path"]):
                os.remove(file_recv_state["temp_path"])
        except Exception as e:
            logger.error(f"Error cleaning up: {e}")

        file_recv_state["active"] = False
        logger.info("File transfer cancelled")

    response = {
        "cmd": "file_cancel",
        "status": "cancelled"
    }
    uart.send_serial(json.dumps(response))

def main():
    """
    Main function to initialize logger, UART, load config, start socket connection
    and handle UART commands.
    """
    global count_interval, profile_index, emer_mode
    global IMAGE_HEIGHT, IMAGE_WIDTH, cam_in_use, cam_in_use_actual
    global cam1_image_shm_ptr, cam2_image_shm_ptr
    global emer_imgage_send, max_image_blocks

    # 打印当前版本
    logger.info("===========================================")
    logger.info(f"UART Control Service Version: {VERSION}")
    logger.info("===========================================")

    uart = UART()
    
    # Step 1: Read actual hardware configuration from gs501.json
    config = load_config(CONFIG_PATH)
    IMAGE_HEIGHT = int(config.get('InputTensorHeith'))
    IMAGE_WIDTH = int(config.get('InputTensorWidth'))
    
    # 确定实际硬件配置 - 程序运行期间不会改变
    sensor_num_actual_str = config.get("SensorNum", "dual")
    if sensor_num_actual_str == "left":
        cam_in_use_actual = 1  # 仅左摄像头可用
    elif sensor_num_actual_str == "right":
        cam_in_use_actual = 2  # 仅右摄像头可用
    elif sensor_num_actual_str == "dual":
        cam_in_use_actual = 3  # 双摄像头可用
    else:
        logger.error(f"Invalid SensorNum in gs501.json: {sensor_num_actual_str}, defaulting to all camera")
        cam_in_use_actual = 3
    
    logger.info(f"Hardware configuration (fixed): {cam_in_use_actual} ({['', 'Left only', 'Right only', 'Dual cameras'][cam_in_use_actual]})")

    # Step 2: Initialize SDK connection
    logger.info("Initializing SDK connection...")
    initial_token = sdk_login()
    if not initial_token:
        logger.error("Failed to login to SDK, but continuing...")
    
    # Start SDK heartbeat thread
    # 注释掉：SDK不再校验token，不需要心跳机制
    # heartbeat_thread = Thread(target=sdk_heartbeat_thread)
    # heartbeat_thread.daemon = True
    # heartbeat_thread.start()

    # Start event server to receive event data from SDK
    logger.info("Starting event server for SDK event data...")
    event_server_thread = Thread(target=start_event_server)
    event_server_thread.daemon = True
    event_server_thread.start()

    # Set event server info in SDK
    if not sdk_set_event_server_info(EVENT_SERVER_IP, EVENT_SERVER_PORT):
        logger.warning("Failed to set event server info in SDK, but continuing...")

    # Step 3: 根据实际硬件配置初始化所有可用摄像头
    if cam_in_use_actual == 1 or cam_in_use_actual == 3:  # 左摄像头可用 (actual=1 或 actual=3)
        cam1_info_address = ("localhost", CAMERA1_PORT)
        cam1_info_thread = Thread(target=connect_socket, args=(cam1_info_address, 'cam1_info_sock'))
        cam1_info_thread.daemon = True
        cam1_info_thread.start()
        
        # 初始化左摄像头共享内存
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
        logger.info("Camera1 initialized successfully")
        
    if cam_in_use_actual == 2 or cam_in_use_actual == 3:  # 右摄像头可用 (actual=2 或 actual=3)
        cam2_info_address = ("localhost", CAMERA2_PORT)
        cam2_info_thread = Thread(target=connect_socket, args=(cam2_info_address, 'cam2_info_sock'))
        cam2_info_thread.daemon = True
        cam2_info_thread.start()
        
        # 初始化右摄像头共享内存
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
        logger.info("Camera2 initialized successfully")

    # Step 4: 读取用户配置并验证
    local_config = load_config("config.json")

    # 读取最大图像块数量配置
    max_image_blocks = local_config.get("TotalImageBlocks", 20)
    # 限制在有效范围内 (20-80)
    max_image_blocks = max(20, min(80, max_image_blocks))
    logger.info(f"Max image blocks set to: {max_image_blocks}")

    # 如果配置文件中没有该字段，或值被修正了，写入配置文件
    if "TotalImageBlocks" not in local_config or local_config["TotalImageBlocks"] != max_image_blocks:
        local_config["TotalImageBlocks"] = max_image_blocks
        with open("config.json", "w", encoding="utf-8") as file:
            json.dump(local_config, file, indent=4)
        logger.info(f"TotalImageBlocks saved to config.json: {max_image_blocks}")

    sensor_num_config = local_config.get("cam_in_use", "dual")
    
    if sensor_num_config in ["1", "left"]:
        requested_cam_in_use = 1
    elif sensor_num_config in ["2", "right"]:
        requested_cam_in_use = 2
    elif sensor_num_config in ["3", "dual"]:
        requested_cam_in_use = 3
    else:
        requested_cam_in_use = cam_in_use_actual  # 默认使用实际硬件配置

    # 验证并设置cam_in_use
    if validate_cam_in_use(requested_cam_in_use, cam_in_use_actual):
        cam_in_use = requested_cam_in_use
        profile_index = requested_cam_in_use
        logger.info(f"Camera output mode set to: {cam_in_use}")
    else:
        # 不支持的配置，使用实际硬件配置
        cam_in_use = cam_in_use_actual
        profile_index = cam_in_use_actual
        logger.warning(f"Requested config {requested_cam_in_use} not supported by hardware {cam_in_use_actual}. Using hardware config.")
        
        # 更新config.json
        config_mapping = {1: "left", 2: "right", 3: "dual"}
        local_config["cam_in_use"] = config_mapping[requested_cam_in_use]
        with open("config.json", "w", encoding="utf-8") as file:
            json.dump(local_config, file, indent=4)

    # Step 5: 初始化图像
    update_sim_attribute(cam_in_use)

    # Step 6: UART命令处理主循环
    while True:
        raw_data = uart.receive_serial()
        if raw_data:
            start_time = time.time()
            string = raw_data.decode("utf_8", "ignore").rstrip()
            logger.debug(f"UART recv <-: {string}")

            # Try to parse as JSON command (for file transfer)
            try:
                json_cmd = json.loads(string)
                if isinstance(json_cmd, dict) and "cmd" in json_cmd:
                    # Handle JSON format command
                    handle_json_command(uart, json_cmd)
                    logger.debug(f"--- {time.time() - start_time} seconds ---")
                    continue
            except json.JSONDecodeError:
                pass  # Not JSON, continue with original command parsing

            # Original command handling
            if string == "?Asset":
                asset_data = {
                    "MfrName": config["MfrName"],
                    "ModelNumber": config["ModelNumber"],
                    "SerialNumber": config["SerialNumber"],
                    "MfgDate": config["MfgDate"],
                    "FWVersion": config["FWVersion"],
                    "HWVersion": config["HWVersion"],
                    "AppNumber": config["AppNumber"]
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
                    requested_profile = int(string[8:])
                    
                    # 验证请求的配置是否被硬件支持
                    if validate_cam_in_use(requested_profile, cam_in_use_actual):
                        profile_index = requested_profile
                        cam_in_use = requested_profile
                        
                        # 更新config.json
                        local_config = load_config("config.json")
                        config_mapping = {1: "left", 2: "right", 3: "dual"}
                        local_config["cam_in_use"] = config_mapping[requested_profile]
                        with open("config.json", "w", encoding="utf-8") as file:
                            json.dump(local_config, file, indent=4)
                        
                        logger.info(f"Profile changed to {requested_profile}")
                    else:
                        logger.warning(f"Profile {requested_profile} not supported by hardware {cam_in_use_actual}")
                        
                response = json.dumps({"CamProfile": int(profile_index)})
                uart.send_serial(response)

            elif string[:5] == "WiFi|":
                #这段是原来的wifi控制
                # if get_wifi_status() == 'enabled':
                #     wifi_cur_config = 1
                # else:
                #     wifi_cur_config = 0
                # if string[5:] and int(string[5:]) in [0, 1]:
                #     wifi_status = str(string[5:])
                #     if wifi_cur_config != int(wifi_status):
                #         if int(wifi_status) == 1:
                #             subprocess.run(['nmcli', 'radio', 'wifi', 'on'])
                #         else:
                #             subprocess.run(['nmcli', 'radio', 'wifi', 'off'])
                # 这段是对接sdk的wifi控制，暂时不使用，因为处理速度太慢
                wifi_cur_config = 0
                if get_wifi_status_from_sdk() == 'enabled':
                    wifi_cur_config = 1
                if string[5:] and int(string[5:]) in [0, 1]:
                    wifi_status = str(string[5:])
                    if wifi_cur_config != int(wifi_status):
                        if int(wifi_status) == 1:
                            set_wifi_status_via_sdk(True)
                        else:
                            set_wifi_status_via_sdk(False)
                else:
                    wifi_status = wifi_cur_config
                response = json.dumps({"WiFiEnable": int(wifi_status)})
                uart.send_serial(response)

            elif string[:5] == "CELL|":
                # LTE硬件控制
                # 获取当前LTE状态
                lte_cur_config = 0
                lte_status_str = get_lte_status_from_sdk()
                if lte_status_str == 'enabled':
                    lte_cur_config = 1

                # 处理设置命令
                if string[5:] and int(string[5:]) in [0, 1]:
                    lte_target_status = str(string[5:])
                    if lte_cur_config != int(lte_target_status):
                        if int(lte_target_status) == 1:
                            set_lte_status_via_sdk(True)
                        else:
                            set_lte_status_via_sdk(False)
                else:
                    lte_target_status = lte_cur_config

                response = json.dumps({"CellularEnable": int(lte_target_status)})
                uart.send_serial(response)

            # elif string[:5] == "WFPW|":
            #     # 解析base64编码的密码
            #     try:
            #         if string[5:]:
            #             # Base64解码密码
            #             encoded_password = string[5:]
            #             try:
            #                 new_password = base64.b64decode(encoded_password).decode('utf-8')
            #             except Exception as e:
            #                 logger.error(f"Failed to decode password: {e}")
            #                 response = json.dumps({"Password": "error", "reason": "invalid_base64"})
            #                 uart.send_serial(response)
            #                 continue

            #             # 验证密码合法性（WiFi密码要求8-63个字符）
            #             if len(new_password) < 8 or len(new_password) > 63:
            #                 logger.error(f"Invalid password length: {len(new_password)}")
            #                 response = json.dumps({"Password": "error", "reason": "invalid_length"})
            #                 uart.send_serial(response)
            #                 continue

            #             # 读取配置文件
            #             try:
            #                 gs501_config = load_config(CONFIG_PATH)
            #             except Exception as e:
            #                 logger.error(f"Failed to read config: {e}")
            #                 response = json.dumps({"Password": "error", "reason": "config_read_failed"})
            #                 uart.send_serial(response)
            #                 continue

            #             # 修改AP_PASSWORD字段
            #             old_password = gs501_config.get("AP_PASSWORD", "")
            #             gs501_config["AP_PASSWORD"] = new_password

            #             # 保存配置文件
            #             if save_config(CONFIG_PATH, gs501_config):
            #                 # 返回base64编码的新密码作为确认
            #                 encoded_response = base64.b64encode(new_password.encode('utf-8')).decode('utf-8')
            #                 response = json.dumps({"Password": encoded_response})
            #                 uart.send_serial(response)

            #                 logger.info(f"WiFi password updated successfully (length: {len(new_password)})")
            #                 # 注意：不记录明文密码到日志

            #                 # 触发kill_main_processes重启相关进程
            #                 logger.info("Triggering process restart after password change...")
            #                 kill_success = kill_main_processes()
            #                 if kill_success:
            #                     logger.info("Main processes killed successfully after password update")
            #                 else:
            #                     logger.warning("No main processes found to kill after password update")
            #             else:
            #                 # 配置保存失败
            #                 response = json.dumps({"Password": "error", "reason": "config_save_failed"})
            #                 uart.send_serial(response)
            #                 logger.error("Failed to save WiFi password configuration")
            #         else:
            #             # 没有提供密码
            #             response = json.dumps({"Password": "error", "reason": "no_password"})
            #             uart.send_serial(response)

            #     except Exception as e:
            #         logger.error(f"Error processing WFPW command: {e}")
            #         response = json.dumps({"Password": "error", "reason": str(e)})
            #         uart.send_serial(response)
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
                    # traffic_request = {"cmd": "traffic_category"}
                    traffic_request = {"cmd": "drawing"}
                    traffic_request_json = json.dumps(traffic_request)
                    send_data(cam_info_socket, traffic_request_json.encode('utf-8'))
                    response = receive_data(cam_info_socket, 4096)
                    if response:
                        try:
                            # 检查响应是否为有效的JSON
                            left_traffic_data = json.loads(response.decode('utf-8'))
                            # logger.info(f"Left camera traffic category data: {left_traffic_data}")
                        except json.JSONDecodeError as e:
                            logger.error(f"Failed to decode left traffic category response: {e}")
                        except Exception as e:
                            logger.error(f"Error processing left traffic category response: {e}")
                
                # 获取右摄像头交通类别信息
                if cam_in_use == 2 or cam_in_use == 3:
                    # 选择右摄像头的socket
                    cam_info_socket = 'cam2_info_sock'
                    # 发送JSON格式的请求获取交通类别信息
                    # traffic_request = {"cmd": "traffic_category"}
                    traffic_request = {"cmd": "drawing"}
                    traffic_request_json = json.dumps(traffic_request)
                    send_data(cam_info_socket, traffic_request_json.encode('utf-8'))
                    response = receive_data(cam_info_socket, 4096)
                    if response:
                        try:
                            # 检查响应是否为有效的JSON
                            right_traffic_data = json.loads(response.decode('utf-8'))
                            # logger.info(f"Right camera traffic category data: {right_traffic_data}")
                        except json.JSONDecodeError as e:
                            logger.error(f"Failed to decode right traffic category response: {e}")
                        except Exception as e:
                            logger.error(f"Error processing right traffic category response: {e}")
                
                # Get counting data from CDS - returns separate left and right data
                left_counting_data, right_counting_data = get_cds_counting_data()
                
                # Process left camera data (cam1)
                if cam_in_use == 1 or cam_in_use == 3:
                    # 根据交通类别信息创建基础uart_data
                    if left_traffic_data:
                        base_uart_data = create_uart_data_from_traffic_categories(left_traffic_data)
                    else:
                        base_uart_data = dnn_default_dirct.copy()
                    if left_counting_data:
                        # Process cumulative data to get period counts for left camera
                        left_period_data = process_cumulative_counting(left_counting_data, "left")
                        # Get speed averages for left camera
                        left_speed_averages = get_speed_data_for_uart("left")
                        # Reformat for UART with speed integration using base data
                        uart_data = reformat_counting_for_uart(left_period_data, left_speed_averages, base_uart_data)
                    else:
                        # 如果没有计数数据，使用基础数据
                        uart_data = base_uart_data
                    
                    response = json.dumps(uart_data)
                    uart.send_serial(response)
                
                # Process right camera data (cam2)
                if cam_in_use == 2 or cam_in_use == 3:
                    # 根据交通类别信息创建基础uart_data
                    if right_traffic_data:
                        base_uart_data = create_uart_data_from_traffic_categories(right_traffic_data)
                    else:
                        base_uart_data = dnn_default_dirct.copy()
                    
                    if right_counting_data:
                        # Process cumulative data to get period counts for right camera
                        right_period_data = process_cumulative_counting(right_counting_data, "right")
                        # Get speed averages for right camera
                        right_speed_averages = get_speed_data_for_uart("right")
                        # Reformat for UART with speed integration using base data
                        uart_data = reformat_counting_for_uart(right_period_data, right_speed_averages, base_uart_data)
                    else:
                        # 如果没有计数数据，使用基础数据
                        uart_data = base_uart_data
                    
                    response = json.dumps(uart_data)
                    uart.send_serial(response)
                
                # Reset speed data for next cycle
                reset_speed_data()

            elif string[:4] == "BLK|":
                # 处理BLK|xxx命令，设置最大图像块数量
                try:
                    if string[4:]:
                        block_count = int(string[4:])
                        # 限制在20-80范围内
                        block_count = max(20, min(80, block_count))
                        max_image_blocks = block_count

                        # 持久化保存到配置文件
                        local_config = load_config("config.json")
                        local_config["TotalImageBlocks"] = block_count
                        with open("config.json", "w", encoding="utf-8") as file:
                            json.dump(local_config, file, indent=4)

                        logger.info(f"Max image blocks set to: {block_count}")
                        response = json.dumps({"TotalImageBlocks": str(block_count)})
                    else:
                        # 如果没有参数，返回当前设置
                        response = json.dumps({"TotalImageBlocks": str(max_image_blocks)})
                except ValueError:
                    # 参数不是有效数字
                    logger.error(f"Invalid BLK parameter: {string[4:]}")
                    response = json.dumps({"TotalImageBlocks": str(max_image_blocks), "Error": "Invalid parameter"})
                uart.send_serial(response)

            elif string[:5] == "WFPW|":
                try:
                    param = string[5:].strip()

                    if not param:
                        # 查询模式 - 从 gs501.json 读取
                        try:
                            gs501_config = load_config(CONFIG_PATH)
                            current_password = gs501_config.get("AP_PASSWORD", "")
                            if current_password:
                                encoded_pwd = base64.b64encode(current_password.encode('utf-8')).decode('utf-8')
                                response = json.dumps({"Password": encoded_pwd})
                            else:
                                response = json.dumps({"Password": ""})
                        except Exception as e:
                            logger.error(f"Query password failed: {e}")
                            response = json.dumps({"Password": ""})
                        uart.send_serial(response)
                    else:
                        # 设置模式
                        try:
                            # Base64 解码
                            new_password = base64.b64decode(param).decode('utf-8')

                            # 密码验证
                            if len(new_password) < 8:
                                response = json.dumps({"Password": ""})
                                uart.send_serial(response)
                                continue
                            if len(new_password) > 63:
                                response = json.dumps({"Password": ""})
                                uart.send_serial(response)
                                continue

                            # 调用 SDK
                            request = {
                                "cmd": "set_wifi_password_req",
                                "password": new_password
                            }
                            sdk_response = send_json_request(request)

                            # 处理响应
                            if sdk_response and sdk_response.get("cmd") == "set_wifi_password_rsp":
                                if sdk_response.get("ret_code") == 0:
                                    encoded_pwd = base64.b64encode(new_password.encode('utf-8')).decode('utf-8')
                                    response = json.dumps({"Password": encoded_pwd})
                                    logger.info("WiFi password updated successfully")
                                else:
                                    response = json.dumps({"Password": ""})
                            else:
                                response = json.dumps({"Password": ""})
                            uart.send_serial(response)

                        except base64.binascii.Error:
                            response = json.dumps({"Password": ""})
                            uart.send_serial(response)
                        except UnicodeDecodeError:
                            response = json.dumps({"Password": ""})
                            uart.send_serial(response)
                except Exception as e:
                    logger.error(f"WFPW error: {e}")
                    response = json.dumps({"Password": ""})
                    uart.send_serial(response)

            elif string == "?RST":
                # 返回响应
                response = json.dumps({"CamReset": 1})
                uart.send_serial(response)

                # 杀掉./main进程
                kill_success = kill_main_processes()
                if kill_success:
                    logger.info("RST command completed successfully")
                else:
                    logger.warning("RST command completed but no processes were killed")

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
                        
                        # 使用SDK获取摄像头参数
                        camera_id = CAM1_ID if index == 1 else CAM2_ID
                        camera_param_response = sdk_get_camera_param(camera_id)
                        if camera_param_response:
                            gain = camera_param_response.get("gain", 0)
                            exposure = camera_param_response.get("exposure", 0)
                            ae_mode = camera_param_response.get("ae_mode", "auto")
                            framerate = camera_param_response.get("framerate", 30)
                            
                            ps_data = {
                                "CameraFPS": str(framerate),  # 使用SDK返回的帧率
                                "ImageSize": f"{config['InputTensorWidth']}*{config['InputTensorHeith']}",
                                "PixelDepth": config["PixelDepth"],
                                "PixelOrder": config["PixelOrder"],
                                "DNNModel": config["DNNModel"],
                                "PostProcessingLogic": config["PostProcessingLogic"],
                                "SendImageQuality": config["SendImageQuality"],
                                "SendImageSizePercent": config["SendImageSizePercent"],
                                "AEModel": ae_mode,  # 直接使用SDK返回的字符串
                                "Exposure": str(exposure),
                                "Gain": str(gain),
                                "Heating": config["Heating"],
                                "Time": datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                            }
                            response = json.dumps(ps_data)
                        else:
                            response = json.dumps({}) # 如果SDK获取失败，发送空字典
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
                    uart.send_serial(response)
                elif index >= 5 and index < (5 + max_image_blocks):  # 从index=5开始处理图像块，动态范围
                    block_index = index - 5  # 计算实际的数组索引

                    if block_index < len(str_image):
                        # 发送实际存在的图像块
                        if block_index == 0 and emer_mode == 1:
                            emer_imgage_send = 1
                        response = "{\"Block" + str(block_index + 1) + "\":\"" + str_image[block_index] + "\"}"
                        uart.send_serial(response)

                        # 检查是否发送完最后一块
                        if block_index == len(str_image) - 1 and emer_imgage_send == 1:
                            emer_imgage_send = 0
                            emer_mode = 0
                            logger.debug(f"Emergency mode image sending completed at block {block_index + 1}")
                    else:
                        # 超出实际图像块范围但在最大范围内，返回空包
                        response = "{\"Block" + str(block_index + 1) + "\":\"\"}"
                        uart.send_serial(response)
                        # 如果在紧急模式下到达最大索引，结束紧急模式
                        if index == (4 + max_image_blocks) and emer_imgage_send == 1:
                            emer_imgage_send = 0
                            emer_mode = 0
                            logger.debug(f"Emergency mode ended at index {index}, actual blocks: {len(str_image)}")
                else:
                    logger.error(f"Unexpected PS index: ?PS{index}")

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