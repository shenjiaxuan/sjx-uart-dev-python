import struct
CAMERA1_DIAGNOSE_INFO_PATH = "/home/root/AglaiaSense/resource/share_config/diagnose_info_1.json"
CAMERA2_DIAGNOSE_INFO_PATH = "/home/root/AglaiaSense/resource/share_config/diagnose_info_2.json"
LEFT_SHM_BMP_NAME = "/left_imx501_bmp_shm"
RIGHT_SHM_BMP_NAME = "/right_imx501_bmp_shm"
LOG_FOLDER = "log"
SHM_BMP_SIZE = 36936000
CONFIG_PATH = '/home/root/AglaiaSense/resource/share_config/uart_config.json'

CAM1_ID = 1
CAM2_ID = 2
CAM1_INFO_PORT = 10808
CAM2_INFO_PORT = 10809
CAM1_DNN_PORT = 11808
CAM2_DNN_PORT = 11809

# define socket commands
SET_GAIN = 0x10
GET_GAIN = 0x11
SET_EXPOSURE = 0x12
GET_EXPOSURE = 0x13
SET_FRAMERATE = 0x14
GET_FRAMERATE = 0x15
GET_AE_MODE = 0x16
SET_AE_MODE = 0x17
GET_AWB_MODE = 0x18
SET_AWB_MODE = 0x19
BMP_GET = 0x1A
DNN_GET = 0x1C
GET_FIRMWARE = 0x1D
UPDATE_FIRMWARE = 0x1E
ROI_SET = 0x1F
ROI_GET = 0x20
CAM_EN = 0x21
ENERGENCY_MODE = 0x22
WHOIAM = 0x23
GET_STATUS = 0x24

# define pic size
IMAGE_CHANNELS = 3
IMAGE_HEIGHT = 300
IMAGE_WIDTH = 300

MAX_ROI_POINT = 50

class ProtoData:
    def __init__(self):
        self.val = bytearray(512)

    def to_bytes(self):
        return bytes(self.val)

class GainData:
    def __init__(self, cmd, val=0):
        self.cmd = cmd
        self.val = val

    def to_bytes(self):
        proto_data = ProtoData()
        struct.pack_into('BB', proto_data.val, 0, self.cmd, self.val)
        return proto_data.to_bytes()

    @classmethod
    def from_bytes(cls, data):
        cmd, val = struct.unpack('BB', data[:2])
        return cls(cmd, val)

class ExposureData:
    def __init__(self, cmd, val=0):
        self.cmd = cmd
        self.val = val

    def to_bytes(self):
        proto_data = ProtoData()
        struct.pack_into('BB', proto_data.val, 0, self.cmd, self.val)
        return proto_data.to_bytes()

    @classmethod
    def from_bytes(cls, data):
        cmd, val = struct.unpack('BB', data[:2])
        return cls(cmd, val)

class FrameRateData:
    def __init__(self, cmd, val=0):
        self.cmd = cmd
        self.val = val

    def to_bytes(self):
        proto_data = ProtoData()
        struct.pack_into('BB', proto_data.val, 0, self.cmd, self.val)
        return proto_data.to_bytes()

    @classmethod
    def from_bytes(cls, data):
        cmd, val = struct.unpack('BB', data[:2])
        return cls(cmd, val)

class AeModeData:
    def __init__(self, cmd, val=0):
        self.cmd = cmd
        self.val = val

    def to_bytes(self):
        proto_data = ProtoData()
        struct.pack_into('BB', proto_data.val, 0, self.cmd, self.val)
        return proto_data.to_bytes()

    @classmethod
    def from_bytes(cls, data):
        cmd, val = struct.unpack('BB', data[:2])
        return cls(cmd, val)

class AwbModeData:
    def __init__(self, cmd, val=0):
        self.cmd = cmd
        self.val = val

    def to_bytes(self):
        proto_data = ProtoData()
        struct.pack_into('BB', proto_data.val, 0, self.cmd, self.val)
        return proto_data.to_bytes()

    @classmethod
    def from_bytes(cls, data):
        cmd, val = struct.unpack('BB', data[:2])
        return cls(cmd, val)

