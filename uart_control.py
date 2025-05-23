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

import logging
from logging.handlers import RotatingFileHandler
import sys

CAMERA1_DIAGNOSE_INFO_PATH = "/home/root/AglaiaSense/resource/share_config/diagnose_info_1.json"
CAMERA2_DIAGNOSE_INFO_PATH = "/home/root/AglaiaSense/resource/share_config/diagnose_info_2.json"
LOG_FOLDER = "log"
CONFIG_PATH = '/home/root/AglaiaSense/resource/share_config/gs501.json'
CAM1_ID = 1
CAM2_ID = 2
# define pic size
IMAGE_CHANNELS = 3
IMAGE_HEIGHT = 300
IMAGE_WIDTH = 300

send_max_length = 980
count_interval = "300"
profile_index = 3
emer_mode = 0  # corrected from ener_mode
str_image = []
emer_imgage_send = 0

dnn_default_dirct = {"spdunit":"MPH","incar":-1,"incarspd":-1,"inbus":-1,"inbusspd":-1,"inped":-1,"inpedspd":-1,"incycle":-1,"incyclespd":-1,"intruck":-1,"intruckspd":-1,"outcar":-1,"outcarspd":-1,"outbus":-1,"outbusspd":-1,"outped":-1,"outpedspd":-1,"outcycle":-1,"outcyclespd":-1,"outtruck":-1,"outtruckspd":-1}
sockets = {
    'cam1_info_sock': None,
    'cam2_info_sock': None,
    'cam1_dnn_sock': None,
    'cam2_dnn_sock': None
}

# Declare globals for shared memory pointers and cam_in_use to be accessible in emer_mode_server
cam1_image_shm_ptr = None
cam2_image_shm_ptr = None
cam_in_use = 1

def setup_logger(log_file_path):
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

def connect_socket(server_address, logger, socket_key):
    while True:
        if sockets[socket_key] is not None:
            time.sleep(1)  # If the connection exists, wait briefly
            continue

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect(server_address)
            sockets[socket_key] = sock
            logger.info(f"Connected to server at {server_address}")
        except socket.error as e:
            logger.error(f"Failed to connect to server: {e}. Retrying in 5 seconds...")
            time.sleep(5)  # Wait 5 seconds and try again

def send_data(socket_key, data, logger):
    sock = sockets[socket_key]
    if sock is None:
        logger.error("No active socket connection. Cannot send data.")
        return
    
    try:
        sock.sendall(data)
    except socket.error as e:
        logger.error(f"Send error: {e}. Setting {socket_key} to None.")
        sockets[socket_key] = None

def receive_data(socket_key, buffer_size, logger):
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

def get_dnn_date(socket_key, logger):
    dnn_data_request = DnnDataYolo(cmd=DNN_GET)
    send_data(socket_key, dnn_data_request.to_bytes(), logger)
    response = receive_data(socket_key, SOCK_COMM_LEN, logger)
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

def camera_control_process(socket_key, command, contol_val, logger):
    try:
        if command == GET_GAIN:
            gain_data_g = GainData(command)
            send_data(socket_key, gain_data_g.to_bytes(), logger)
            response = receive_data(socket_key, SOCK_COMM_LEN, logger)
            if response:
                gain_data_g = GainData.from_bytes(response)
            return gain_data_g.val

        elif command == GET_EXPOSURE:
            exposure_data_g = ExposureData(command)
            send_data(socket_key, exposure_data_g.to_bytes(), logger)
            response = receive_data(socket_key, SOCK_COMM_LEN, logger)
            if response:
                exposure_data_g = ExposureData.from_bytes(response)
            return exposure_data_g.val

        elif command == GET_AE_MODE:
            ae_mode_data_g = AeModeData(command)
            send_data(socket_key, ae_mode_data_g.to_bytes(), logger)
            response = receive_data(socket_key, SOCK_COMM_LEN, logger)
            if response:
                ae_mode_data_g = AeModeData.from_bytes(response)
            return ae_mode_data_g.val

        elif command == GET_AWB_MODE:
            awb_mode_data_g = AwbModeData(command)
            send_data(socket_key, awb_mode_data_g.to_bytes(), logger)
            response = receive_data(socket_key, SOCK_COMM_LEN, logger)
            if response:
                awb_mode_data_g = AwbModeData.from_bytes(response)
            return awb_mode_data_g.val
        elif command == CAM_EN:
            cam_en = CamEn(command, contol_val)
            send_data(socket_key, cam_en.to_bytes(), logger)
        elif command == ENERGENCY_MODE:
            energency_mode = EnergencyMode(command, contol_val)
            send_data(socket_key, energency_mode.to_bytes(), logger)
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
    def __init__(self, logger):
        self.logger = logger
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
        self.logger.debug(f"UART send ->: {cmd}")
        self.uartport.write((cmd+"\n").encode("utf_8"))

    def receive_serial(self):
        rcvdata = self.uartport.readline()
        return rcvdata

