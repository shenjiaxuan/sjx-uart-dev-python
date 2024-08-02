import socket
import serial
import base64
import time
import math
import random
from PIL import Image
import json
import subprocess
from datetime import datetime
import numpy as np
from pathlib import Path
import mmap
import posix_ipc
import os
from definitions import *

random.seed(1)
image_folder = '/home/root/sjx/input_tensors/'
send_max_length = 980
count_interval = "300"
wifi_status = "0"
profile_index = "1"
ener_mode = "0"
# image_index = 1
send_time = 0
str_image = []
config_path = '/home/root/sjx/config.json'

# cam1_image_shm_ptr = None
# cam2_image_shm_ptr = None

# open socket
def open_socket(port,log_file):
    server_address = ('localhost', port)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect(server_address)
    except socket.error as e:
        log_file.write(f"[{datetime.now().strftime('%m/%d/%Y %H:%M:%S')}]: Failed to connect to server: {e}\n")
        return
    return sock

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

def get_pic_from_socket(sock,shm_ptr,cam_id):
    # get pic_shm from camera
    bmp_data = BmpData(BMP_GET)
    sock.sendall(bmp_data.to_bytes())
    response = sock.recv(512)
    if len(response) >= 36:
        bmp_data = BmpData.from_bytes(response)
    # get image from shm
    shm_ptr.seek(0)
    image_data = shm_ptr.read(IMAGE_WIDTH * IMAGE_HEIGHT * IMAGE_CHANNELS)
    image_array = np.frombuffer(image_data, dtype=np.uint8)
    image_array = image_array.reshape((IMAGE_HEIGHT, IMAGE_WIDTH, IMAGE_CHANNELS))

    image = Image.fromarray(image_array)
    tmp_image_path = Path(f'./tmp/tmp_{cam_id}.bmp').resolve()
    # tmp_image_path = Path('./tmp/tmp.bmp').resolve()
    tmp_image_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(tmp_image_path)

def get_dnn_date(sock):
    dnn_data_request = DnnDataYolo(cmd=DNN_GET)
    sock.sendall(dnn_data_request.to_bytes())
    response = sock.recv(512)
    if response:
        dnn_data = DnnDataYolo.from_bytes(response)
        dnn_dict = dnn_data.to_dict()
        return dnn_dict
    return

def camera_control_process(cam_socket, command, contol_val, log_file):
    try:
        # if command == SET_GAIN:
        #     gain_data_s = GainData(command, contol_val)
        #     global_sock.sendall(gain_data_s.to_bytes())

        if command == GET_GAIN:
            gain_data_g = GainData(command)
            cam_socket.sendall(gain_data_g.to_bytes())
            response = cam_socket.recv(512)
            if len(response) >= 2:
                gain_data_g = GainData.from_bytes(response)
                return gain_data_g.val
        # elif command == SET_EXPOSURE:
        #     exposure_data_s = ExposureData(command, contol_val)
        #     global_sock.sendall(exposure_data_s.to_bytes())

        elif command == GET_EXPOSURE:
            exposure_data_g = ExposureData(command)
            cam_socket.sendall(exposure_data_g.to_bytes())
            response = cam_socket.recv(512)
            if len(response) >= 2:
                exposure_data_g = ExposureData.from_bytes(response)
                return exposure_data_g.val
        # elif command == SET_FRAMERATE:
        #     frame_rate_data_s = FrameRateData(command, contol_val)
        #     global_sock.sendall(frame_rate_data_s.to_bytes())

        # elif command == GET_FRAMERATE:
        #     frame_rate_data_g = FrameRateData(command)
        #     global_sock.sendall(frame_rate_data_g.to_bytes())
        #     response = global_sock.recv(512)
        #     if len(response) >= 2:
        #         frame_rate_data_g = FrameRateData.from_bytes(response)

        # elif command == SET_AE_MODE:
        #     ae_mode_data_s = AeModeData(command, contol_val)
        #     global_sock.sendall(ae_mode_data_s.to_bytes())
        elif command == GET_AE_MODE:
            ae_mode_data_g = AeModeData(command)
            cam_socket.sendall(ae_mode_data_g.to_bytes())
            response = cam_socket.recv(512)
            if len(response) >= 2:
                ae_mode_data_g = AeModeData.from_bytes(response)
                return ae_mode_data_g.val
        # elif command == SET_AWB_MODE:
        #     awb_mode_data_s = AwbModeData(command, contol_val)
        #     global_sock.sendall(awb_mode_data_s.to_bytes())

        elif command == GET_AWB_MODE:
            awb_mode_data_g = AwbModeData(command)
            cam_socket.sendall(awb_mode_data_g.to_bytes())
            response = cam_socket.recv(512)
            if len(response) >= 2:
                awb_mode_data_g = AwbModeData.from_bytes(response)
                return awb_mode_data_g.val
        elif command == CAM_EN:
            cam_en = CamEn(command, contol_val)
            cam_socket.sendall(cam_en.to_bytes())
            print(f">>> Test SET_CAM_EN, val = {cam_en.val}")
        elif command == ENERGENCY_MODE:
            energency_mode = EnergencyMode(command, contol_val)
            cam_socket.sendall(energency_mode.to_bytes())
            print(f">>> Test SET_ENERGENCY_MODE, val = {energency_mode.val}")
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

