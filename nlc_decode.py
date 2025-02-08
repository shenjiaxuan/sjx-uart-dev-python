import os
import base64
import json
from PIL import Image
import io

def hex_to_string(hex_data):
    """将十六进制数据转换为字符串，并在遇到换行符时截断"""
    try:
        byte_data = bytes.fromhex(hex_data)  # 将十六进制转换为字节
        string_data = byte_data.decode('utf-8')  # 将字节解码为字符串
        
        # 查找换行符的位置进行截断
        newline_index = string_data.find('\n')
        if newline_index != -1:
            string_data = string_data[:newline_index]
        return string_data

    except Exception as e:
        print(f"十六进制转换为字符串失败：{e}")
        return None

def process_file(filename):
    """读取文件，转换十六进制为字符串，解析 JSON 提取 Base64 数据并生成图片"""
    if not os.path.exists(filename):
        print(f"文件 {filename} 不存在！")
        return

    base64_strings = []  # 用于存储所有的 Base64 字符串片段

    with open(filename, 'r', encoding='utf-8') as file:
        for line_num, line in enumerate(file, start=1):
            line = line.strip()  # 去除行首尾的空白字符
            if line:
                try:
                    # 将十六进制数据转换为字符串
                    json_string = hex_to_string(line)
                    if not json_string:
                        print(f"第 {line_num} 行转换十六进制失败！")
                        continue

                    # 尝试解析为 JSON
                    data = json.loads(json_string)
                    for key, value in data.items():
                        if isinstance(value, str):
                            # 将 Base64 数据片段添加到列表中
                            print(f"Base64 data size: {len(value)}")  # 打印 Base64 数据的大小
                            base64_strings.append(value)
                except json.JSONDecodeError:
                    print(f"第 {line_num} 行 JSON 解析失败：{json_string}")
                except Exception as e:
                    print(f"处理第 {line_num} 行时出现错误：{e}")
    
    # 合并 Base64 字符串并保存为图片
    save_image_from_list(base64_strings)

def save_image_from_list(base64_strings):
    """将合并的 Base64 数据片段解码并保存为 BMP 图片"""
    try:
        # 将所有 Base64 数据片段合并成一个完整的字符串
        complete_base64_data = ''.join(base64_strings)
        # 解码 Base64 数据
        image_binary = base64.b64decode(complete_base64_data)
        # 使用 Pillow 将二进制数据转换为图片
        image = Image.open(io.BytesIO(image_binary))
        # 保存为 BMP 格式
        filename = "complete_image.bmp"
        image.save(filename, format='BMP')
        print(f"图片已保存到 {filename}")
    except Exception as e:
        print(f"保存图片时出现错误：{e}")

if __name__ == '__main__':
    # 输入文件路径
    input_filename = 'uart_nlc.txt'

    # 处理文件内容
    process_file(input_filename)
