import socket
import sys
import os
import time
import struct
import pygame
import select
import math  # NUEVO: para animaciones (pulso del aro, bamboleo de la bandera)

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.protocol import  send_tcp_message, pack_str, receive_tcp_message, unpack_str

DISCOVERY_PORT = 5001
DIR_NONE, DIR_UP, DIR_DOWN, DIR_LEFT, DIR_RIGHT = 0, 1, 2, 3, 4

# NUEVO: tamaño máximo de la ventana de juego (antes 800, quedaba muy alta en pantallas chicas)
GAME_WINDOW_SIZE = 650

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

# ==========================================
# NUEVO: helpers de dibujo (para no llenar de puntitos la pantalla)
# ==========================================

# Vector (dx, dy) por cada dirección, usado para la flechita que indica hacia dónde mira el jugador
DIR_VECTORES = {
    DIR_UP: (0, -1),
    DIR_DOWN: (0, 1),
    DIR_LEFT: (-1, 0),
    DIR_RIGHT: (1, 0),
}

def draw_player(screen, font_name, pos, radius, color, direction, name, is_me, has_flag, tick_ms):
    # Sombra proyectada, para dar sensación de volumen sobre el fondo
    pygame.draw.circle(screen, (0, 0, 0), (pos[0] + 2, pos[1] + 3), radius)

    # Aro dorado pulsante para quien lleva la bandera
    if has_flag:
        pulso = radius + 5 + int(2 * math.sin(tick_ms / 150.0))
        pygame.draw.circle(screen, (255, 215, 0), pos, pulso, 3)

    # Cuerpo del jugador: relleno + borde (blanco si soy yo, para distinguirme del resto)
    pygame.draw.circle(screen, color, pos, radius)
    borde = (255, 255, 255) if is_me else (15, 15, 15)
    pygame.draw.circle(screen, borde, pos, radius, 3 if is_me else 2)

    # Brillo tipo "gloss" arriba a la izquierda, para que no se vea plano
    brillo_pos = (pos[0] - radius // 3, pos[1] - radius // 3)
    pygame.draw.circle(screen, (255, 255, 255), brillo_pos, max(2, radius // 4))

    # Flechita indicando hacia dónde se está moviendo
    if direction in DIR_VECTORES:
        dx, dy = DIR_VECTORES[direction]
        punta = (pos[0] + dx * (radius + 10), pos[1] + dy * (radius + 10))
        pygame.draw.line(screen, (255, 255, 255), pos, punta, 3)

    # Etiqueta con el nombre, sobre un fondo semitransparente para que se lea sobre cualquier color
    etiqueta = f"TÚ ({name})" if is_me else name
    name_surface = font_name.render(etiqueta, True, (255, 255, 255))
    name_rect = name_surface.get_rect(center=(pos[0], pos[1] - radius - 14))
    fondo = pygame.Surface((name_rect.width + 6, name_rect.height + 2), pygame.SRCALPHA)
    fondo.fill((0, 0, 0, 140))
    screen.blit(fondo, (name_rect.x - 3, name_rect.y - 1))
    screen.blit(name_surface, name_rect)

def draw_flag(screen, pos, tick_ms, carried):
    # Si nadie la lleva, hace un pequeño bamboleo; si la llevan, va fija sobre el portador
    bob = 0 if carried else int(4 * math.sin(tick_ms / 300.0))
    base = (pos[0], pos[1] + bob)

    # Sombra en el piso
    pygame.draw.ellipse(screen, (0, 0, 0), (base[0] - 7, base[1] + 6, 14, 5))

    # Asta
    pygame.draw.line(screen, (210, 210, 210), (base[0], base[1] + 8), (base[0], base[1] - 16), 3)

    # Tela triangular ondeando
    color_tela = (255, 235, 120) if carried else (255, 215, 0)
    tela = [(base[0], base[1] - 16), (base[0] + 16, base[1] - 10), (base[0], base[1] - 4)]
    pygame.draw.polygon(screen, color_tela, tela)
    pygame.draw.polygon(screen, (150, 110, 0), tela, 1)

def draw_hud(screen, width, hud_font, help_font, my_id, my_name, jugadores_vivos, fps):
    # Barra superior semitransparente con info de la partida
    barra = pygame.Surface((width, 30), pygame.SRCALPHA)
    barra.fill((0, 0, 0, 150))
    screen.blit(barra, (0, 0))
    texto = hud_font.render(
        f"P{my_id:02d} - {my_name}    |    {jugadores_vivos} jugadores    |    {int(fps)} FPS",
        True, (230, 230, 230)
    )
    screen.blit(texto, (8, 6))

    # Ayuda de controles, abajo del todo
    ayuda = help_font.render("WASD / Flechas: moverse — ESPACIO: capturar o robar la bandera", True, (190, 190, 190))
    ayuda_rect = ayuda.get_rect(center=(width // 2, screen.get_height() - 14))
    fondo = pygame.Surface((ayuda_rect.width + 12, ayuda_rect.height + 4), pygame.SRCALPHA)
    fondo.fill((0, 0, 0, 120))
    screen.blit(fondo, (ayuda_rect.x - 6, ayuda_rect.y - 2))
    screen.blit(ayuda, ayuda_rect)

def run_game_loop(client_socket, my_id, game_config):
    pygame.init()

    MAP_SIZE = game_config['map_size']
    SCALE = GAME_WINDOW_SIZE / MAP_SIZE
    screen = pygame.display.set_mode((int(MAP_SIZE * SCALE), int(MAP_SIZE * SCALE)))
    pygame.display.set_caption(f"Jugador ID: P{my_id:02d}")
    clock = pygame.time.Clock()

    # NUEVO: fuentes para el nombre de los jugadores y el cartel de victoria
    font_name = pygame.font.SysFont(None, 20)
    font_banner = pygame.font.SysFont(None, 48)
    # NUEVO: fuentes para la barra de HUD (creadas una sola vez, no en cada frame)
    hud_font = pygame.font.SysFont(None, 22)
    help_font = pygame.font.SysFont(None, 18)

    players_data = game_config.get('players', {}) # Guarda la data cruda enviada por el servidor
    # NUEVO: estado de la bandera, ya viene armado desde GAME_STARTED
    flag_data = game_config.get('flag', {'status': 0x01, 'carrierId': 0, 'x': MAP_SIZE / 2, 'y': MAP_SIZE / 2})
    current_direction = DIR_NONE
    running = True

    # NUEVO: control del cartel de fin de partida
    game_over = False
    winner_text = ""

    while running:
        # 1. Eventos de Pygame (Cerrar ventana y Teclado)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            # NUEVO: barra espaciadora -> INTERACT (0x12) para capturar/robar la bandera
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_SPACE:
                    send_tcp_message(client_socket, 0x12, struct.pack('>H', my_id))
                
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
            send_tcp_message(client_socket, 0x11, struct.pack('>HB', my_id, current_direction))

        # 2. Leer estado del Servidor sin bloquear el juego
        readable, _, _ = select.select([client_socket], [], [], 0)
        if readable:
            msg_type, payload = receive_tcp_message(client_socket)
            if msg_type is None: 
                break # No hay más mensajes en la cola por ahora

            if msg_type == 0x25: # GAME_STATE
                offset = 0
                # Desempaquetar cabecera de la bandera y cantidad de jugadores (>BHiiB = 12 bytes)
                tick, flag_status, flag_carrier, flag_x, flag_y, p_count = struct.unpack_from('>IBHiiB', payload, offset)
                offset += 16 # CORREGIDO: antes era 11

                # NUEVO: actualizamos el estado de la bandera para dibujarla
                flag_data['status'] = flag_status
                flag_data['carrierId'] = flag_carrier
                flag_data['x'] = flag_x / 100.0
                flag_data['y'] = flag_y / 100.0

                # NUEVO: reconstruimos la lista conservando el nombre que ya conocíamos de cada jugador
                nuevos_players = {}
                # Usamos un bucle seguro basado en los bytes restantes del paquete para evitar desbordes
                while offset + 12 <= len(payload):
                    # Volvemos a leer SOLO los 10 bytes que envía el servidor (>Hii)
                    p_id, p_x, p_y, p_dir, p_flag = struct.unpack_from('>HiiBb', payload, offset)
                    offset += 12

                    # 1. Deducir si este jugador tiene la bandera según la cabecera
                    has_flag = bool(p_flag)
                    nombre_previo = players_data.get(p_id, {}).get('name', f"P{p_id}")

                    # 2. Deducir la dirección de movimiento comparando con el frame anterior
                    p_dir = DIR_NONE
                    jugador_previo = players_data.get(p_id)
                    if jugador_previo:
                        dx = (p_x / 100.0) - jugador_previo['x']
                        dy = (p_y / 100.0) - jugador_previo['y']
                        
                        # Determinar el eje de mayor movimiento
                        if abs(dx) > abs(dy):
                            p_dir = DIR_RIGHT if dx > 0 else DIR_LEFT
                        elif abs(dy) > abs(dx):
                            p_dir = DIR_DOWN if dy > 0 else DIR_UP
                        else:
                            p_dir = jugador_previo.get('direction', DIR_NONE) # Mantiene la vista si está quieto

                    nombre_previo = players_data.get(p_id, {}).get('name', f"P{p_id}")
                    nuevos_players[p_id] = {
                        'name': nombre_previo,
                        'x': p_x / 100.0, 'y': p_y / 100.0,
                        'direction': p_dir, 
                        'hasFlag': has_flag
                    }
                players_data = nuevos_players

            # NUEVO: GAME_OVER (0x29) -> mostramos el cartel de victoria
            elif msg_type == 0x29:
                winner_id = struct.unpack_from('>H', payload, 0)[0]
                
                # 2. Buscamos el nombre seguro en nuestro propio diccionario local
                winner_name = f"P{winner_id:02d}"
                if winner_id in players_data:
                    winner_name = players_data[winner_id].get('name', winner_name)

                print(f"\n[!] ¡PARTIDA FINALIZADA! El ganador es {winner_name}")
                game_over = True
                winner_text = f"¡{winner_name.upper()} GANÓ LA PARTIDA!"

        # 3. Dibujar Frame Gráfico
        screen.fill((22, 24, 30)) # Fondo oscuro

        tick_ms = pygame.time.get_ticks() # NUEVO: reloj interno para las animaciones

        # Dibujar Círculo Seguro (Escalado)
        center = (int((MAP_SIZE/2) * SCALE), int((MAP_SIZE/2) * SCALE))
        radius = int(game_config['circle_radius'] * SCALE)
        # NUEVO: relleno translúcido de la zona segura, en vez de solo el borde
        zona_segura = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
        pygame.draw.circle(zona_segura, (60, 160, 90, 60), (radius, radius), radius)
        screen.blit(zona_segura, (center[0] - radius, center[1] - radius))
        pygame.draw.circle(screen, (90, 210, 120), center, radius, 3)

        # NUEVO: Dibujar la Bandera con asta y tela animada (reemplaza el cuadrado plano)
        flag_pos = (int(flag_data['x'] * SCALE + center[0]), int(flag_data['y'] * SCALE + center[1]))
        draw_flag(screen, flag_pos, tick_ms, carried=(flag_data['status'] == 0x02))

        # Dibujar Jugadores (con relieve, flecha de dirección y aro si llevan la bandera)
        p_rad = int(game_config['player_radius'] * SCALE)
        for p_id, p_info in players_data.items():
            color = (60, 120, 255) if p_id == my_id else (230, 70, 70)
            p_pos = (int(p_info['x'] * SCALE + center[0]), int(p_info['y'] * SCALE + center[1]))
            draw_player(
                screen, font_name, p_pos, p_rad, color,
                p_info.get('direction', DIR_NONE), p_info.get('name', f"P{p_id}"),
                is_me=(p_id == my_id), has_flag=p_info.get('hasFlag', False), tick_ms=tick_ms
            )

        # NUEVO: barra de HUD con info de la partida y ayuda de controles
        mi_nombre = players_data.get(my_id, {}).get('name', f"P{my_id}")
        draw_hud(screen, int(MAP_SIZE * SCALE), hud_font, help_font, my_id, mi_nombre, len(players_data), clock.get_fps())

        # NUEVO: Cartel de victoria si la partida ya terminó
        if game_over:
            text_surf = font_banner.render(winner_text, True, (255, 215, 0))
            text_rect = text_surf.get_rect(center=(int(MAP_SIZE * SCALE) // 2, int(MAP_SIZE * SCALE) // 2))
            pygame.draw.rect(screen, (0, 0, 0), text_rect.inflate(20, 20))
            pygame.draw.rect(screen, (255, 215, 0), text_rect.inflate(20, 20), 2)
            screen.blit(text_surf, text_rect)

        pygame.display.flip()
        clock.tick(60) # El cliente corre a 60 FPS suavizado, aunque reciba 20 Ticks/s

    # NUEVO: avisamos al servidor que nos vamos (LEAVE, 0x13) antes de cerrar
    send_tcp_message(client_socket, 0x13, b'')

    pygame.quit()
    sys.exit()

# ==========================================
# NUEVO: SALA DE ESPERA GRÁFICA (Fase previa al juego)
# ==========================================
def run_lobby_screen(client_socket):
    pygame.init()

    ancho, alto = 480, 420
    screen = pygame.display.set_mode((ancho, alto))
    pygame.display.set_caption("Captura la Bandera - Sala de espera")
    clock = pygame.time.Clock()

    font_titulo = pygame.font.SysFont(None, 34)
    font_jugador = pygame.font.SysFont(None, 24)
    font_countdown = pygame.font.SysFont(None, 90)
    font_estado = pygame.font.SysFont(None, 22)

    my_id = None
    jugadores_sala = {} # NUEVO: id -> nombre, se va llenando con cada LOBBY_STATE
    countdown_seconds = None
    game_config = None

    running = True
    while running:
        # Cerrar la ventana también nos saca de la sala de espera
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                client_socket.close()
                pygame.quit()
                sys.exit()

        # Leer mensajes del servidor sin bloquear la ventana
        readable, _, _ = select.select([client_socket], [], [], 0)
        if readable:
            msg_type, payload = receive_tcp_message(client_socket)
            if msg_type is None:
                print("Desconectado del servidor.")
                pygame.quit()
                sys.exit()

            elif msg_type == 0x22: # LOBBY_STATE
                offset = 0
                state, count = struct.unpack_from('>BB', payload, offset)
                offset += 2
                jugadores_sala = {}
                for _ in range(count):
                    p_id = struct.unpack_from('>H', payload, offset)[0]
                    offset += 2
                    p_name, offset = unpack_str(payload, offset)
                    jugadores_sala[p_id] = p_name

            elif msg_type == 0x20: # JOIN_ACCEPTED
                my_id, _ = struct.unpack('>HH', payload)

            elif msg_type == 0x23: # GAME_COUNTDOWN
                countdown_seconds = struct.unpack('>B', payload)[0]

            elif msg_type == 0x24: # GAME_STARTED
                offset = 0

                # Lee las variables base (i32 x5, u16 x1)
                m_size, c_rad, p_rad, p_speed, int_rad, tick = struct.unpack_from('>iiiiiH', payload, offset)
                offset += 22

                game_config = {
                    'map_size': m_size / 100.0,
                    'circle_radius': c_rad / 100.0,
                    'player_radius': p_rad / 100.0,
                    'player_speed': p_speed / 100.0,
                    'interaction_radius': int_rad / 100.0,
                    'tick_interval_ms': tick
                }

                # Lee el estado inicial de la bandera (u8 estado, u16 dueño, i32 X, i32 Y = 11 bytes)
                f_status, f_carrier, f_x, f_y = struct.unpack_from('>BHii', payload, offset)
                offset += 11
                game_config['flag'] = {
                    'status': f_status, 'carrierId': f_carrier,
                    'x': f_x / 100.0, 'y': f_y / 100.0
                }

                # Lee la lista de jugadores (id, nombre, posición, dirección, bandera)
                p_count = struct.unpack_from('>B', payload, offset)[0]
                offset += 1

                game_config['players'] = {}
                for _ in range(p_count):
                    p_id = struct.unpack_from('>H', payload, offset)[0]
                    offset += 2
                    p_name, offset = unpack_str(payload, offset)
                    p_x, p_y, p_dir, p_flag = struct.unpack_from('>iiBb', payload, offset)
                    offset += 10

                    game_config['players'][p_id] = {
                        'name': p_name,
                        'x': p_x / 100.0, 'y': p_y / 100.0,
                        'direction': p_dir, 'hasFlag': bool(p_flag)
                    }

                running = False # Ya tenemos todo lo necesario para arrancar el juego

        # --- Dibujar la sala de espera ---
        screen.fill((22, 24, 30))

        titulo = font_titulo.render("Sala de espera", True, (255, 255, 255))
        screen.blit(titulo, titulo.get_rect(center=(ancho // 2, 34)))

        y = 90
        if jugadores_sala:
            for p_id, p_name in jugadores_sala.items():
                etiqueta = f"P{p_id:02d} - {p_name}" + ("  (vos)" if p_id == my_id else "")
                color = (120, 200, 255) if p_id == my_id else (220, 220, 220)
                fila = font_jugador.render(etiqueta, True, color)
                screen.blit(fila, (40, y))
                y += 28
        else:
            espera = font_estado.render("Esperando jugadores...", True, (150, 150, 150))
            screen.blit(espera, (40, y))

        # Countdown grande abajo, o el mensaje de que el anfitrión todavía no arrancó
        if countdown_seconds is not None:
            if countdown_seconds > 0:
                texto, color = str(countdown_seconds), (255, 215, 0)
            else:
                texto, color = "¡YA!", (90, 210, 120)
            cd_surf = font_countdown.render(texto, True, color)
            screen.blit(cd_surf, cd_surf.get_rect(center=(ancho // 2, alto - 90)))
        else:
            info = font_estado.render("El anfitrión iniciará la partida pronto...", True, (150, 150, 150))
            screen.blit(info, info.get_rect(center=(ancho // 2, alto - 40)))

        pygame.display.flip()
        clock.tick(30)

    return my_id, game_config

def start_client():
    available_servers = discover_servers()
    if not available_servers:
        print("No se encontraron servidores. ")
        return
        
    print("\n--- SERVIDORES ENCONTRADOS ---")
    for i, srv in enumerate(available_servers):
        print(f"[{i}] {srv['name']} ({srv['players']}/{srv['max']} jugadores) - IP: {srv['ip']}")
        
    #target_server = available_servers[0] # Auto-seleccionar para la prueba
    #print(f"\nConectando automáticamente al servidor: {target_server['name']}...")
    seleccion = input("\nElige el número del servidor para conectarte: ")
    try:
        index = int(seleccion)
        target_server = available_servers[index]
    except (ValueError, IndexError):
        print("Selección inválida.")
        return
    
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.connect((target_server['ip'], target_server['port']))
    client_socket.setblocking(False)

    join_payload = pack_str("Jugador")
    send_tcp_message(client_socket, 0x10, join_payload)

    print("Esperando arranque...")

    try:
        # NUEVO: la ventana gráfica aparece desde que nos conectamos, mostrando
        # la sala de espera (jugadores conectándose) y el countdown en vivo
        my_id, game_config = run_lobby_screen(client_socket)

        if my_id is not None and game_config is not None:
            print("\n¡Arrancando interfaz gráfica!")
            run_game_loop(client_socket, my_id, game_config)

    except KeyboardInterrupt:
        print("\nSaliendo...")
        client_socket.close()

if __name__ == "__main__":
    start_client()