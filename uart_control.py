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
from socket_def import *

CAMERA1_DIAGNOSE_INFO_PATH = "/home/root/AglaiaSense/resource/share_config/diagnose_info_1.json"
CAMERA2_DIAGNOSE_INFO_PATH = "/home/root/AglaiaSense/resource/share_config/diagnose_info_2.json"
LOG_FOLDER = "log"
CONFIG_PATH = '/home/root/AglaiaSense/resource/share_config/uart_config.json'
CAM1_ID = 1
CAM2_ID = 2
# define pic size
IMAGE_CHANNELS = 3
IMAGE_HEIGHT = 300
IMAGE_WIDTH = 300
DEBUG = False

send_max_length = 980
count_interval = "300"
profile_index = "3"
ener_mode = "0"
send_time = 0
str_image = []

dnn_default_dirct = {}
sockets = {
    'cam1_info_sock': None,
    'cam2_info_sock': None,
    'cam1_dnn_sock': None,
    'cam2_dnn_sock': None
}

def debug_print(*args, **kwargs):
    if DEBUG:
        print(*args, **kwargs)

def connect_socket(server_address, log_file, socket_key):
    while True:
        if sockets[socket_key] is not None:
            time.sleep(1)  # If the connection exists, wait briefly
            continue

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect(server_address)
            sockets[socket_key] = sock
            log_file.write(
                f"[{datetime.now().strftime('%m/%d/%Y %H:%M:%S')}]: Connected to server at {server_address}\n"
            )
            # break  # If the connection is successful, exit the loop
        except socket.error as e:
            log_file.write(
                f"[{datetime.now().strftime('%m/%d/%Y %H:%M:%S')}]: Failed to connect to server: {e}. Retrying in 5 seconds...\n"
            )
            time.sleep(5)  # Wait 5 seconds and try again

def send_data(socket_key, data, log_file):
    sock = sockets[socket_key]
    if sock is None:
        log_file.write("No active socket connection. Cannot send data.\n")
        return
    
    try:
        sock.sendall(data)
    except socket.error as e:
        log_file.write(
            f"[{datetime.now().strftime('%m/%d/%Y %H:%M:%S')}]: Send error: {e}. Setting {socket_key} to None.\n"
        )
        sockets[socket_key] = None

def receive_data(socket_key, buffer_size=SOCK_COMM_LEN, log_file=None):
    sock = sockets[socket_key]
    if sock is None:
        log_file.write("No active socket connection. Cannot receive data.\n")
        return None
    
    try:
        response = sock.recv(buffer_size)
        if not response:
            log_file.write(
                f"[{datetime.now().strftime('%m/%d/%Y %H:%M:%S')}]: Receive None: Setting {socket_key} to None.\n"
            )
            sockets[socket_key] = None
        return response
    except socket.error as e:
        log_file.write(
            f"[{datetime.now().strftime('%m/%d/%Y %H:%M:%S')}]: Receive error: {e}. Setting {socket_key} to None.\n"
        )
        sockets[socket_key] = None
        return None

def open_shared_memory(shm_name):
    try:
        shm = posix_ipc.SharedMemory(shm_name, posix_ipc.O_RDWR)
        return shm
    except posix_ipc.Error as e:
        return None

def map_shared_memory(shm):
    shm_ptr = mmap.mmap(shm.fd, SHM_BMP_SIZE, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE)
    if shm_ptr == -1:
        os.close(shm.fd)
        return None
    return shm_ptr

def get_pic_from_socket(socket_key, shm_ptr, cam_id, log_file):
    image_data = shm_ptr.read(IMAGE_WIDTH * IMAGE_HEIGHT * IMAGE_CHANNELS)
    image_array = np.frombuffer(image_data, dtype=np.uint8)
    image_array = image_array.reshape((IMAGE_HEIGHT, IMAGE_WIDTH, IMAGE_CHANNELS))

    image = Image.fromarray(image_array)
    tmp_image_path = Path(f'./tmp/tmp_{cam_id}.bmp').resolve()
    tmp_image_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(tmp_image_path)

def get_dnn_date(socket_key, log_file):
    dnn_data_request = DnnDataYolo(cmd=DNN_GET)
    send_data(socket_key, dnn_data_request.to_bytes(), log_file)
    response = receive_data(socket_key, SOCK_COMM_LEN, log_file)
    if response:
        dnn_data = DnnDataYolo.from_bytes(response)
        dnn_dict = dnn_data.to_dict()
        return dnn_dict
    else:
        return None

