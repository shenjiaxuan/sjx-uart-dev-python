#!/usr/bin/env python3

"""
Description   : This script performs simulation data communication between IMX500 and Itron NLC
Author        : Fang Du
Email         : fang.du@sony.com
Date Created  : 08-24-2023
Date Modified : 06-27-2024
Version       : 1.2
Python Version: 3.9.2
Dependencies  : serial, pillow
License       : © 2024 - Sony Semiconductor Solution America United State Technology Center
History       :
              : 1.0 - simulate the data communication for demo purpose only, reference document AITRIOS Traffic Monitoring Interface version Demo Only - v4 Fang.xlsx
              : 1.1 - simulate the data communication for first generation product, reference document AITRIOS Traffic Monitoring interface version 1.5.xlsx
                1.2 - bug fixed. Change baudrate to 38400, remove receiving "im", update image data after receiving "?OBdata", Show real text message instead of lens
"""

import serial
import base64
import time
import math
import random
from PIL import Image
import json

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

def load_camera_info():
    with open('camera_info.json', 'r') as file:
        return json.load(file)

class UART:
    def __init__(self):
        self.uartport = serial.Serial(
                # port="/dev/ttyAMA1",
                port="COM1",  # 修改串口端口为 COM1
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
        #print(time.strftime("%B-%d-%Y %H:%M:%S") + "  ->: {0}".format(len(cmd)))
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
    # convert image to string
    with open("converted-jpg-image.jpg", "rb") as image2string:
        converted_string = base64.b64encode(image2string.read()).decode()
        # calculate blocks number
    str_len = len(converted_string)
    send_time = math.ceil(str_len / send_max_length)
    str_image = []
    # set each block value
    for x in range(send_time):
        str_image.append(converted_string[x*send_max_length:(x+1)*send_max_length])


if __name__ == '__main__':
    # enable uart
    uart = UART()
    update_sim_attribute()
    while True:
        raw_data = uart.receive_serial()
        if raw_data:
            start_time = time.time()
            string = raw_data.decode("utf_8","ignore").rstrip()
            print(time.strftime("%B-%d-%Y %H:%M:%S") + "  <-: {0}".format(string))
            if string == "?Asset":
                response = ("{\"MfrName\":\"Leopard\","
                            "\"ModelNumber\":\"IMX501_EV1\","
                            "\"SerialNumber\":\"1A325G32\","
                            "\"MfgDate\":\"20240103\","
                            "\"FWVersion\":\"1.0.0\","
                            "\"HWVersion\":\"1.0.2\","
                            "\"AppNumber\":\"699\"}")
                uart.send_serial(response)          
            elif string[:2] == "@|":
                if string[2:] and int(string[2:]) > 0:
                    count_interval = str(string[2:])
                response = "{\"NICFrequency\":" + count_interval + "}"
                uart.send_serial(response)  
            elif string == "?Order":
                response = ("{\"PassThAttr\":\"620,621,622,623,624,625,626,627,628,629,630,631,632,633,634,635,636,637,638,639,640,641,642,643\","
                            "\"ImageAttr\":\"624,625,626,627,628,629,630,631,632,633,634,635,636,637,638,639,640,641,642,643\","
                            "\"Cam1SetAttr\":\"620\","
                            "\"Cam2SetAttr\":\"621\","
                            "\"AIProessAttr\":\"622,623\"}")
                uart.send_serial(response)
            elif string[:8] == "Profile|":
                if string[8:] and int(string[8:]) in [0, 1, 2, 3, 16, 17, 18, 19]:
                    profile_index = str(string[8:])
                response = "{\"CamProfile\":" + profile_index + "}"
                uart.send_serial(response)  
            elif string[:5] == "WiFi|":
                if string[5:] and int(string[5:]) in [0, 1]:
                    wifi_status = str(string[5:])
                response = "{\"WiFiEnable\":" + wifi_status + "}"
                uart.send_serial(response)  
            elif string == "?ERR":
                response = "{\"Cam1ErrCode\":\"0\",\"Cam2ErrCode\":\"0\"}"
                uart.send_serial(response)
            elif string[:6] == "REACT|":
                if string[6:] and int(string[6:]) in range(0, 27):
                    ener_mode = str(string[6:])
                response = "{\"EmergencyMode\":" + ener_mode + "}"
                uart.send_serial(response)
            elif string == "?OBdata":
                update_sim_attribute()
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
                uart.send_serial(response1)
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
                uart.send_serial(response2)
            elif string[:3] == "?PS":
                index = int(string[3:])
                if index in [1, 2]: # camera settings
                    response = ("{\"CameraFPS\":\"60\","
                                "\"ImageSize\":\"640*320\","
                                "\"PixelDepth\":\"RAW10\","
                                "\"PixelOrder\":\"RGGB\","
                                "\"DNNModel\":\"TrafficCount20231102\","
                                "\"PostProcessingLogic\":\"8:00-PostProcessing1,19:00-PostProcessing2\","
                                "\"SendImageQuality\":\"100\","
                                "\"SendImageSizePercent\":\"100\","
                                "\"AEModel\":\"auto\","
                                "\"Exposure\":\"1120\","
                                "\"Gain\":\"1\","
                                "\"AWBMode\":\"enable\","
                                "\"Power\":\"1.2W\","
                                "\"Heating\":\"enable\","
                                "\"Dust\":\"enable\","
                                "\"Time\":\"12/08/2023 14:00:58\"}")
                    uart.send_serial(response)
                elif index in [3, 4]:
                    response = ("{\"OutcomingRefLine_x1\":\"100\","
                                "\"OutcomingRefLine_y1\":\"500\","
                                "\"OutcomingRefLine_x2\":\"100\","
                                "\"OutcomingRefLine_y2\":\"200\"}")
                    uart.send_serial(response)
                else:
                    if (index-5) < len(str_image):
                        response = "{\"Block" + str(index-4) + ":" + str_image[index-5] + "}"
                        uart.send_serial(response)
            print("--- %s seconds ---" % (time.time() - start_time))