import numpy as np
import cv2

# 定义图像的分辨率和Bayer模式
width = 2016
height = 1520
bayer_pattern = 'RGGB'

# 读取RAW文件
with open('test.raw', 'rb') as f:
    raw_data = np.fromfile(f, dtype=np.uint16, count=width * height)

# 将一维数组转换为二维数组
raw_image = raw_data.reshape((height, width))

# 缩放像素值到0-255范围
raw_image = ((raw_image - 255) / (1023 - 255) * 255).astype(np.uint8)

# 使用OpenCV的demosaicing函数进行Bayer转换
rgb_image = cv2.cvtColor(raw_image, cv2.COLOR_BAYER_RGGB2BGR)

# 将RGB图像转换为灰度图像
gray_image = cv2.cvtColor(rgb_image, cv2.COLOR_BGR2GRAY)

# 保存为JPEG文件
cv2.imwrite('test_gray.jpg', gray_image)

print("转换完成并保存为test_gray.jpg")
