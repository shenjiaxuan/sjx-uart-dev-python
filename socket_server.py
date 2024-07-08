import socket

def start_server():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_address = ('localhost', 10045)
    server_socket.bind(server_address)
    
    server_socket.listen(1)
    print('Server is up, awaiting connection...')
    
    while True:
        client_socket, client_address = server_socket.accept()
        print(f'connect from: {client_address}')

        try:
            while True:
                message = client_socket.recv(1024).decode()
                if not message:
                    break
                if message[:6] == "REACT|":
                    print(f'get message: {message}')
                    #To Do
                elif message == "?OBdata":
                    print(f'get message: {message}')
                    #To Do
                else:
                    break
        finally:
            client_socket.close()
            print(f'close connection: {client_address}')

if __name__ == "__main__":
    try:
        start_server()
    except KeyboardInterrupt:
        print("\nServer terminated by user.")