def read_exposure_and_gain():
    result = subprocess.run(['i2ctransfer', '-f', '-y', '3', 'w2@0x1a', '0x02', '0x02', 'r4'], capture_output=True, text=True)
    values = result.stdout.strip().split()
    if len(values) < 4:
        print("Error: Insufficient data received from i2ctransfer command.")
        return None, None
    exposure = (int(values[0], 16) << 8) + int(values[1], 16)  # Combine high and low bytes for exposure
    gain = (int(values[2], 16) << 8) + int(values[3], 16)  # Combine high and low bytes for gain
    return exposure, gain

def read_ae_awb_mode():
    result = subprocess.run(['i2ctransfer', '-f', '-y', '3', 'w2@0x1a', '0xD8', '0x00', 'r1'], capture_output=True, text=True)
    value = int(result.stdout.strip(), 16)
    ae_awb_mode = 'auto' if (value & 0x01) == 0 else 'manual'
    return ae_awb_mode, ae_awb_mode  # Assuming the same value is used for AEModel and AWBMode

def check_camera_errors(path):
    config = load_config(path)
    if all(value == "True" for value in config.values()):
        return "0"
    else:
        return "1"

config = load_config(config_path)

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
        print(time.strftime("%B-%d-%Y %H:%M:%S") + "  ->: {0}".format(cmd))
        self.uartport.write((cmd+"\n").encode("utf_8"))

    def receive_serial(self):
        rcvdata = self.uartport.readline()
        return rcvdata

def update_sim_attribute(cam_id):
    global str_image
    # global image_index
    # if image_index > 10:
    #     image_index = 1
    # image_file_name = image_folder + str(image_index) + ".bmp"
    # image_index = image_index + 1

    image = Image.open(f'./tmp/tmp_{cam_id}.bmp')
    image.save("/home/root/sjx/converted-jpg-image.jpg", optimize=True, quality=50)
    with open("/home/root/sjx/converted-jpg-image.jpg", "rb") as image2string:
        converted_string = base64.b64encode(image2string.read()).decode()
    str_len = len(converted_string)
    send_time = math.ceil(str_len / send_max_length)
    str_image = []
    for x in range(send_time):
        str_image.append(converted_string[x*send_max_length:(x+1)*send_max_length])

