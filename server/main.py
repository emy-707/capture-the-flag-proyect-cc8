import socket
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.protocol import receive_tcp_message, unpack_str

HOST = '0.0.0.0'
PORT = 5000

def start_server():
    # Configuración básica del socket TCP
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((HOST, PORT))
    server_socket.listen(1) 
    
    print(f"Servidor de prueba escuchando en puerto {PORT}...")

    # Aceptamos solo una conexión para la prueba
    client_socket, client_address = server_socket.accept()
    print(f"Nueva conexión entrante desde {client_address}")

    msg_type, payload = receive_tcp_message(client_socket)
    
    if msg_type is None:
        print("El cliente se desconectó o hubo un error en la lectura.")
    elif msg_type == 0x10: # 0x10 es el código del mensaje JOIN
        # Desempaquetamos el string dinámico
        player_name, _ = unpack_str(payload)
        print(f"Mensaje JOIN recibido correctamente.")
        print(f" -> Nombre del jugador decodificado: {player_name}")
    else:
        print(f"Mensaje recibido, pero no es un JOIN. Tipo: {hex(msg_type)}")

    # Cerramos para terminar la prueba
    client_socket.close()
    server_socket.close()

if __name__ == "__main__":
    start_server()