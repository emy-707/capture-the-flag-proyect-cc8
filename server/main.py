import socket
import sys
import os
import select
import struct

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.protocol import receive_tcp_message, unpack_str, send_tcp_message, pack_str

HOST = '0.0.0.0'
PORT = 5000
DISCOVERY_PORT = 5001 # Puerto del radar UDP
MAX_PLAYERS = 100
SERVER_NAME = "CC8-Server VAEB"

"""
    Avisa a todos los jugadores conectados quién está en la sala.
"""
def broadcast_lobby_state(clients):
    # El paquete contiene: u8 state, u8 count, y luego una lista dinámica
    # Se usa 0x01 para el estado WAITING
    payload = bytearray(struct.pack('>BB', 0x01, len(clients)))
    
    for client_info in clients.values():
        player_id = client_info["playerId"]
        name = client_info.get("name", "Unknown")

        # Por cada jugador: u16 playerId, str nombre
        payload.extend(struct.pack('>H', player_id))
        payload.extend(pack_str(name))
        
    # Envia paquete LOBBY_STATE (0x22) a todos
    for sock in clients.keys():
        send_tcp_message(sock, 0x22, bytes(payload))

def start_server():

    # 1. Configuración TCP (Partida)
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    # Modo no bloqueante: evita que el servidor se congele si no hay conexiones entrantes inmediatas
    server_socket.setblocking(False) 
    server_socket.bind((HOST, PORT))
    server_socket.listen(15) 

    # 2. Configuración UDP (Descubrimiento / Radar)
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    udp_socket.setblocking(False)
    udp_socket.bind((HOST, DISCOVERY_PORT))

    #Se vigila DOS sockets principales
    sockets_list = [server_socket, udp_socket]
    clients = {}
    player_counter = 1
    game_id = 1001 
    
    print(f"Servidor en estado WAITING...")
    print(f" - Partida TCP en puerto {PORT}")
    print(f" - Descubrimiento UDP en puerto {DISCOVERY_PORT}")
    
    while True:
        # select() vigila quién tiene mensajes listos para leer
        # La función select vigila todas las conexiones de red al mismo tiempo y devuelve tres listas:
        # Sockets que enviaron un mensaje (read_sockets).
        # Sockets listos para que se les envíe algo (aquí se ignora con un _).
        # Sockets que sufrieron un error fatal o crítico (exception_sockets).

        read_sockets, _, exception_sockets = select.select(sockets_list, [], sockets_list, 0.05)
        
        for notified_socket in read_sockets:
            # EVENTO A: Alguien buscó servidores por el radar UDP
            if notified_socket == udp_socket:
                try:
                    data, client_address = udp_socket.recvfrom(1024)
                    # Validamos el DISCOVER_REQUEST (0x01)
                    if len(data) >= 2 and data[0] == 0x01 and data[1] == 3:
                        # Armar DISCOVER_RESPONSE (0x02)
                        tipo_ver = struct.pack('>BB', 0x02, 3)
                        game_id_pack = struct.pack('>H', game_id)
                        name_pack = pack_str(SERVER_NAME)
                        rest_pack = struct.pack('>H B H H', PORT, 0x01, len(clients), MAX_PLAYERS)
                        
                        response = tipo_ver + game_id_pack + name_pack + rest_pack
                        udp_socket.sendto(response, client_address)
                        print(f"Radar UDP: Respondí a solicitud de {client_address[0]}")
                except Exception:
                    pass

            #EVENTO B: Nueva conexión TCP
            elif notified_socket == server_socket:
                client_socket, client_address = server_socket.accept()
                client_socket.setblocking(False)
                sockets_list.append(client_socket)
                
                # Se le asigna un ID interno
                clients[client_socket] = {"playerId": player_counter}
                player_counter += 1

            #EVENTO C: Mensajes TCP
            else:
                msg_type, payload = receive_tcp_message(notified_socket)
                
                # Desconexión
                if msg_type is None:
                    sockets_list.remove(notified_socket)
                    del clients[notified_socket]
                    broadcast_lobby_state(clients) # Avisa que alguien se fue
                    continue
                    
                # Mensaje JOIN (0x10)
                if msg_type == 0x10: 
                    player_name, _ = unpack_str(payload)
                    clients[notified_socket]["name"] = player_name
                    p_id = clients[notified_socket]["playerId"]
                    
                    # Responder con JOIN_ACCEPTED (0x20)
                    # Formato del protocolo: u16 playerId, u16 gameId
                    response_payload = struct.pack('>HH', p_id, game_id)
                    send_tcp_message(notified_socket, 0x20, response_payload)

                    # Avisa a todos que entró alguien nuevo
                    broadcast_lobby_state(clients)

        # Limpieza de errores
        # Garantiza que si un cliente se sale, el servidor simplemente barre los restos 
        # y sigue funcionando para los demás como si nada hubiera pasado.
        for notified_socket in exception_sockets:
            if notified_socket in sockets_list:
                sockets_list.remove(notified_socket)
            if notified_socket in clients:
                del clients[notified_socket]
                broadcast_lobby_state(clients)

if __name__ == "__main__":
    start_server()