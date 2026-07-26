import socket
import sys
import os
import time
import struct

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.protocol import  send_tcp_message, pack_str, receive_tcp_message

PORT = 5001
HOST = '127.0.0.1' # Conectando a nuestra propia máquina

def start_client():
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    
    try:
        client_socket.connect((HOST, PORT))
        client_socket.setblocking(False) # Hacemos el socket no bloqueante
        print("Conectado al servidor. Enviando petición de ingreso...")
        
        # Enviar JOIN (0x10)
        join_payload = pack_str("Jugador1")
        send_tcp_message(client_socket, 0x10, join_payload)
        
        my_player_id = 0
        timeout = time.time() + 5.0 # Esperar máximo 5 segundos
        
        print("Esperando respuesta del servidor...")
        while time.time() < timeout:
            msg_type, payload = receive_tcp_message(client_socket)
            
            if msg_type is None:
                continue # Como es no bloqueante, sigue intentando sin frenarse
                
            # JOIN_ACCEPTED
            if msg_type == 0x20: 
                # Desempaquetar u16 playerId y u16 gameId (ambos de 2 bytes)
                my_player_id, game_id = struct.unpack('>HH', payload)
                print(f"\n ¡Éxito! El servidor me aceptó.")
                print(f" -> Mi ID oficial asignado es: P{my_player_id:02d}")
                print(f" -> ID de la partida: {game_id}")
                break
            elif msg_type == 0x21: # JOIN_REJECTED
                print(" Fui rechazado por el servidor.")
                break
                
    except Exception as e:
        print(f"Error de conexión: {e}")
        
    print("\nTerminando prueba de cliente...")
    client_socket.close()

if __name__ == "__main__":
    start_client()