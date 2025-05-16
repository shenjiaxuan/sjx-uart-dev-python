import socket
import json

def send_emer_mode(host='127.0.0.1', port=5555, emer_mode_value=1):
    try:
        # 创建 TCP socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((host, port))
        
        # 创建消息
        msg = json.dumps({"EmergMode": emer_mode_value})
        # 发送消息，注意编码为 bytes
        sock.sendall(msg.encode('utf-8'))
        print(f"Sent message: {msg}")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        sock.close()

if __name__ == '__main__':
    send_emer_mode()