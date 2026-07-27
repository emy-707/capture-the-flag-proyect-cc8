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
        print(f"Error UDP: {e}")
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
        print("No se encontraron servidores. Asegúrate de encender el servidor primero.")
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

    print("Esperando eventos de la sala (Presiona Ctrl+C para salir)...")
    try:
        while True:
            msg_type, payload = receive_tcp_message(client_socket)
            if msg_type is None: continue
            
            if msg_type == 0x20: # JOIN_ACCEPTED
                my_player_id = struct.unpack('>HH', payload)[0]
                print(f"¡Éxito! Mi ID oficial es: P{my_player_id:02d}")
                
            elif msg_type == 0x22: # LOBBY_STATE
                offset = 0
                state, count = struct.unpack_from('>BB', payload, offset)
                offset += 2
                print(f"\n--- ACTUALIZACIÓN DE SALA ({count} JUGADORES) ---")
                for _ in range(count):
                    p_id = struct.unpack_from('>H', payload, offset)[0]
                    offset += 2
                    p_name, offset = unpack_str(payload, offset)
                    print(f" -> P{p_id:02d}: {p_name}")
                    
    except KeyboardInterrupt:
        print("\nSaliendo...")
        client_socket.close()

if __name__ == "__main__":
    start_client()