def camera_control_process(socket_key, command, contol_val, log_file):
    try:
        if command == GET_GAIN:
            gain_data_g = GainData(command)
            send_data(socket_key, gain_data_g.to_bytes(), log_file)
            response = receive_data(socket_key, SOCK_COMM_LEN, log_file)
            if response:
                gain_data_g = GainData.from_bytes(response)
            return gain_data_g.val

        elif command == GET_EXPOSURE:
            exposure_data_g = ExposureData(command)
            send_data(socket_key, exposure_data_g.to_bytes(), log_file)
            response = receive_data(socket_key, SOCK_COMM_LEN, log_file)
            if response:
                exposure_data_g = ExposureData.from_bytes(response)
            return exposure_data_g.val

        elif command == GET_AE_MODE:
            ae_mode_data_g = AeModeData(command)
            send_data(socket_key, ae_mode_data_g.to_bytes(), log_file)
            response = receive_data(socket_key, SOCK_COMM_LEN, log_file)
            # response = cam_socket.recv(SOCK_COMM_LEN)
            if response:
                ae_mode_data_g = AeModeData.from_bytes(response)
            return ae_mode_data_g.val

        elif command == GET_AWB_MODE:
            awb_mode_data_g = AwbModeData(command)
            send_data(socket_key, awb_mode_data_g.to_bytes(), log_file)
            response = receive_data(socket_key, SOCK_COMM_LEN, log_file)
            if response:
                awb_mode_data_g = AwbModeData.from_bytes(response)
            return awb_mode_data_g.val
        elif command == CAM_EN:
            cam_en = CamEn(command, contol_val)
            send_data(socket_key, cam_en.to_bytes(), log_file)
        elif command == ENERGENCY_MODE:
            energency_mode = EnergencyMode(command, contol_val)
            send_data(socket_key, energency_mode.to_bytes(), log_file)
        else:
            log_file.write(f"[{datetime.now().strftime('%m/%d/%Y %H:%M:%S')}]: Camera command error: {hex(command)}\n")
    except socket.timeout:
        log_file.write(f"[{datetime.now().strftime('%m/%d/%Y %H:%M:%S')}]: Socket timed out waiting for response for command: {hex(command)}\n")
    except socket.error as e:
        log_file.write(f"[{datetime.now().strftime('%m/%d/%Y %H:%M:%S')}]: Socket error for command: {hex(command)}, error: {e}\n")
    except Exception as e:
        log_file.write(f"[{datetime.now().strftime('%m/%d/%Y %H:%M:%S')}]: Unexpected error for command: {hex(command)}, error: {e}\n")

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

config = load_config(CONFIG_PATH)

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
        debug_print(time.strftime("%B-%d-%Y %H:%M:%S") + "  ->: {0}".format(cmd))
        self.uartport.write((cmd+"\n").encode("utf_8"))

    def receive_serial(self):
        rcvdata = self.uartport.readline()
        return rcvdata

def update_sim_attribute(cam_id):
    global str_image
    image = Image.open(f'./tmp/tmp_{cam_id}.bmp')
    image.save("./tmp/converted-jpg-image.jpg", optimize=True, quality=50)
    with open("./tmp/converted-jpg-image.jpg", "rb") as image2string:
        converted_string = base64.b64encode(image2string.read()).decode()
    str_len = len(converted_string)
    send_time = math.ceil(str_len / send_max_length)
    str_image = []
    for x in range(send_time):
        str_image.append(converted_string[x*send_max_length:(x+1)*send_max_length])

