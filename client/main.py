import socket
import sys
import os
import time
import struct

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.protocol import  send_tcp_message, pack_str, receive_tcp_message, unpack_str

DISCOVERY_PORT = 5001

def discover_servers():
    print("Buscando servidores en la red local (Broadcast UDP)...")
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1) # Permitir broadcast
    udp_socket.settimeout(2.0) # Esperar max 2 segundos
    
    # Paquete DISCOVER_REQUEST: tipo 0x01
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
                offset = 2
                game_id = struct.unpack_from('>H', data, offset)[0]
                offset += 2
                server_name, offset = unpack_str(data, offset)
                tcp_port, state, p_count, max_p = struct.unpack_from('>H B H H', data, offset)
                
                if state == 0x01: # Solo si el servidor está en WAITING
                    servers.append({
                        'ip': addr[0], 'port': tcp_port, 'name': server_name, 
                        'players': p_count, 'max': max_p
                    })
        except socket.timeout:
            break # Pasaron los 2 segundos

    udp_socket.close()
    return servers

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

    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.connect((target_server['ip'], target_server['port']))
    client_socket.setblocking(False)

    join_payload = pack_str("Jugador")
    send_tcp_message(client_socket, 0x10, join_payload)

    print("Esperando inicio de la partida... (Presiona Ctrl+C para salir)")
    game_data = None
    try:
        while True:
            msg_type, payload = receive_tcp_message(client_socket)
            if msg_type is None: continue
            
            if msg_type == 0x22: # LOBBY_STATE
                print(" -> Actualización de sala recibida.")
                
            elif msg_type == 0x23: # GAME_COUNTDOWN
                seconds_left = struct.unpack('>B', payload)[0]
                if seconds_left > 0:
                    print(f">>> La partida inicia en {seconds_left}...")
                else:
                    print(">>> ¡Preparando entorno gráfico!")

            elif msg_type == 0x24: # GAME_STARTED
                print("\n[!] ¡Paquete GAME_STARTED recibido! Desempaquetando variables...")
                offset = 0
                
                # Lee las variables base (i32 x5, u16 x1)
                m_size, c_rad, p_rad, p_speed, int_rad, tick = struct.unpack_from('>iiiiiH', payload, offset)
                offset += 22
                
                print(f" -> Mapa: {m_size/100}x{m_size/100}, Radio círculo: {c_rad/100}")
                print(f" -> Velocidad: {p_speed/100} u/s, Tick: {tick}ms")
                
                f_status, f_carrier, f_x, f_y = struct.unpack_from('>BHii', payload, offset)
                offset += 11
                
                p_count = struct.unpack_from('>B', payload, offset)[0]
                offset += 1
                
                print(f" -> Jugadores inicializados: {p_count}")
                for _ in range(p_count):
                    p_id = struct.unpack_from('>H', payload, offset)[0]
                    offset += 2
                    p_name, offset = unpack_str(payload, offset)
                    p_x, p_y, p_dir, p_flag = struct.unpack_from('>iiBb', payload, offset)
                    offset += 10
                    print(f"    - P{p_id:02d} ({p_name}) spawneado en ({p_x/100:.1f}, {p_y/100:.1f})")
                
                print("\nSetup completado. Listo para pasarle el control al Motor Gráfico.")
                break # Rompe el bucle TCP puro
    except KeyboardInterrupt:
        print("\nSaliendo...")
        pass
        client_socket.close()

if __name__ == "__main__":
    start_client()