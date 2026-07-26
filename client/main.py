import socket
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.protocol import  send_tcp_message, pack_str

PORT = 5000
HOST = '127.0.0.1' # Conectando a nuestra propia máquina

def start_client():
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    
    try:
        client_socket.connect((HOST, PORT))
        print("Conectado al servidor con éxito.")
        
        # Empaquetamos el nombre como lo pide el protocolo
        nombre_jugador = "Jugador1"
        join_payload = pack_str(nombre_jugador)
        
        print(f"Enviando paquete JOIN con nombre '{nombre_jugador}'...")
        
        # 0x10 es el tipo de mensaje JOIN
        send_tcp_message(client_socket, 0x10, join_payload)
        
    except ConnectionRefusedError:
        print("Error: El servidor no está encendido.")
        
    # Cerramos la conexión
    client_socket.close()

if __name__ == "__main__":
    start_client()