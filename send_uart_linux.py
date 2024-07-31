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

random.seed(1)
image_folder = '/home/root/sjx/input_tensors/'
send_max_length = 980
count_interval = "300"
wifi_status = "0"
profile_index = "1"
ener_mode = "0"
image_index = 1
send_time = 0
str_image = []

def load_config():
    with open('/home/root/sjx/config.json', 'r') as file:
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

config = load_config()

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

def update_sim_attribute():
    global str_image
    global image_index
    if image_index > 10:
        image_index = 1
    image_file_name = image_folder + str(image_index) + ".bmp"
    image_index = image_index + 1
    image = Image.open(image_file_name)
    image.save("/home/root/sjx/converted-jpg-image.jpg", optimize=True, quality=10)
    with open("/home/root/sjx/converted-jpg-image.jpg", "rb") as image2string:
        converted_string = base64.b64encode(image2string.read()).decode()
    str_len = len(converted_string)
    send_time = math.ceil(str_len / send_max_length)
    str_image = []
    for x in range(send_time):
        str_image.append(converted_string[x*send_max_length:(x+1)*send_max_length])

def start_client(command):
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_address = ('localhost', 10045)
    client_socket.connect(server_address)
    try:
        client_socket.sendall(command.encode())
    finally:
        client_socket.close()

if __name__ == '__main__':
    uart = UART()
    update_sim_attribute()
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
                    start_client(string)
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
                config = load_config()
                response = json.dumps(config["?ERR"][0])
                uart.send_serial(response)
            elif string[:6] == "REACT|":
                if string[6:] and int(string[6:]) in range(0, 27):
                    ener_mode = str(string[6:])
                    start_client(string)
                response = json.dumps({"EmergencyMode": int(ener_mode)})
                uart.send_serial(response)
                if int(ener_mode) in range(0, 27):
                    pass
                    ener_mode = "0"
            elif string == "?OBdata":
                start_client(string)
                update_sim_attribute()
                # response1 = json.dumps(config["?OBdata"][0])
                # response2 = json.dumps(config["?OBdata"][1])
                # uart.send_serial(response1)
                # uart.send_serial(response2)
                cam1_data = [random.randrange(10,50),random.randrange(50,80), # in car
                             random.randrange(2,10),random.randrange(20,50), # in bus
                             random.randrange(40,100),random.randrange(1,10), # in ped
                             random.randrange(0,1),random.randrange(0,1), # in cycle
                             random.randrange(2,20),random.randrange(40,80), # in truck
                             random.randrange(12,40),random.randrange(20,100), # out car
                             random.randrange(1,2),random.randrange(30,85), # out bus
                             random.randrange(1,3),random.randrange(1,9), # out ped
                             random.randrange(1,25),random.randrange(1,20), # out cycle
                             random.randrange(1,30),random.randrange(40,100), # out truck
                             ]
                response1 = ("{\"spdunit\":\"MPH\","
                            "\"incar\":" + str(cam1_data[0]) + ","
                            "\"incarspd\":" + str(cam1_data[1]) + ","
                            "\"inbus\":" + str(cam1_data[2]) + ","
                            "\"inbusspd\":" + str(cam1_data[3]) + ","
                            "\"inped\":" + str(cam1_data[4]) + ","
                            "\"inpedspd\":" + str(cam1_data[5]) + ","
                            "\"incycle\":" + str(cam1_data[6]) + ","
                            "\"incyclespd\":" + str(cam1_data[7]) + ","
                            "\"intruck\":" + str(cam1_data[8]) + ","
                            "\"intruckspd\":" + str(cam1_data[9]) + ","
                            "\"outcar\":" + str(cam1_data[10]) + ","
                            "\"outcarspd\":" + str(cam1_data[11]) + ","
                            "\"outbus\":" + str(cam1_data[12]) + ","
                            "\"outbusspd\":" + str(cam1_data[13]) + ","
                            "\"outped\":" + str(cam1_data[14]) + ","
                            "\"outpedspd\":" + str(cam1_data[15]) + ","
                            "\"outcycle\":" + str(cam1_data[16]) + ","
                            "\"outcyclespd\":" + str(cam1_data[17]) + ","
                            "\"outtruck\":" + str(cam1_data[18]) + ","
                            "\"outtruckspd\":" + str(cam1_data[19]) + "}")
                cam2_data = [random.randrange(10,50),random.randrange(50,80), # in car
                             random.randrange(2,10),random.randrange(20,50), # in bus
                             random.randrange(40,100),random.randrange(1,10), # in ped
                             random.randrange(0,1),random.randrange(0,1), # in cycle
                             random.randrange(2,20),random.randrange(40,80), # in truck
                             random.randrange(12,40),random.randrange(20,100), # out car
                             random.randrange(1,2),random.randrange(30,85), # out bus
                             random.randrange(1,3),random.randrange(1,9), # out ped
                             random.randrange(1,25),random.randrange(1,20), # out cycle
                             random.randrange(1,30),random.randrange(40,100), # out truck
                             ]
                response2 = ("{\"incar\":" + str(cam2_data[0]) + ","
                            "\"incarspd\":" + str(cam2_data[1]) + ","
                            "\"inbus\":" + str(cam2_data[2]) + ","
                            "\"inbusspd\":" + str(cam2_data[3]) + ","
                            "\"inped\":" + str(cam2_data[4]) + ","
                            "\"inpedspd\":" + str(cam2_data[5]) + ","
                            "\"incycle\":" + str(cam2_data[6]) + ","
                            "\"incyclespd\":" + str(cam2_data[7]) + ","
                            "\"intruck\":" + str(cam2_data[8]) + ","
                            "\"intruckspd\":" + str(cam2_data[9]) + ","
                            "\"outcar\":" + str(cam2_data[10]) + ","
                            "\"outcarspd\":" + str(cam2_data[11]) + ","
                            "\"outbus\":" + str(cam2_data[12]) + ","
                            "\"outbusspd\":" + str(cam2_data[13]) + ","
                            "\"outped\":" + str(cam2_data[14]) + ","
                            "\"outpedspd\":" + str(cam2_data[15]) + ","
                            "\"outcycle\":" + str(cam2_data[16]) + ","
                            "\"outcyclespd\":" + str(cam2_data[17]) + ","
                            "\"outtruck\":" + str(cam2_data[18]) + ","
                            "\"outtruckspd\":" + str(cam2_data[19]) + "}")
                uart.send_serial(response1)
                uart.send_serial(response2)
            elif string[:3] == "?PS":
                index = int(string[3:])
                if index in [1, 2]:
                    current_time = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                    exposure, gain = read_exposure_and_gain()
                    ae_model, awb_model = read_ae_awb_mode()
                    ps_data = config[f"?PS{index}"][0]
                    ps_data["Exposure"] = exposure
                    ps_data["Gain"] = gain
                    ps_data["AEModel"] = ae_model
                    ps_data["AWBMode"] = awb_model
                    ps_data["Time"] = current_time
                    response = json.dumps(ps_data)
                    uart.send_serial(response)
                elif index in [3, 4]:
                    response = json.dumps(config[f"?PS{index}"][0])
                    uart.send_serial(response)
                else:
                    if (index - 5) < len(str_image):
                        response = "{\"Block" + str(index - 4) + ":" + str_image[index - 5] + "}"
                        uart.send_serial(response)
            print("--- %s seconds ---" % (time.time() - start_time))
