import socket
import serial
import base64
import time
import math
import random
from PIL import Image
import json
import subprocess

random.seed(1)
image_folder = 'input_tensors/'
send_max_length = 980
count_interval = "300"
wifi_status = "0"
profile_index = "1"
ener_mode = "0"
image_index = 1
send_time = 0
str_image = []

def load_config():
    with open('config.json', 'r') as file:
        return json.load(file)

def get_wifi_status():
    result = subprocess.run(['nmcli', '-t', '-f', 'WIFI', 'radio'], capture_output=True, text=True)
    return result.stdout.strip()

config = load_config()

class UART:
    def __init__(self):
        self.uartport = serial.Serial(
                # port="/dev/ttyAMA1",
                port="COM1",
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
    image.save("converted-jpg-image.jpg",optimize=True,quality=10)
    with open("converted-jpg-image.jpg", "rb") as image2string:
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
            string = raw_data.decode("utf_8","ignore").rstrip()
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
                response = json.dumps({"CamProfile": int(profile_index)})
                uart.send_serial(response)  
            elif string[:5] == "WiFi|":
                # if get_wifi_status() == 'enabled':
                #     wifi_cur_config = 1
                # else:
                #     wifi_cur_config = 0
                if string[5:] and int(string[5:]) in [0, 1]:
                    wifi_status = str(string[5:])
                #     if wifi_cur_config != int(wifi_status):
                #         subprocess.run(['nmcli', 'radio', 'wifi', wifi_status])
                # else:
                #     wifi_status = wifi_cur_config
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
                response1 = json.dumps(config["?OBdata"][0])
                response2 = json.dumps(config["?OBdata"][1])
                uart.send_serial(response1)
                uart.send_serial(response2)
            elif string[:3] == "?PS":
                index = int(string[3:])
                if index in [1, 2]:
                    response = json.dumps(config[f"?PS{index}"][0])
                    uart.send_serial(response)
                elif index in [3, 4]:
                    response = json.dumps(config[f"?PS{index}"][0])
                    uart.send_serial(response)
                else:
                    if (index-5) < len(str_image):
                        response = "{\"Block" + str(index-4) + ":" + str_image[index-5] + "}"
                        uart.send_serial(response)
            print("--- %s seconds ---" % (time.time() - start_time))
