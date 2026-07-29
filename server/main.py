import socket
import sys
import os
import select
import struct
import msvcrt  # Para detectar teclas sin bloquear (Windows)
import math    # Para senos y cosenos
import random  # Para ángulos aleatorios
import time
import pygame  # NUEVO: para la ventana de espectador que visualiza la partida sin participar en ella

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.protocol import receive_tcp_message, unpack_str, send_tcp_message, pack_str

HOST, PORT = '0.0.0.0', 5000
DISCOVERY_PORT = 5001 # Puerto del radar UDP
MAX_PLAYERS = 100
SERVER_NAME = "CC8-Server VAEB2"

# Estados del Servidor
STATE_WAITING = 0x01
STATE_STARTING = 0x02
STATE_RUNNING = 0x03

DIR_NONE, DIR_UP, DIR_DOWN, DIR_LEFT, DIR_RIGHT = 0, 1, 2, 3, 4

# Estados posibles de la bandera
FLAG_AVAILABLE, FLAG_CARRIED, FLAG_OUTSIDE = 0x01, 0x02, 0x03

# Constantes del juego
MAP_SIZE = 2000
CIRCLE_RADIUS = 500
PLAYER_RADIUS = 15
SPAWN_MARGIN = 80
PLAYER_SPEED = 220
INTERACTION_RADIUS = 60
TICK_INTERVAL_MS = 50

# NUEVO: Configuración de la ventana de espectador (solo visualización, el servidor no participa del juego)
SPECTATOR_WINDOW_SIZE = 650
SPECTATOR_FPS = 30
SPECTATOR_COLORS = [
    (230, 70, 70), (60, 150, 230), (90, 200, 120), (230, 180, 60),
    (180, 90, 220), (240, 130, 170), (80, 210, 210), (200, 200, 90),
]

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

# ==========================================
# NUEVO: helpers de dibujo para la ventana de espectador del servidor
# (el servidor solo observa, nunca envía inputs ni participa en el juego)
# ==========================================

def get_player_color(player_id):
    return SPECTATOR_COLORS[player_id % len(SPECTATOR_COLORS)]

def draw_spectator_flag(screen, pos, tick_ms, carried):
    # Si nadie la lleva, hace un pequeño bamboleo; si la llevan, va fija sobre el portador
    bob = 0 if carried else int(4 * math.sin(tick_ms / 300.0))
    base = (pos[0], pos[1] + bob)

    pygame.draw.ellipse(screen, (0, 0, 0), (base[0] - 7, base[1] + 6, 14, 5))
    pygame.draw.line(screen, (210, 210, 210), (base[0], base[1] + 8), (base[0], base[1] - 16), 3)

    color_tela = (255, 235, 120) if carried else (255, 215, 0)
    tela = [(base[0], base[1] - 16), (base[0] + 16, base[1] - 10), (base[0], base[1] - 4)]
    pygame.draw.polygon(screen, color_tela, tela)
    pygame.draw.polygon(screen, (150, 110, 0), tela, 1)

