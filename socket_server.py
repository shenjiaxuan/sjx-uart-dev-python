import socket

def start_server():
    # 创建一个TCP/IP socket
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    
    # 绑定socket到本地地址和端口
    server_address = ('localhost', 10000)
    server_socket.bind(server_address)
    
    # 监听传入连接
    server_socket.listen(1)
    
    print('服务器启动，等待连接...')
    
    while True:
        # 等待连接
        client_socket, client_address = server_socket.accept()
        print(f'连接来自: {client_address}')
        
        try:
            while True:
                # 接收数据
                data = client_socket.recv(1024)
                if data:
                    print(f'收到数据: {data.decode()}')
                    # 回显数据给客户端
                    client_socket.sendall(data)
                else:
                    break
        finally:
            # 清理连接
            client_socket.close()
            print(f'连接关闭: {client_address}')

if __name__ == "__main__":
    start_server()