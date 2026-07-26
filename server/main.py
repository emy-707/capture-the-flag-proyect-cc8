import socket
import sys
import os
import select
import struct

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.protocol import receive_tcp_message, unpack_str, send_tcp_message

HOST = '0.0.0.0'
PORT = 5001

def start_server():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    # Modo no bloqueante: evita que el servidor se congele si no hay conexiones entrantes inmediatas
    server_socket.setblocking(False) 
    server_socket.bind((HOST, PORT))
    server_socket.listen(15) 
    
    sockets_list = [server_socket]
    clients = {}
    player_counter = 1
    game_id = 1001 
    
    print(f"Servidor TCP V2 en estado WAITING en puerto {PORT}...")
    print("Presiona Ctrl+C para apagarlo.")
    
    while True:
        # select() vigila quién tiene mensajes listos para leer
        # La función select vigila todas las conexiones de red al mismo tiempo y devuelve tres listas:
        # Sockets que enviaron un mensaje (read_sockets).
        # Sockets listos para que se les envíe algo (aquí se ignora con un _).
        # Sockets que sufrieron un error fatal o crítico (exception_sockets).

        read_sockets, _, exception_sockets = select.select(sockets_list, [], sockets_list, 0.05)
        
        for notified_socket in read_sockets:
            if notified_socket == server_socket:
                # EVENTO A: Alguien nuevo se está conectando
                client_socket, client_address = server_socket.accept()
                client_socket.setblocking(False)
                sockets_list.append(client_socket)
                
                # Se le asigna un ID interno
                clients[client_socket] = {"playerId": player_counter}
                player_counter += 1
                
            else:
                # EVENTO B: Mensaje de un cliente que ya estaba conectado
                msg_type, payload = receive_tcp_message(notified_socket)
                
                # Desconexión
                if msg_type is None:
                    p_id = clients[notified_socket].get("playerId", "?")
                    print(f"Cliente P{p_id} se desconectó.")
                    sockets_list.remove(notified_socket)
                    del clients[notified_socket]
                    continue
                    
                # Mensaje JOIN (0x10)
                if msg_type == 0x10: 
                    player_name, _ = unpack_str(payload)
                    p_id = clients[notified_socket]["playerId"]
                    clients[notified_socket]["name"] = player_name
                    print(f"P{p_id:02d} se unió con el nombre: {player_name}")
                    
                    # Responder con JOIN_ACCEPTED (0x20)
                    # Formato del protocolo: u16 playerId, u16 gameId
                    response_payload = struct.pack('>HH', p_id, game_id)
                    send_tcp_message(notified_socket, 0x20, response_payload)
                    print(f" -> Enviado paquete JOIN_ACCEPTED a P{p_id:02d}")

        # Limpieza de errores
        # Garantiza que si un cliente se sale, el servidor simplemente barre los restos 
        # y sigue funcionando para los demás como si nada hubiera pasado.
        for notified_socket in exception_sockets:
            if notified_socket in sockets_list:
                sockets_list.remove(notified_socket)
            if notified_socket in clients:
                del clients[notified_socket]

if __name__ == "__main__":
    start_server()