def draw_spectator_player(screen, font_name, pos, radius, color, direction, name, has_flag, tick_ms):
    pygame.draw.circle(screen, (0, 0, 0), (pos[0] + 2, pos[1] + 3), radius)

    # Aro dorado pulsante para quien lleva la bandera
    if has_flag:
        pulso = radius + 5 + int(2 * math.sin(tick_ms / 150.0))
        pygame.draw.circle(screen, (255, 215, 0), pos, pulso, 3)

    pygame.draw.circle(screen, color, pos, radius)
    pygame.draw.circle(screen, (15, 15, 15), pos, radius, 2)

    brillo_pos = (pos[0] - radius // 3, pos[1] - radius // 3)
    pygame.draw.circle(screen, (255, 255, 255), brillo_pos, max(2, radius // 4))

    vectores = {DIR_UP: (0, -1), DIR_DOWN: (0, 1), DIR_LEFT: (-1, 0), DIR_RIGHT: (1, 0)}
    if direction in vectores:
        dx, dy = vectores[direction]
        punta = (pos[0] + dx * (radius + 10), pos[1] + dy * (radius + 10))
        pygame.draw.line(screen, (255, 255, 255), pos, punta, 3)

    name_surface = font_name.render(name, True, (255, 255, 255))
    name_rect = name_surface.get_rect(center=(pos[0], pos[1] - radius - 14))
    fondo = pygame.Surface((name_rect.width + 6, name_rect.height + 2), pygame.SRCALPHA)
    fondo.fill((0, 0, 0, 140))
    screen.blit(fondo, (name_rect.x - 3, name_rect.y - 1))
    screen.blit(name_surface, name_rect)

def draw_lobby_view(screen, fonts, clients, countdown_seconds):
    # Muestra la sala de espera (WAITING) o la cuenta regresiva (STARTING), vista desde el servidor
    screen.fill((22, 24, 30))

    titulo = fonts['lobby_title'].render("Sala de espera (vista del servidor)", True, (255, 255, 255))
    screen.blit(titulo, titulo.get_rect(center=(screen.get_width() // 2, 34)))

    y = 90
    if clients:
        for client_info in clients.values():
            p_id = client_info.get("playerId", "?")
            p_name = client_info.get("name", "(conectando...)")
            etiqueta = f"P{p_id:02d} - {p_name}"
            fila = fonts['lobby_player'].render(etiqueta, True, (220, 220, 220))
            screen.blit(fila, (40, y))
            y += 28
    else:
        espera = fonts['lobby_player'].render("Esperando jugadores...", True, (150, 150, 150))
        screen.blit(espera, (40, y))

    if countdown_seconds is not None:
        texto = str(countdown_seconds) if countdown_seconds >= 0 else "¡YA!"
        color = (255, 215, 0) if countdown_seconds >= 0 else (90, 210, 120)
        cd_surf = fonts['banner'].render(texto, True, color)
        screen.blit(cd_surf, cd_surf.get_rect(center=(screen.get_width() // 2, screen.get_height() - 80)))

def draw_running_view(screen, fonts, clients, flag_status, flag_x, flag_y, tick_ms, scale, map_size, circle_radius):
    # Dibuja la partida en curso (STATE_RUNNING), vista desde el servidor, sin controles de jugador
    screen.fill((22, 24, 30))

    center = (int((map_size / 2) * scale), int((map_size / 2) * scale))
    radius = int(circle_radius * scale)
    zona_segura = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
    pygame.draw.circle(zona_segura, (60, 160, 90, 60), (radius, radius), radius)
    screen.blit(zona_segura, (center[0] - radius, center[1] - radius))
    pygame.draw.circle(screen, (90, 210, 120), center, radius, 3)

    # AQUÍ YA ESTÁ LA BANDERA CORREGIDA
    flag_pos = (int(flag_x * scale + center[0]), int(flag_y * scale + center[1]))
    draw_spectator_flag(screen, flag_pos, tick_ms, carried=(flag_status == FLAG_CARRIED))

    # CICLO FOR INTACTO CON LA VARIABLE client_info
    for client_info in clients.values():
        if 'x' not in client_info:
            continue  # NUEVO: aún no se calculó su posición inicial (recién conectado)
        p_id = client_info["playerId"]
        
        # AQUÍ YA ESTÁ EL JUGADOR CORREGIDO, DENTRO DEL CICLO
        p_pos = (int(client_info['x'] * scale + center[0]), int(client_info['y'] * scale + center[1]))
        
        draw_spectator_player(
            screen, fonts['name'], p_pos, int(PLAYER_RADIUS * scale), get_player_color(p_id),
            client_info.get('direction', DIR_NONE), client_info.get('name', f"P{p_id}"),
            has_flag=client_info.get('hasFlag', False), tick_ms=tick_ms
        )

    barra = pygame.Surface((screen.get_width(), 26), pygame.SRCALPHA)
    barra.fill((0, 0, 0, 150))
    screen.blit(barra, (0, 0))
    texto = fonts['hud'].render(f"Partida en curso — {len(clients)} jugadores", True, (230, 230, 230))
    screen.blit(texto, (8, 5))

    barra = pygame.Surface((screen.get_width(), 26), pygame.SRCALPHA)
    barra.fill((0, 0, 0, 150))
    screen.blit(barra, (0, 0))
    texto = fonts['hud'].render(f"Partida en curso — {len(clients)} jugadores", True, (230, 230, 230))
    screen.blit(texto, (8, 5))

def draw_winner_banner(screen, fonts, texto):
    text_surf = fonts['banner'].render(texto, True, (255, 215, 0))
    text_rect = text_surf.get_rect(center=(screen.get_width() // 2, screen.get_height() // 2))
    pygame.draw.rect(screen, (0, 0, 0), text_rect.inflate(20, 20))
    pygame.draw.rect(screen, (255, 215, 0), text_rect.inflate(20, 20), 2)
    screen.blit(text_surf, text_rect)

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
    current_tick = 1
    last_time = 0
    last_tick_time = 0

    # Variables de control de la bandera
    flag_status = FLAG_AVAILABLE
    flag_carrier = 0
    flag_x = 0  # Arranca en el centro exacto del mapa
    flag_y = 0
    
    print(f"Servidor en estado WAITING...")
    print(f" - Partida TCP en puerto {PORT}")
    print("[INFO] Presiona 'Enter' en esta consola para iniciar la partida.")

    # NUEVO: Ventana de espectador — permite ver la partida desde el servidor sin participar en ella
    pygame.init()
    spectator_scale = SPECTATOR_WINDOW_SIZE / MAP_SIZE
    spectator_screen = pygame.display.set_mode((int(MAP_SIZE * spectator_scale), int(MAP_SIZE * spectator_scale)))
    pygame.display.set_caption(f"{SERVER_NAME} - Vista del servidor (Espectador)")
    spectator_fonts = {
        'name': pygame.font.SysFont(None, 20),
        'hud': pygame.font.SysFont(None, 22),
        'banner': pygame.font.SysFont(None, 48),
        'lobby_title': pygame.font.SysFont(None, 34),
        'lobby_player': pygame.font.SysFont(None, 24),
    }
    spectator_active = True
    last_spectator_draw = 0.0
    winner_banner_text = ""
    winner_banner_until = 0.0
    print("[INFO] Ventana de espectador abierta (solo visualización, no participa del juego).")

    while True:
        current_time = time.time()
        # EVENTO A: Gatillo del anfitrión
        if server_state == STATE_WAITING and msvcrt.kbhit():
            tecla = msvcrt.getch()
            if tecla in (b'\r', b'\n'):
                print("\n[!] ¡Iniciando secuencia de arranque! Cerrando puertas...")
                server_state = STATE_STARTING # Cambiamos de estado
                last_time = time.time()

        # EVENTO B: Motor de cuenta regresiva
        if server_state == STATE_STARTING:
            if current_time - last_time >= 1.0: # Pasó 1 segundo exacto
                last_time = current_time
                
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
                    last_tick_time = current_time
                    dist = CIRCLE_RADIUS + SPAWN_MARGIN

                    # 1. Calcular posiciones iniciales polares (fuera del círculo)
                    for client in clients.values():
                        angulo = random.uniform(0, 2 * math.pi)
                        client['x'] = dist * math.cos(angulo) # <- Quítale el (MAP_SIZE / 2)
                        client['y'] = dist * math.sin(angulo) # <- Quítale el (MAP_SIZE / 2)
                        client['direction'] = DIR_NONE
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
                    
                    # reinicio de la bandera al centro del mapa para la nueva ronda
                    flag_status = FLAG_AVAILABLE
                    flag_carrier = 0
                    flag_x = 0.0 # <- Vuelve a 0.0
                    flag_y = 0.0 # <- Vuelve a 0.0

                    # 3. Estado inicial de la bandera en (0,0)
                    # u8 estado(0x01=AVAILABLE), u16 dueño, i32 X, i32 Y
                    payload.extend(struct.pack('>BHii', flag_status, flag_carrier,
                        int(round(flag_x * 100)), int(round(flag_y * 100))
                    ))
                    
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
                    print("\n[!] ¡Partida en curso! Procesando inputs...")

        # EVENTO C: Motor Principal del Juego (50ms) ---
        if server_state == STATE_RUNNING:
            if current_time - last_tick_time >= (TICK_INTERVAL_MS / 1000.0):
                last_tick_time = current_time
                
                # 1. Calcular físicas de movimiento
                delta_t = TICK_INTERVAL_MS / 1000.0
                distancia = PLAYER_SPEED * delta_t # Píxeles a mover en este frame
                
                for client in clients.values():
                    if client['direction'] == DIR_UP: client['y'] -= distancia
                    elif client['direction'] == DIR_DOWN: client['y'] += distancia
                    elif client['direction'] == DIR_LEFT: client['x'] -= distancia
                    elif client['direction'] == DIR_RIGHT: client['x'] += distancia
                    
                    # Evitar que se salgan del mapa (0 a 2000)
                    limit = MAP_SIZE / 2.0
                    client['x'] = max(-limit, min(limit, client['x']))
                    client['y'] = max(-limit, min(limit, client['y']))

                # Si alguien lleva la bandera, ésta viaja pegada a su portador
                juego_termino = False
                if flag_status == FLAG_CARRIED:
                    for client in clients.values():
                        if client.get('hasFlag', False):
                            flag_x = client['x']
                            flag_y = client['y']

                            # El centro real del mapa es (MAP_SIZE/2, MAP_SIZE/2)
                            distancia_centro = math.hypot(flag_x, flag_y)
                            if distancia_centro > CIRCLE_RADIUS:
                                p_id = client['playerId']
                                nombre_ganador = client.get('name', f"Jugador_{p_id}")
                                print(f"\n[!] ¡FIN DEL JUEGO! El jugador P{p_id} ({nombre_ganador}) sacó la bandera del círculo y GANÓ.")

                                flag_status = FLAG_OUTSIDE
                                juego_termino = True
                                # NUEVO: guarda el cartel de victoria para mostrarlo unos segundos en la ventana de espectador
                                winner_banner_text = f"¡{nombre_ganador.upper()} GANÓ LA PARTIDA!"
                                winner_banner_until = current_time + 5.0
                            break

                # 2. Empaquetar y enviar GAME_STATE (0x25)
                # payload: u8 flag_status, u16 flag_carrier, i32 flag_x, i32 flag_y, u8 count

                payload = bytearray()
                payload.extend(struct.pack('>IBHiiB', current_tick, flag_status, flag_carrier,
                    int(round(flag_x * 100)), int(round(flag_y * 100)), len(clients)
                ))
                current_tick += 1

                for client in clients.values():
                    # u16 id, i32 x, i32 y, u8 dir, i8 hasFlag
                    payload.extend(struct.pack('>HiiBb',
                        client['playerId'], int(round(client['x'] * 100)), int(round(client['y'] * 100)),
                        client['direction'], client['hasFlag']
                    ))
                    
                for sock in clients.keys():
                    send_tcp_message(sock, 0x25, bytes(payload))

                # Si la ronda terminó, avisa con GAME_OVER (0x29) y vuelve a WAITING
                if juego_termino:
                    # Formato: u16 versión, u16 winnerPlayerId, str winnerName, u8 indicador final
                    game_over_payload = bytearray()
                    game_over_payload.extend(struct.pack('>H', 0x03))
                    game_over_payload.extend(struct.pack('>H', p_id))
                    game_over_payload.extend(pack_str(nombre_ganador))
                    game_over_payload.extend(struct.pack('>B', 0x04))

                    for sock in clients.keys():
                        send_tcp_message(sock, 0x29, bytes(game_over_payload))

                    # Reinicia la sala para permitir una nueva ronda
                    server_state = STATE_WAITING
                    countdown_seconds = 5
                    broadcast_lobby_state(clients)

        # EVENTO D: Ventana de espectador del servidor (solo visualización, no participa del juego)
        if spectator_active:
            for spec_event in pygame.event.get():
                if spec_event.type == pygame.QUIT:
                    print("[INFO] Ventana de espectador cerrada. El servidor sigue ejecutándose (revisa esta consola).")
                    pygame.quit()
                    spectator_active = False

        if spectator_active and (current_time - last_spectator_draw) >= (1.0 / SPECTATOR_FPS):
            last_spectator_draw = current_time
            tick_ms = pygame.time.get_ticks()

            if server_state in (STATE_WAITING, STATE_STARTING):
                cd = (countdown_seconds + 1) if (server_state == STATE_STARTING and countdown_seconds < 5) else None
                draw_lobby_view(spectator_screen, spectator_fonts, clients, cd)
            else:  # STATE_RUNNING
                draw_running_view(
                    spectator_screen, spectator_fonts, clients, flag_status,
                    flag_x, flag_y, tick_ms, spectator_scale, MAP_SIZE, CIRCLE_RADIUS
                )
                if current_time < winner_banner_until:
                    draw_winner_banner(spectator_screen, spectator_fonts, winner_banner_text)

            pygame.display.flip()

        # EVENTOS DE RED:
        # select() vigila quién tiene mensajes listos para leer
        # La función select vigila todas las conexiones de red al mismo tiempo y devuelve tres listas:
        # Sockets que enviaron un mensaje (read_sockets).
        # Sockets listos para que se les envíe algo (aquí se ignora con un _).
        # Sockets que sufrieron un error fatal o crítico (exception_sockets).

        read_sockets, _, exception_sockets = select.select(sockets_list, [], sockets_list, 0.005)
        
        for notified_socket in read_sockets:
            # EVENTO A: Alguien buscó servidores por el radar UDP
            if notified_socket == udp_socket:
                try:
                    data, client_address = udp_socket.recvfrom(1024)
                    # Validamos el DISCOVER_REQUEST (0x01)
                    if data[0] == 0x01 and server_state == STATE_WAITING:
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

                # Si la partida ya arrancó, no se aceptan jugadores nuevos
                if server_state == STATE_WAITING:
                    client_socket.setblocking(False)
                    sockets_list.append(client_socket)

                    # Se le asigna un ID interno
                    clients[client_socket] = {"playerId": player_counter}
                    player_counter += 1
                else:
                    client_socket.close()

            #EVENTO C: Mensajes TCP
            else:
                msg_type, payload = receive_tcp_message(notified_socket)
                
                # Desconexión
                if msg_type is None:
                    # Si el jugador que se cayó llevaba la bandera, ésta cae al suelo
                    client_info = clients.get(notified_socket, {})
                    if client_info.get('hasFlag', False):
                        flag_status = FLAG_AVAILABLE
                        flag_carrier = 0
                        flag_x = client_info['x']
                        flag_y = client_info['y']

                    sockets_list.remove(notified_socket)
                    del clients[notified_socket]

                    # Avisa al resto de la sala si estábamos en WAITING
                    if server_state == STATE_WAITING:
                        broadcast_lobby_state(clients)

                # Mensaje JOIN (0x10)
                elif msg_type == 0x10: 
                    player_name, _ = unpack_str(payload)
                    clients[notified_socket]["name"] = player_name
                    p_id = clients[notified_socket]["playerId"]
                    
                    # Responde con JOIN_ACCEPTED (0x20)
                    # Formato del protocolo: u16 playerId, u16 gameId
                    response_payload = struct.pack('>HH', p_id, game_id)
                    send_tcp_message(notified_socket, 0x20, response_payload)

                    # Avisa a todos que entró alguien nuevo
                    broadcast_lobby_state(clients)

                elif msg_type == 0x11: # INPUT RECIBIDO 
                    p_id, direccion = struct.unpack('>HB', payload)
                    # Actualizamos la dirección activa del jugador en memoria
                    clients[notified_socket]['direction'] = direccion

                # Mensaje INTERACT (0x12) -> capturar o robar la bandera
                elif msg_type == 0x12:
                    client = clients[notified_socket]
                    p_id = client["playerId"]

                    # Caso A: la bandera está libre en el suelo
                    if flag_status == FLAG_AVAILABLE:
                        distancia = math.hypot(client['x'] - flag_x, client['y'] - flag_y)
                        if distancia <= INTERACTION_RADIUS:
                            print(f"[!] Jugador P{p_id} capturó la bandera.")
                            flag_status = FLAG_CARRIED
                            flag_carrier = p_id
                            client['hasFlag'] = True

                    # Caso B: la bandera la lleva otro jugador -> se la puede robar
                    elif flag_status == FLAG_CARRIED and flag_carrier != p_id:
                        distancia = math.hypot(client['x'] - flag_x, client['y'] - flag_y)
                        if distancia <= INTERACTION_RADIUS:
                            print(f"[!] Jugador P{p_id} le robó la bandera a P{flag_carrier}.")
                            for otro in clients.values():
                                if otro['playerId'] == flag_carrier:
                                    otro['hasFlag'] = False
                                    break
                            flag_carrier = p_id
                            client['hasFlag'] = True

                # Mensaje LEAVE (0x13) -> desconexión voluntaria
                elif msg_type == 0x13:
                    client_info = clients.get(notified_socket, {})
                    p_id = client_info.get("playerId", "?")
                    print(f"Cliente P{p_id} abandonó la sala (LEAVE).")

                    # Si llevaba la bandera, cae al suelo en su última posición
                    if client_info.get('hasFlag', False):
                        flag_status = FLAG_AVAILABLE
                        flag_carrier = 0
                        flag_x = client_info['x']
                        flag_y = client_info['y']

                    sockets_list.remove(notified_socket)
                    del clients[notified_socket]
                    notified_socket.close()

                    if server_state == STATE_WAITING:
                        broadcast_lobby_state(clients)

        # Limpieza de errores
        # Garantiza que si un cliente se sale, el servidor simplemente barre los restos 
        # y sigue funcionando para los demás como si nada hubiera pasado.
        for notified_socket in exception_sockets:
            if notified_socket in sockets_list:
                sockets_list.remove(notified_socket)
            if notified_socket in clients:
                # Si el jugador que falló llevaba la bandera, ésta cae al suelo
                client_info = clients[notified_socket]
                if client_info.get('hasFlag', False):
                    flag_status = FLAG_AVAILABLE
                    flag_carrier = 0
                    flag_x = client_info['x']
                    flag_y = client_info['y']

                del clients[notified_socket]
                broadcast_lobby_state(clients)

if __name__ == "__main__":
    start_server()