def save_image_with_target_size(image, cam_in_use, logger):
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
        quality -= 5
    os.rename(temp_filepath, filepath)

def update_sim_attribute(cam_in_use, logger):
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

    save_image_with_target_size(image, cam_in_use, logger)

    with open('./tmp/converted-jpg-image.jpg', 'rb') as image2string:
        converted_string = base64.b64encode(image2string.read()).decode()
    
    str_len = len(converted_string)
    send_time = math.ceil(str_len / send_max_length)
    str_image = []
    for x in range(send_time):
        str_image.append(converted_string[x * send_max_length:(x + 1) * send_max_length])

def update_speeds_with_prefix(dnn_dict):
    # different types of speed ranges
    speed_ranges = {
        "car": (20, 70),
        "bus": (30, 60),
        "cycle": (5, 20),
        "truck": (40, 80),
        "ped": (2, 10)
    }
    prefixes = ['in', 'out']

    for key in dnn_dict.keys():
        # find the count field: no spd suffix, and starts with in or out
        if key.startswith(tuple(prefixes)) and not key.endswith('spd'):
            count = dnn_dict.get(key, -1)
            # get the vehicle type by removing the prefix
            vehicle_type = None
            for prefix in prefixes:
                if key.startswith(prefix):
                    vehicle_type = key[len(prefix):]
                    break
            if vehicle_type not in speed_ranges:
                continue

            speed_key = key + "spd"
            if count > 0:
                low, high = speed_ranges[vehicle_type]
                dnn_dict[speed_key] = random.randint(low, high)
            else:
                dnn_dict[speed_key] = 0
    return dnn_dict

def handle_emer_mode_client(client_sock, addr, logger):
    """
    Handle communication with one EmergenMode client.
    Keep receiving until client disconnects.
    """
    global emer_mode, cam_in_use, cam1_image_shm_ptr, cam2_image_shm_ptr
    logger.info(f"Handling EmergenMode client from {addr}")
    try:
        while True:
            data = client_sock.recv(1024)
            if not data:
                logger.info(f"Client {addr} disconnected")
                break  # client closed connection

            try:
                msg = json.loads(data.decode('utf-8'))
                if 'EmergMode' in msg:
                    emer_mode = int(msg['EmergMode'])
                    logger.info(f"emer_mode set to {emer_mode} by socket message")
                    if emer_mode == 1:
                        # Save images to buffer when emer_mode is set to 1
                        if cam_in_use == 1 or cam_in_use == 3:
                            get_pic_from_socket(cam1_image_shm_ptr, CAM1_ID)
                        if cam_in_use == 2 or cam_in_use == 3:
                            get_pic_from_socket(cam2_image_shm_ptr, CAM2_ID)
                        update_sim_attribute(cam_in_use, logger)
            except Exception as e:
                logger.error(f"Failed to parse EmergenMode json: {e}")
    except Exception as e:
        logger.error(f"Error handling EmergenMode client: {e}")
    finally:
        client_sock.close()
        logger.info(f"EmergenMode client from {addr} connection closed")


def emer_mode_server(host, port, logger):
    """
    Multi-threaded Socket server to listen for {"EmergMode": 1} JSON messages.
    Each client connection handled in a separate thread.
    """
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind((host, port))
    server_sock.listen(5)  # backlog 5
    logger.info(f"EmergMode server listening on {host}:{port}")

    while True:
        client_sock, addr = server_sock.accept()
        logger.info(f"EmergMode client connected from {addr}")
        client_thread = threading.Thread(target=handle_emer_mode_client, args=(client_sock, addr, logger))
        client_thread.daemon = True
        client_thread.start()

