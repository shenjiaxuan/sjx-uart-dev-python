import struct
CAMERA1_PORT = 10808
CAMERA2_PORT = 10809
CAMERA1_DNN_PORT = 11808
CAMERA2_DNN_PORT = 11809
CAMERA1_SHM_BMP_NAME = "/left_imx501_bmp_shm"
CAMERA2_SHM_BMP_NAME = "/right_imx501_bmp_shm"
SHM_BMP_SIZE = 36936000

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
RAW_GET = 0x1B
DNN_GET = 0x1C
GET_FIRMWARE = 0x1D
UPDATE_FIRMWARE = 0x1E
ROI_SET = 0x1F
ROI_GET = 0x20
CAM_EN = 0x21
ENERGENCY_MODE = 0x22
WHOIAM = 0x23
GET_STATUS = 0x24

E_FLGA_MANUAL = 0
E_FLGA_AUTO = 1
FW = 0
DNN = 1
E_FLGA_WEBSER = 0xF1
E_FLGA_DEVM = 0xF2
E_FLGA_UART = 0xF3
E_FLGA_DNN_SERVER = 0xF4

SOCK_COMM_LEN = 512
MAX_ROI_POINT = 50


class ProtoData:
    def __init__(self):
        self.val = bytearray(SOCK_COMM_LEN)

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

class FirmwareData:
    def __init__(self, cmd, type, md5='', file_path=''):
        self.cmd = cmd
        self.type = type
        self.md5 = md5
        self.file_path = str(file_path)

    def to_bytes(self):
        proto_data = ProtoData()
        struct.pack_into('B', proto_data.val, 0, self.cmd)
        struct.pack_into('128s', proto_data.val, 1, self.md5.encode('utf-8'))
        struct.pack_into('256s', proto_data.val, 129, self.file_path.encode('utf-8'))
        struct.pack_into('B', proto_data.val, 385, self.type)
        return proto_data.to_bytes()

    @classmethod
    def from_bytes(cls, data):
        cmd = struct.unpack('B', data[0:1])[0]
        md5 = struct.unpack('128s', data[1:129])[0].decode('utf-8').strip('\x00')
        file_path = struct.unpack('256s', data[129:385])[0].decode('utf-8').strip('\x00')
        type = struct.unpack('B', data[385:386])[0]
        return cls(cmd, type, md5, file_path)

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

class RawData:
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

class RoiData:
    def __init__(self, cmd, point_number, points):
        self.cmd = cmd
        self.point_number = point_number
        self.x = [0] * MAX_ROI_POINT
        self.y = [0] * MAX_ROI_POINT

        for i in range(min(point_number, MAX_ROI_POINT)):
            self.x[i] = points[i]['x']
            self.y[i] = points[i]['y']

    def to_bytes(self):
        data_format = f'B B {MAX_ROI_POINT}I {MAX_ROI_POINT}I'
        roi_data_bytes = struct.pack(data_format, self.cmd, self.point_number, *self.x, *self.y)

        ProData = bytearray(SOCK_COMM_LEN)
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

class ClientDev:
    def __init__(self, cmd, val=0):
        self.cmd = cmd
        self.val = val

    def to_bytes(self):
        proto_data = ProtoData()
        struct.pack_into('BI', proto_data.val, 0, self.cmd, self.val)
        return proto_data.to_bytes()

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
