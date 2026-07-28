import socket
import sys
import os
import time
import struct
import pygame
import select

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.protocol import  send_tcp_message, pack_str, receive_tcp_message, unpack_str

DISCOVERY_PORT = 5001
DIR_NONE, DIR_UP, DIR_DOWN, DIR_LEFT, DIR_RIGHT = 0, 1, 2, 3, 4

def discover_servers():
    print("Buscando servidores en la red local (Broadcast UDP)...")
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # Permite enviar mensajes Broadcast
    udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    
    # Espera un máximo de 2 segundos para recibir respuestas
    udp_socket.settimeout(2.0) 

    # Arma el paquete DISCOVER_REQUEST: tipo 0x01
    request_packet = struct.pack('>BB', 0x01, 3)
        
    try:
        udp_socket.sendto(request_packet, ('255.255.255.255', DISCOVERY_PORT))
    except Exception as e:
        print(f"Error al enviar broadcast: {e}")
        return []

    servers = []
    while True:
        try:
            data, addr = udp_socket.recvfrom(1024)
            # Valida DISCOVER_RESPONSE (0x02)
            if len(data) >= 2 and data[0] == 0x02 and data[1] == 3:

                # Desempaquetado manual guiado por el RFC
                offset = 2
                game_id = struct.unpack_from('>H', data, offset)[0]
                offset += 2

                # Extrae el string dinámico del nombre del servidor
                server_name, offset = unpack_str(data, offset)
                
                # Extrae el resto de datos: tcpPort(u16), state(u8), playerCount(u16), maxPlayers(u16)
                tcp_port, state, p_count, max_p = struct.unpack_from('>H B H H', data, offset)

                # Solo lista los servidores que están en estado WAITING (0x01)
                if state == 0x01:
                    servers.append({
                        'ip': addr[0],
                        'port': tcp_port,
                        'name': server_name,
                        'game_id': game_id,
                        'players': p_count,
                        'max': max_p
                    })

        except socket.timeout:
            break # Pasaron los 2 segundos, deja de escuchar

    udp_socket.close()
    return servers

def run_game_loop(client_socket, my_id, game_config):
    pygame.init()

    MAP_SIZE = game_config['map_size']
    SCALE = 800.0 / MAP_SIZE
    screen = pygame.display.set_mode((int(MAP_SIZE * SCALE), int(MAP_SIZE * SCALE)))
    pygame.display.set_caption(f"Jugador ID: P{my_id:02d}")
    clock = pygame.time.Clock()

    players_data = {} # Guarda la data cruda enviada por el servidor
    current_direction = DIR_NONE
    running = True

    while running:
        # 1. Eventos de Pygame (Cerrar ventana y Teclado)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                
        # Lectura de teclas para movimiento
        keys = pygame.key.get_pressed()
        new_dir = DIR_NONE
        if keys[pygame.K_w] or keys[pygame.K_UP]: new_dir = DIR_UP
        elif keys[pygame.K_s] or keys[pygame.K_DOWN]: new_dir = DIR_DOWN
        elif keys[pygame.K_a] or keys[pygame.K_LEFT]: new_dir = DIR_LEFT
        elif keys[pygame.K_d] or keys[pygame.K_RIGHT]: new_dir = DIR_RIGHT

        # Solo enviar al servidor si cambiamos de dirección (ahorra ancho de banda)
        if new_dir != current_direction:
            current_direction = new_dir
            send_tcp_message(client_socket, 0x11, struct.pack('>B', current_direction))

        # 2. Leer estado del Servidor sin bloquear el juego
        readable, _, _ = select.select([client_socket], [], [], 0)
        if readable:
            msg_type, payload = receive_tcp_message(client_socket)
            if msg_type is None: 
                break # No hay más mensajes en la cola por ahora

            if msg_type == 0x25: # GAME_STATE
                offset = 0
                # Desempaquetar cabecera de la bandera y cantidad de jugadores (>BHiiB = 12 bytes)
                flag_status, flag_carrier, flag_x, flag_y, p_count = struct.unpack_from('>BHiiB', payload, offset)
                offset += 12 # CORREGIDO: antes era 11
                
                players_data.clear()
                for _ in range(p_count):
                    # Desempaquetar cada jugador (>HiiBb = 12 bytes)
                    p_id, p_x, p_y, p_dir, p_flag = struct.unpack_from('>HiiBb', payload, offset)
                    offset += 12 # CORREGIDO: antes era 10
                    players_data[p_id] = {'x': p_x / 100.0, 'y': p_y / 100.0}

        # 3. Dibujar Frame Gráfico
        screen.fill((30, 30, 30)) # Fondo oscuro
        
        # Dibujar Círculo Seguro (Escalado)
        center = (int((MAP_SIZE/2) * SCALE), int((MAP_SIZE/2) * SCALE))
        radius = int(game_config['circle_radius'] * SCALE)
        pygame.draw.circle(screen, (50, 150, 50), center, radius, 3)

        # Dibujar Jugadores
        p_rad = int(game_config['player_radius'] * SCALE)
        for p_id, p_info in players_data.items():
            color = (50, 50, 250) if p_id == my_id else (200, 50, 50)
            p_pos = (int(p_info['x'] * SCALE), int(p_info['y'] * SCALE))
            pygame.draw.circle(screen, color, p_pos, p_rad)

        pygame.display.flip()
        clock.tick(60) # El cliente corre a 60 FPS suavizado, aunque reciba 20 Ticks/s

    pygame.quit()
    sys.exit()