def main():
    """
    Main function to initialize logger, UART, load config, start socket connection
    and emer_mode server thread, and handle UART commands.
    """
    global count_interval, profile_index, emer_mode
    global IMAGE_HEIGHT, IMAGE_WIDTH, cam_in_use
    global cam1_image_shm_ptr, cam2_image_shm_ptr
    global emer_imgage_send

    log_folder_path = Path(LOG_FOLDER)
    log_folder_path.mkdir(parents=True, exist_ok=True)
    log_file_path = log_folder_path.joinpath("uart_log.txt")
    logger = setup_logger(log_file_path)
    uart = UART(logger)
    dnn_dirct = dnn_default_dirct.copy()
    config = load_config(CONFIG_PATH)
    IMAGE_HEIGHT = int(config.get('InputTensorHeith'))
    IMAGE_WIDTH = int(config.get('InputTensorWidth'))
    # cam_in_use: left = 1, right =2, all = 3. note:left is cam1, right is cam2
    sensor_num = config["SensorNum"]
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

    # Start emer_mode socket server thread
    emer_mode_thread = threading.Thread(target=emer_mode_server, args=('127.0.0.1', 5555, logger))
    emer_mode_thread.daemon = True
    emer_mode_thread.start()

    if cam_in_use == 1 or cam_in_use == 3:
        cam1_info_address = ("localhost", CAMERA1_PORT)
        cam1_dnn_address = ("localhost", CAMERA1_DNN_PORT)
        cam1_info_thread = Thread(target=connect_socket, args=(cam1_info_address, logger, 'cam1_info_sock'))
        cam1_dnn_thread = Thread(target=connect_socket, args=(cam1_dnn_address, logger, 'cam1_dnn_sock'))
        cam1_info_thread.daemon = True
        cam1_dnn_thread.daemon = True
        cam1_info_thread.start()
        cam1_dnn_thread.start()
    if cam_in_use == 2 or cam_in_use == 3:
        cam2_info_address = ("localhost", CAMERA2_PORT)
        cam2_dnn_address = ("localhost", CAMERA2_DNN_PORT)
        cam2_info_thread = Thread(target=connect_socket, args=(cam2_info_address, logger, 'cam2_info_sock'))
        cam2_dnn_thread = Thread(target=connect_socket, args=(cam2_dnn_address, logger, 'cam2_dnn_sock'))
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

    update_sim_attribute(cam_in_use, logger)

    while True:
        raw_data = uart.receive_serial()
        if raw_data:
            start_time = time.time()
            string = raw_data.decode("utf_8", "ignore").rstrip()
            logger.debug(f"UART recv <-: {string}")
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
                    profile_index = int(string[8:])
                response = json.dumps({"CamProfile": int(profile_index)})
                uart.send_serial(response)
                if int(profile_index) != cam_in_use:
                    if int(profile_index) == 1:
                        config["SensorNum"] = "left"
                    elif int(profile_index) == 2:
                        config["SensorNum"] = "right"
                    elif int(profile_index) == 3:
                        config["SensorNum"] = "dual"
                    with open(CONFIG_PATH, "w", encoding="utf-8") as file:
                        json.dump(config, file, indent=4)
                    subprocess.call("reboot", shell=True)

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
                    update_sim_attribute(cam_in_use, logger)
                    
                # get count data
                if cam_in_use == 1 or cam_in_use == 3:
                    dnn_dict1 = get_dnn_date('cam1_dnn_sock', logger)
                if cam_in_use == 2 or cam_in_use == 3:
                    dnn_dict2 = get_dnn_date('cam2_dnn_sock', logger)
                if cam_in_use == 1 or cam_in_use == 3:
                    if dnn_dict1:
                        for key in dnn_dict1.keys():
                            dnn_dirct[key] = dnn_dict1[key]
                        dnn_dirct = update_speeds_with_prefix(dnn_dirct)
                        response = json.dumps(dnn_dirct)
                        uart.send_serial(response)
                    else:
                        response = json.dumps(dnn_default_dirct)
                        uart.send_serial(response)
                if cam_in_use == 2 or cam_in_use == 3:
                    if dnn_dict2:
                        for key in dnn_dict2.keys():
                            dnn_dirct[key] = dnn_dict2[key]
                        dnn_dirct = update_speeds_with_prefix(dnn_dirct)
                        response = json.dumps(dnn_dirct)
                        uart.send_serial(response)
                    else:
                        response = json.dumps(dnn_default_dirct)
                        uart.send_serial(response)
            elif string[:3] == "?PS":
                index = int(string[3:])
                if index in [1, 2]:
                    if index == 1:
                        cam_info_socket = 'cam1_info_sock'
                        if cam_in_use == 2:
                            cam_info_socket = 'cam2_info_sock'
                    else:
                        cam_info_socket = 'cam2_info_sock'
                        if cam_in_use == 1:
                            cam_info_socket = 'cam1_info_sock'
                    current_time = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                    gain = camera_control_process(cam_info_socket, GET_GAIN, 0, logger)
                    exposure = camera_control_process(cam_info_socket, GET_EXPOSURE, 0, logger)
                    ae_model = camera_control_process(cam_info_socket, GET_AE_MODE, 0, logger)
                    awb_model = camera_control_process(cam_info_socket, GET_AWB_MODE, 0, logger)
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
                    uart.send_serial(response)
                elif index in [3, 4]:
                    if index == 3:
                        cam_info_socket = 'cam1_dnn_sock'
                        if cam_in_use == 2:
                            cam_info_socket = 'cam2_dnn_sock'
                    else:
                        cam_info_socket = 'cam2_dnn_sock'
                        if cam_in_use == 1:
                            cam_info_socket = 'cam1_dnn_sock'
                    roi_data_g = RoiData(ROI_GET, 0, [])
                    send_data(cam_info_socket, roi_data_g.to_bytes(), logger)
                    response = receive_data(cam_info_socket, SOCK_COMM_LEN, logger)
                    if response:
                        roi_data_g = RoiData.from_bytes(response)
                    post_processing = {}
                    for i in range(roi_data_g.point_number):
                        post_processing[f"x{i+1}"] = str(roi_data_g.x[i])
                        post_processing[f"y{i+1}"] = str(roi_data_g.y[i])
                    response = json.dumps(post_processing)
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

if __name__ == '__main__':
    main()
