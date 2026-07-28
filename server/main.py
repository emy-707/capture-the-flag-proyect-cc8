import socket
import sys
import os
import select
import struct
import msvcrt  # Para detectar teclas sin bloquear (Windows)
import math    # Para senos y cosenos
import random  # Para ángulos aleatorios
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.protocol import receive_tcp_message, unpack_str, send_tcp_message, pack_str

HOST = '0.0.0.0'
PORT = 5000
DISCOVERY_PORT = 5001 # Puerto del radar UDP
MAX_PLAYERS = 100
SERVER_NAME = "CC8-Server VAEB"

# Estados del Servidor
STATE_WAITING = 0x01
STATE_STARTING = 0x02
STATE_RUNNING = 0x03

# Constantes del juego
MAP_SIZE = 2000
CIRCLE_RADIUS = 500
PLAYER_RADIUS = 15
SPAWN_MARGIN = 80
PLAYER_SPEED = 220
INTERACTION_RADIUS = 60
TICK_INTERVAL_MS = 50

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

    # Variables de control de la partida
    server_state = STATE_WAITING
    countdown_seconds = 5
    last_countdown_time = 0
    
    print(f"Servidor en estado WAITING...")
    print(f" - Partida TCP en puerto {PORT}")
    print("[INFO] Presiona 'Enter' en esta consola para iniciar la partida.")
    
    while True:

        # EVENTO A: Gatillo del anfitrión
        if server_state == STATE_WAITING and msvcrt.kbhit():
            tecla = msvcrt.getch()
            if tecla in (b'\r', b'\n'):
                print("\n[!] ¡Iniciando secuencia de arranque! Cerrando puertas...")
                server_state = STATE_STARTING # Cambiamos de estado
                last_countdown_time = time.time()

        # EVENTO B: Motor de cuenta regresiva
        if server_state == STATE_STARTING:
            current_time = time.time()
            if current_time - last_countdown_time >= 1.0: # Pasó 1 segundo exacto
                last_countdown_time = current_time
                
                # Armamos el paquete GAME_COUNTDOWN (0x23)
                # Formato: u8 secondsRemaining
                countdown_payload = struct.pack('>B', countdown_seconds)
                
                # Hacemos broadcast a todos los jugadores en la sala
                for sock in clients.keys():
                    send_tcp_message(sock, 0x23, countdown_payload)
                
                print(f"Cuenta regresiva: {countdown_seconds}...")
                countdown_seconds -= 1

                if countdown_seconds < 0:
                    server_state = STATE_RUNNING
                    
                    # 1. Calcular posiciones iniciales polares (fuera del círculo)
                    dist = CIRCLE_RADIUS + SPAWN_MARGIN
                    for client in clients.values():
                        angulo = random.uniform(0, 2 * math.pi)
                        client['x'] = dist * math.cos(angulo)
                        client['y'] = dist * math.sin(angulo)
                        client['direction'] = 0x00 # NONE
                        client['hasFlag'] = False
                        
                    # 2. Empaquetar la cabecera geométrica del juego (GAME_STARTED - 0x24)
                    # i32 (5 variables) y u16 (1 variable)
                    payload = bytearray()
                    payload.extend(struct.pack('>iiiiiH',
                        MAP_SIZE * 100, 
                        CIRCLE_RADIUS * 100, 
                        PLAYER_RADIUS * 100,
                        PLAYER_SPEED * 100, 
                        INTERACTION_RADIUS * 100, 
                        TICK_INTERVAL_MS
                    ))
                    
                    # 3. Estado inicial de la bandera en (0,0)
                    # u8 estado(0x01=AVAILABLE), u16 dueño, i32 X, i32 Y
                    payload.extend(struct.pack('>BHii', 0x01, 0, 0, 0))
                    
                    # 4. Lista de Jugadores
                    payload.extend(struct.pack('>B', len(clients))) # u8 count
                    for client in clients.values():
                        # Identificador y string
                        payload.extend(struct.pack('>H', client['playerId']))
                        
                        nombre_seguro = client.get('name', f"Jugador_{client['playerId']}")
                        payload.extend(pack_str(nombre_seguro))
                        
                        # Las coordenadas se envían en centésimas (x100) como i32
                        payload.extend(struct.pack('>iiBb', 
                            int(round(client['x'] * 100)), 
                            int(round(client['y'] * 100)), 
                            client['direction'], 
                            client['hasFlag']
                        ))
                        
                    # 5. Broadcast final: ¡Empieza la partida!
                    for sock in clients.keys():
                        send_tcp_message(sock, 0x24, bytes(payload))
                    print("\n[!] Partida iniciada. (El servidor se detendrá por ahora en esta prueba).")
                    return # Termina la prueba temporalmente

        # EVENTOS DE RED:
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