def start_client():
    available_servers = discover_servers()
    if not available_servers:
        print("No se encontraron servidores. ")
        return
        
    print("\n--- SERVIDORES ENCONTRADOS ---")
    for i, srv in enumerate(available_servers):
        print(f"[{i}] {srv['name']} ({srv['players']}/{srv['max']} jugadores) - IP: {srv['ip']}")
        
    target_server = available_servers[0] # Auto-seleccionar para la prueba
    print(f"\nConectando automáticamente al servidor: {target_server['name']}...")
    """seleccion = input("\nElige el número del servidor para conectarte: ")
    try:
        index = int(seleccion)
        target_server = available_servers[index]
    except (ValueError, IndexError):
        print("Selección inválida.")
        return"""
    
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.connect((target_server['ip'], target_server['port']))
    client_socket.setblocking(False)

    join_payload = pack_str("Jugador")
    send_tcp_message(client_socket, 0x10, join_payload)
    my_id = None
    game_config = {}

    print("Esperando arranque...")
    
    try:
        while True:
            readable, _, _ = select.select([client_socket], [], [], 0.05)
            if readable: 
                msg_type, payload = receive_tcp_message(client_socket)
                if msg_type is None: 
                    print("Desconectado del servidor.")
                    continue
                
                elif msg_type == 0x22: # LOBBY_STATE
                    print(" -> Actualización de sala recibida.")

                elif msg_type == 0x20: 
                    my_id = struct.unpack('>HH', payload)[0]    

                elif msg_type == 0x23: # GAME_COUNTDOWN
                    seconds_left = struct.unpack('>B', payload)[0]
                    if seconds_left > 0:
                        print(f">>> La partida inicia en {seconds_left}...")
                    else:
                        print(">>> ¡Preparando entorno gráfico!")

                elif msg_type == 0x24: # GAME_STARTED
                    #print("\n[!] ¡Paquete GAME_STARTED recibido! Desempaquetando variables...")
                    offset = 0
                    
                    # Lee las variables base (i32 x5, u16 x1)
                    m_size, c_rad, p_rad, p_speed, int_rad, tick = struct.unpack_from('>iiiiiH', payload, offset)
                    offset += 22
                    
                    game_config = {
                        'map_size': m_size / 100.0,
                        'circle_radius': c_rad / 100.0,
                        'player_radius': p_rad / 100.0
                    }

                    print("\n¡Arrancando interfaz gráfica!")
                    run_game_loop(client_socket, my_id, game_config, )
                    break

    except KeyboardInterrupt:
        print("\nSaliendo...")
        client_socket.close()

if __name__ == "__main__":
    start_client()