def main():
    global count_interval, ener_mode
    uart = UART()
    log_folder_path = Path(LOG_FOLDER)
    log_folder_path.mkdir(parents=True, exist_ok=True)
    log_file_path = log_folder_path.joinpath(f"log_{datetime.now().strftime('%m%d%Y')}.txt")
    log_file_path.touch(exist_ok=True)
    log_file = open(log_file_path, 'a')

    # open sockets
    cam1_info_address = ("localhost", CAMERA1_PORT)
    cam2_info_address = ("localhost", CAMERA2_PORT)
    cam1_dnn_address = ("localhost", CAMERA1_DNN_PORT)
    cam2_dnn_address = ("localhost", CAMERA2_DNN_PORT)

    cam1_info_thread = Thread(target=connect_socket, args=(cam1_info_address, log_file, 'cam1_info_sock'))
    cam2_info_thread = Thread(target=connect_socket, args=(cam2_info_address, log_file, 'cam2_info_sock'))
    cam1_dnn_thread = Thread(target=connect_socket, args=(cam1_dnn_address, log_file, 'cam1_dnn_sock'))
    cam2_dnn_thread = Thread(target=connect_socket, args=(cam2_dnn_address, log_file, 'cam2_dnn_sock'))

    cam1_info_thread.daemon = True
    cam2_info_thread.daemon = True
    cam1_dnn_thread.daemon = True
    cam2_dnn_thread.daemon = True

    cam1_info_thread.start()
    cam2_info_thread.start()
    cam1_dnn_thread.start()
    cam2_dnn_thread.start()

    shm_name = CAMERA1_SHM_BMP_NAME
    cam1_image_shm = open_shared_memory(shm_name)
    if cam1_image_shm is None:
        log_file.write(f"[{datetime.now().strftime('%m/%d/%Y %H:%M:%S')}]: Failed to open shared memory\n")
        return
    cam1_image_shm_ptr = map_shared_memory(cam1_image_shm)
    if cam1_image_shm_ptr is None:
        log_file.write(f"[{datetime.now().strftime('%m/%d/%Y %H:%M:%S')}]: Failed to map shared memory\n")
        cam1_image_shm.close_fd()
        return
    get_pic_from_socket('cam1_info_sock', cam1_image_shm_ptr, CAM1_ID, log_file)
    update_sim_attribute(CAM1_ID)

    while True:
        raw_data = uart.receive_serial()
        if raw_data:
            start_time = time.time()
            string = raw_data.decode("utf_8", "ignore").rstrip()
            debug_print(f"{datetime.now().strftime('%B-%d-%Y %H:%M:%S')}  <-: {string}")
            if string == "?Asset":
                response = json.dumps(config["?Asset"][0])
                uart.send_serial(response)
            elif string[:2] == "@|":
                if string[2:] and int(string[2:]) > 0:
                    count_interval = str(string[2:])
                response = json.dumps({"NICFrequency": int(count_interval)})
                uart.send_serial(response)
            elif string == "?Order":
                response = json.dumps(config["?Order"][0])
                uart.send_serial(response)
            elif string[:8] == "Profile|":
                response = json.dumps({"CamProfile": int(profile_index)})
                uart.send_serial(response)
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
                if string[6:] and int(string[6:]) in range(0, 27):
                    ener_mode = str(string[6:])
                    camera_control_process('cam1_info_sock', ENERGENCY_MODE, int(string[6:]), log_file)
                    camera_control_process('cam2_info_sock', ENERGENCY_MODE, int(string[6:]), log_file)
                response = json.dumps({"EmergencyMode": int(ener_mode)})
                uart.send_serial(response)
                if int(ener_mode) in range(0, 27):
                    pass
                    ener_mode = "0"
            elif string == "?OBdata":
                get_pic_from_socket('cam1_info_sock', cam1_image_shm_ptr, CAM1_ID, log_file)
                update_sim_attribute(CAM1_ID)
                dnn_dict1 = get_dnn_date('cam1_dnn_sock', log_file)
                dnn_dict2 = get_dnn_date('cam2_dnn_sock', log_file)
                if dnn_dict1:
                    response1 = json.dumps(dnn_dict1)
                    uart.send_serial(response1)
                else:
                    uart.send_serial(dnn_default_dirct)
                if dnn_dict2:
                    response2 = json.dumps(dnn_dict2)
                    uart.send_serial(response2)
                else:
                    uart.send_serial(dnn_default_dirct)
            elif string[:3] == "?PS":
                index = int(string[3:])
                if index in [1, 2]:
                    if index == 1:
                        cam_info_socket = 'cam1_info_sock'
                    else:
                        cam_info_socket = 'cam2_info_sock'
                    current_time = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                    gain = camera_control_process(cam_info_socket, GET_GAIN, 0, log_file)
                    exposure = camera_control_process(cam_info_socket, GET_EXPOSURE, 0, log_file)
                    ae_model = camera_control_process(cam_info_socket, GET_AE_MODE, 0, log_file)
                    awb_model = camera_control_process(cam_info_socket, GET_AWB_MODE, 0, log_file)
                    if ae_model == 0:
                        ae_status = "auto"
                    else:
                        ae_status = "manual"
                    if awb_model == 0:
                        awb_status = "enable"
                    else:
                        awb_status = "disable"
                    ps_data = config[f"?PS{index}"][0]
                    ps_data["Exposure"] = exposure
                    ps_data["Gain"] = gain
                    ps_data["AEModel"] = ae_status
                    ps_data["AWBMode"] = awb_status
                    ps_data["Time"] = current_time
                    response = json.dumps(ps_data)
                    uart.send_serial(response)
                elif index in [3, 4]:
                    if index == 3:
                        cam_info_socket = 'cam1_info_sock'
                    else:
                        cam_info_socket = 'cam2_info_sock'
                    roi_data_g = RoiData(ROI_GET, 0, [])
                    send_data(cam_info_socket, roi_data_g.to_bytes(), log_file)
                    response = receive_data(cam_info_socket, SOCK_COMM_LEN, log_file)
                    if response:
                        roi_data_g = RoiData.from_bytes(response)
                    post_processing = {}
                    for i in range(roi_data_g.point_number):
                        post_processing[f"x{i+1}"] = str(roi_data_g.x[i])
                        post_processing[f"y{i+1}"] = str(roi_data_g.y[i])
                    response = json.dumps(post_processing)
                    uart.send_serial(response)
                else:
                    if (index - 5) < len(str_image):
                        response = "{\"Block" + str(index - 4) + ":" + str_image[index - 5] + "}"
                        uart.send_serial(response)

            debug_print(f"--- {time.time() - start_time} seconds ---")
if __name__ == '__main__':
    main()