class CamEn:
    def __init__(self, cmd, val=3):
        self.cmd = cmd
        self.val = val

    def to_bytes(self):
        proto_data = ProtoData()
        struct.pack_into('BB', proto_data.val, 0, self.cmd, self.val)
        return proto_data.to_bytes()

class EnergencyMode:
    def __init__(self, cmd, val=0):
        self.cmd = cmd
        self.val = val

    def to_bytes(self):
        proto_data = ProtoData()
        struct.pack_into('BB', proto_data.val, 0, self.cmd, self.val)
        return proto_data.to_bytes()

class BmpData:
    def __init__(self, cmd, shmName='', size=0):
        self.cmd = cmd
        self.shmName = shmName
        self.size = size

    def to_bytes(self):
        proto_data = ProtoData()
        struct.pack_into('B31sI', proto_data.val, 0, self.cmd, self.shmName.encode('utf-8'), self.size)
        return proto_data.to_bytes()

    @classmethod
    def from_bytes(cls, data):
        cmd, shmName, size = struct.unpack('B31sI', data[:36])
        shmName = shmName.decode('utf-8').strip('\x00')
        return cls(cmd, shmName, size)

class DnnDataYolo:
    def __init__(self, cmd=0, name='', x_start=0, y_start=0, x_end=0, y_end=0):
        self.cmd = cmd
        self.name = name
        self.x_start = x_start
        self.y_start = y_start
        self.x_end = x_end
        self.y_end = y_end

    def to_bytes(self):
        proto_data = ProtoData()
        name_bytes = self.name.encode('utf-8')[:31] + b'\x00' * (31 - len(self.name))
        struct.pack_into('B 31s I I I I', proto_data.val, 0, self.cmd, name_bytes, self.x_start, self.y_start, self.x_end, self.y_end)
        return proto_data.to_bytes()

    @classmethod
    def from_bytes(cls, data):
        if len(data) < 48:
            raise ValueError(f"Data is too short: expected at least 48 bytes, got {len(data)}.")
        cmd, name_bytes, x_start, y_start, x_end, y_end = struct.unpack('B 31s I I I I', data[:48])
        name = name_bytes.decode('utf-8').strip('\x00')
        return cls(cmd, name, x_start, y_start, x_end, y_end)

    def to_dict(self):
        return {
            'cmd': self.cmd,
            'name': self.name,
            'x_start': self.x_start,
            'y_start': self.y_start,
            'x_end': self.x_end,
            'y_end': self.y_end
        }

class RoiData:
    def __init__(self, cmd, point_number, points):
        self.cmd = cmd
        self.point_number = point_number
        self.x = [0] * MAX_ROI_POINT
        self.y = [0] * MAX_ROI_POINT

        # 初始化 x 和 y
        for i in range(min(point_number, MAX_ROI_POINT)):
            self.x[i] = points[i]['x']
            self.y[i] = points[i]['y']

    def to_bytes(self):
        data_format = f'B B {MAX_ROI_POINT}I {MAX_ROI_POINT}I'
        roi_data_bytes = struct.pack(data_format, self.cmd, self.point_number, *self.x, *self.y)

        ProData = bytearray(512)
        ProData[:len(roi_data_bytes)] = roi_data_bytes
        return ProData

    @classmethod
    def from_bytes(cls, data):
        # Unpack the data
        fmt = f'BB{MAX_ROI_POINT}I{MAX_ROI_POINT}I'
        unpacked = struct.unpack(fmt, data[:struct.calcsize(fmt)])
        
        cmd, point_number = unpacked[0], unpacked[1]
        x = list(unpacked[2:2+MAX_ROI_POINT])
        y = list(unpacked[2+MAX_ROI_POINT:2+2*MAX_ROI_POINT])
        
        points = [{'x': x[i], 'y': y[i]} for i in range(point_number)]
        return cls(cmd, point_number, points)
