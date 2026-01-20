"""
WiFi密码控制功能测试脚本
通过串口发送WFPW|xxxx命令设置WiFi密码
"""

import serial
import base64
import json
import time


def encode_password(password: str) -> str:
    """将密码进行Base64编码"""
    return base64.b64encode(password.encode('utf-8')).decode('utf-8')


def decode_password(encoded_password: str) -> str:
    """将Base64编码的密码解码"""
    return base64.b64decode(encoded_password.encode('utf-8')).decode('utf-8')


def test_wifi_password(port: str, baudrate: int, password: str = None, timeout: float = 5.0) -> bool:
    """
    测试WiFi密码设置/查询功能

    Args:
        port: 串口号，如 'COM10'
        baudrate: 波特率
        password: 要设置的WiFi密码（明文），如果为None则查询当前密码
        timeout: 等待响应的超时时间（秒）

    Returns:
        bool: 测试是否通过
    """
    # 判断是设置密码还是查询密码
    if password:
        # 设置密码模式
        encoded_password = encode_password(password)
        command = f"WFPW|{encoded_password}\r\n"
        print(f"[INFO] 模式: 设置密码")
        print(f"[INFO] 原始密码: {password}")
        print(f"[INFO] Base64编码后: {encoded_password}")
    else:
        # 查询密码模式
        command = "WFPW|\r\n"
        print(f"[INFO] 模式: 查询密码")

    print(f"[INFO] 发送命令: {command.strip()}")

    try:
        # 打开串口
        ser = serial.Serial(
            port=port,
            baudrate=baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=timeout
        )

        print(f"[INFO] 串口 {port} 已打开，波特率: {baudrate}")

        # 清空缓冲区
        ser.reset_input_buffer()
        ser.reset_output_buffer()

        # 发送命令
        ser.write(command.encode('utf-8'))
        print("[INFO] 命令已发送，等待响应...")

        # 等待并读取响应
        start_time = time.time()
        response_data = b""

        while time.time() - start_time < timeout:
            if ser.in_waiting > 0:
                response_data += ser.read(ser.in_waiting)
                # 检查是否收到完整的JSON响应
                try:
                    response_str = response_data.decode('utf-8').strip()
                    if response_str.startswith('{') and response_str.endswith('}'):
                        break
                except:
                    pass
            time.sleep(0.1)

        ser.close()

        if not response_data:
            print("[FAIL] 未收到响应")
            return False

        response_str = response_data.decode('utf-8').strip()
        print(f"[INFO] 收到响应: {response_str}")

        # 解析JSON响应
        try:
            response_json = json.loads(response_str)
        except json.JSONDecodeError as e:
            print(f"[FAIL] JSON解析失败: {e}")
            return False

        # 检查Password字段
        if "Password" not in response_json:
            print("[FAIL] 响应中缺少Password字段")
            return False

        received_password = response_json["Password"]

        # 检查是否为空（表示失败）
        if not received_password:
            print("[FAIL] 返回的密码为空，操作失败")
            return False

        # 解码返回的密码
        try:
            decoded_received = decode_password(received_password)
            print(f"[INFO] 返回的密码(Base64): {received_password}")
            print(f"[INFO] 返回的密码(解码后): {decoded_received}")

            if password:
                # 设置密码模式：验证返回的密码是否与设置的一致
                if decoded_received == password:
                    print("[PASS] 密码设置成功，验证通过!")
                    return True
                else:
                    print(f"[FAIL] 密码不匹配! 期望: {password}, 实际: {decoded_received}")
                    return False
            else:
                # 查询密码模式：直接打印密码
                print(f"[PASS] 当前WiFi密码: {decoded_received}")
                return True
        except Exception as e:
            print(f"[FAIL] 解码返回密码失败: {e}")
            return False

    except serial.SerialException as e:
        print(f"[ERROR] 串口错误: {e}")
        return False
    except Exception as e:
        print(f"[ERROR] 发生异常: {e}")
        return False


def main():
    import argparse

    parser = argparse.ArgumentParser(description="WiFi密码控制功能测试")
    parser.add_argument("password", nargs="?", default=None, help="要设置的WiFi密码（明文），不提供则查询当前密码")
    parser.add_argument("-p", "--port", default="COM10", help="串口号（默认: COM10）")
    parser.add_argument("-b", "--baudrate", type=int, default=38400, help="波特率（默认: 38400）")
    parser.add_argument("-t", "--timeout", type=float, default=5.0, help="超时时间（秒，默认: 5.0）")

    args = parser.parse_args()

    print("=" * 50)
    print("WiFi密码控制功能测试")
    print("=" * 50)
    print(f"串口: {args.port}")
    print(f"波特率: {args.baudrate}")
    if args.password:
        print(f"操作: 设置密码 -> {args.password}")
    else:
        print(f"操作: 查询密码")
    print("=" * 50)

    result = test_wifi_password(args.port, args.baudrate, args.password, args.timeout)

    if result:
        print("\n[结果] 操作成功!")
    else:
        print("\n[结果] 操作失败!")


if __name__ == "__main__":
    main()