def main():
    # global cam1_image_shm_ptr
    # global cam2_image_shm_ptr
    uart = UART()
    log_folder_path = Path(LOG_FOLDER)
    if not log_folder_path.is_dir():
        log_folder_path.mkdir(parents=True, exist_ok=True)  # create the log file folder if not exists
    log_file_path = log_folder_path.joinpath(f"log_{datetime.now().strftime('%m%d%Y')}.txt")
    log_file_path.touch(exist_ok=True)  # create the log file if not exists
    log_file = open(log_file_path, 'a')

    cam1_info_socket = open_socket(CAM1_INFO_PORT,log_file)
    cam2_info_socket = open_socket(CAM2_INFO_PORT,log_file)
    cam1_dnn_socket = open_socket(CAM1_DNN_PORT,log_file)
    cam2_dnn_socket = open_socket(CAM2_DNN_PORT,log_file)

    # open image_shm
    shm_name = LEFT_SHM_BMP_NAME
    cam1_image_shm = open_shared_memory(shm_name)
    if cam1_image_shm is None:
        log_file.write(f"[{datetime.now().strftime('%m/%d/%Y %H:%M:%S')}]: Failed to open shared memory\n")
        return
    cam1_image_shm_ptr = map_shared_memory(cam1_image_shm)
    if cam1_image_shm is None:
        log_file.write(f"[{datetime.now().strftime('%m/%d/%Y %H:%M:%S')}]: Failed to map shared memory\n")
        cam1_image_shm.close_fd()
        return
    
    # shm_name = RIGHT_SHM_BMP_NAME
    # cam2_image_shm = open_shared_memory(shm_name)
    # if cam2_image_shm is None:
    #     log_file.write(f"[{datetime.now().strftime('%m/%d/%Y %H:%M:%S')}]: Failed to open shared memory\n")
    #     return
    # cam2_image_shm_ptr = map_shared_memory(cam2_image_shm)
    # if cam2_image_shm is None:
    #     log_file.write(f"[{datetime.now().strftime('%m/%d/%Y %H:%M:%S')}]: Failed to map shared memory\n")
    #     cam2_image_shm.close_fd()
    #     return

    get_pic_from_socket(cam1_info_socket, cam1_image_shm_ptr, CAM1_ID)
    # get_pic_from_socket(cam2_info_socket, cam2_image_shm_ptr, 2)
    update_sim_attribute(CAM1_ID)

    while True:
        raw_data = uart.receive_serial()
        if raw_data:
            start_time = time.time()
            string = raw_data.decode("utf_8", "ignore").rstrip()
            print(time.strftime("%B-%d-%Y %H:%M:%S") + "  <-: {0}".format(string))
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
                if string[8:] and int(string[8:]) in [0, 1, 2, 3, 16, 17, 18, 19]:
                    profile_index = str(string[8:])
                    camera_control_process(cam1_info_socket, CAM_EN, int(profile_index), log_file)
                    camera_control_process(cam2_info_socket, CAM_EN, int(profile_index), log_file)
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
                # response = {"Cam1ErrCode": cam1_error_code, "Cam2ErrCode": cam2_error_code}
                response = json.dumps({"Cam1ErrCode": cam1_error_code,"Cam2ErrCode": cam2_error_code})
                uart.send_serial(response)
            elif string[:6] == "REACT|":
                if string[6:] and int(string[6:]) in range(0, 27):
                    ener_mode = str(string[6:])
                    camera_control_process(cam1_info_socket, ENERGENCY_MODE, int(string[6:]), log_file)
                    camera_control_process(cam2_info_socket, ENERGENCY_MODE, int(string[6:]), log_file)
                response = json.dumps({"EmergencyMode": int(ener_mode)})
                uart.send_serial(response)
                if int(ener_mode) in range(0, 27):
                    pass
                    ener_mode = "0"
            elif string == "?OBdata":
                get_pic_from_socket(cam1_info_socket, cam1_image_shm_ptr, CAM1_ID)
                update_sim_attribute(CAM1_ID)
                # response1 = json.dumps(config["?OBdata"][0])
                # response2 = json.dumps(config["?OBdata"][1])
                # uart.send_serial(response1)
                # uart.send_serial(response2)
                # cam1_data = [random.randrange(10,50),random.randrange(50,80), # in car
                #              random.randrange(2,10),random.randrange(20,50), # in bus
                #              random.randrange(40,100),random.randrange(1,10), # in ped
                #              random.randrange(0,1),random.randrange(0,1), # in cycle
                #              random.randrange(2,20),random.randrange(40,80), # in truck
                #              random.randrange(12,40),random.randrange(20,100), # out car
                #              random.randrange(1,2),random.randrange(30,85), # out bus
                #              random.randrange(1,3),random.randrange(1,9), # out ped
                #              random.randrange(1,25),random.randrange(1,20), # out cycle
                #              random.randrange(1,30),random.randrange(40,100), # out truck
                #              ]
                # response1 = ("{\"spdunit\":\"MPH\","
                #             "\"incar\":" + str(cam1_data[0]) + ","
                #             "\"incarspd\":" + str(cam1_data[1]) + ","
                #             "\"inbus\":" + str(cam1_data[2]) + ","
                #             "\"inbusspd\":" + str(cam1_data[3]) + ","
                #             "\"inped\":" + str(cam1_data[4]) + ","
                #             "\"inpedspd\":" + str(cam1_data[5]) + ","
                #             "\"incycle\":" + str(cam1_data[6]) + ","
                #             "\"incyclespd\":" + str(cam1_data[7]) + ","
                #             "\"intruck\":" + str(cam1_data[8]) + ","
                #             "\"intruckspd\":" + str(cam1_data[9]) + ","
                #             "\"outcar\":" + str(cam1_data[10]) + ","
                #             "\"outcarspd\":" + str(cam1_data[11]) + ","
                #             "\"outbus\":" + str(cam1_data[12]) + ","
                #             "\"outbusspd\":" + str(cam1_data[13]) + ","
                #             "\"outped\":" + str(cam1_data[14]) + ","
                #             "\"outpedspd\":" + str(cam1_data[15]) + ","
                #             "\"outcycle\":" + str(cam1_data[16]) + ","
                #             "\"outcyclespd\":" + str(cam1_data[17]) + ","
                #             "\"outtruck\":" + str(cam1_data[18]) + ","
                #             "\"outtruckspd\":" + str(cam1_data[19]) + "}")
                # cam2_data = [random.randrange(10,50),random.randrange(50,80), # in car
                #              random.randrange(2,10),random.randrange(20,50), # in bus
                #              random.randrange(40,100),random.randrange(1,10), # in ped
                #              random.randrange(0,1),random.randrange(0,1), # in cycle
                #              random.randrange(2,20),random.randrange(40,80), # in truck
                #              random.randrange(12,40),random.randrange(20,100), # out car
                #              random.randrange(1,2),random.randrange(30,85), # out bus
                #              random.randrange(1,3),random.randrange(1,9), # out ped
                #              random.randrange(1,25),random.randrange(1,20), # out cycle
                #              random.randrange(1,30),random.randrange(40,100), # out truck
                #              ]
                # response2 = ("{\"incar\":" + str(cam2_data[0]) + ","
                #             "\"incarspd\":" + str(cam2_data[1]) + ","
                #             "\"inbus\":" + str(cam2_data[2]) + ","
                #             "\"inbusspd\":" + str(cam2_data[3]) + ","
                #             "\"inped\":" + str(cam2_data[4]) + ","
                #             "\"inpedspd\":" + str(cam2_data[5]) + ","
                #             "\"incycle\":" + str(cam2_data[6]) + ","
                #             "\"incyclespd\":" + str(cam2_data[7]) + ","
                #             "\"intruck\":" + str(cam2_data[8]) + ","
                #             "\"intruckspd\":" + str(cam2_data[9]) + ","
                #             "\"outcar\":" + str(cam2_data[10]) + ","
                #             "\"outcarspd\":" + str(cam2_data[11]) + ","
                #             "\"outbus\":" + str(cam2_data[12]) + ","
                #             "\"outbusspd\":" + str(cam2_data[13]) + ","
                #             "\"outped\":" + str(cam2_data[14]) + ","
                #             "\"outpedspd\":" + str(cam2_data[15]) + ","
                #             "\"outcycle\":" + str(cam2_data[16]) + ","
                #             "\"outcyclespd\":" + str(cam2_data[17]) + ","
                #             "\"outtruck\":" + str(cam2_data[18]) + ","
                #             "\"outtruckspd\":" + str(cam2_data[19]) + "}")
                dnn_dict1 = get_dnn_date(cam1_dnn_socket)
                dnn_dict2 = get_dnn_date(cam1_dnn_socket)
                response1 = json.dumps(dnn_dict1)
                response2 = json.dumps(dnn_dict2)
                uart.send_serial(response1)
                uart.send_serial(response2)
            elif string[:3] == "?PS":
                index = int(string[3:])
                if index in [1, 2]:
                    if index == 1:
                        cam_info_socket = cam1_info_socket
                    else:
                        cam_info_socket = cam2_info_socket
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
                    #exposure, gain = read_exposure_and_gain()
                    # ae_model, awb_model = read_ae_awb_mode()
                    ps_data = config[f"?PS{index}"][0]
                    ps_data["Exposure"] = exposure
                    ps_data["Gain"] = gain

                    ps_data["AEModel"] = ae_status
                    ps_data["AWBMode"] = awb_status
                    ps_data["Time"] = current_time
                    print(f"sjx debug:{exposure},{gain},{ae_model},{awb_model}")
                    response = json.dumps(ps_data)
                    uart.send_serial(response)
                elif index in [3, 4]:
                    if index == 3:
                        cam_info_socket = cam1_info_socket
                    else:
                        cam_info_socket = cam2_info_socket
                    roi_data_g = RoiData(ROI_GET, 0, [])
                    cam_info_socket.sendall(roi_data_g.to_bytes())
                    response = cam_info_socket.recv(512)
                    if len(response) >= 2 + MAX_ROI_POINT * 8:
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
            print("--- %s seconds ---" % (time.time() - start_time))
    unmap_shared_memory(cam1_image_shm_ptr)
    cam1_image_shm.close_fd()
    # unmap_shared_memory(cam2_image_shm_ptr)
    # cam2_image_shm.close_fd()
    cam1_dnn_socket.close()

if __name__ == '__main__':
    main()