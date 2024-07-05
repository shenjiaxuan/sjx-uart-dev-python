import numpy as np
import cv2

# 定义图像的分辨率和Bayer模式
width = 2016
height = 1530
bayer_pattern = 'RGGP'

# 读取RAW文件
with open('test.raw', 'rb') as f:
    raw_data = np.fromfile(f, dtype=np.uint16, count=width * height)

# 将一维数组转换为二维数组
raw_image = raw_data.reshape((height, width))

# 缩放像素值到0-255范围
raw_image = ((raw_image - 255) / (1023 - 255) * 255).astype(np.uint8)

# 使用OpenCV的demosaicing函数进行Bayer转换
rgb_image = cv2.cvtColor(raw_image, cv2.COLOR_BAYER_RGGB2RGB)

# 颜色校正矩阵（示例）
color_matrix = np.array([[1.2, -0.2, 0.0],
                         [-0.1, 1.1, 0.0],
                         [0.0, -0.1, 1.0]])

# 应用颜色校正
rgb_image = cv2.transform(rgb_image, color_matrix)

# 白平衡增益（示例）
wb_gains = [1.5, 1.0, 2.0]  # R, G, B

# 将rgb_image转换为float32类型
rgb_image = rgb_image.astype(np.float32)

# 应用白平衡
rgb_image[:, :, 0] *= wb_gains[0]
rgb_image[:, :, 1] *= wb_gains[1]
rgb_image[:, :, 2] *= wb_gains[2]

# 确保像素值在0-255范围内
rgb_image = np.clip(rgb_image, 0, 255)

# 将rgb_image转换回uint8类型
rgb_image = rgb_image.astype(np.uint8)

# 保存为JPEG文件
cv2.imwrite('test.jpg', rgb_image)

print("转换完成并保存为test.jpg")
