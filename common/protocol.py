import struct

# La versión oficial de este protocolo es la 3
PROTOCOL_VERSION = 3
"""
    Función que lee exactamente 'n' bytes del socket.
    Como TCP no tiene fronteras de mensaje, puede entregar la lectura partida.
    Esta función insiste hasta juntar los 'n' bytes solicitados.
"""

def recv_exact(sock, n):
    data = bytearray()
    while len(data) < n:
        try:
            packet = sock.recv(n -len(data))
            if not packet:
                return None     # Desconexión limpia
            # Toma los bytes nuevos que acaban de llegar a packet y los añade al final de data
            data.extend(packet)
        except BlockingIOError:
            # Si el socket es no bloqueante y no hay datos, espera
            # El programa continúa de inmediato a refrescar el juego.
            pass
        except Exception:
            return None
    return bytes(data)

"""
    Función que lee un mensaje completo, respetando el enmarcado de longitud (u16).
    Retorna (tipo_mensaje, payload_bytes) o (None, None) so hay error. 
"""
def receive_tcp_message(sock):
    # 1. Lee los 2 bytes del prefijo de longitur (u16)
    len_bytes = recv_exact(sock, 2)
    if not len_bytes:
        return None, None

    # Desempaquetando el u16 big-endian ('>H')
    # H: Unsigned Short, >: orden de lectura (primer bit más significativo)
    # Traduce de bytes a número entero; los devuelve en una lista
    msg_length = struct.unpack('>H', len_bytes)[0]

    # 2. Lee exactamente el cuerpo del mensaje según la longitud
    body_bytes = recv_exact(sock, msg_length)
    if not body_bytes or len(body_bytes) < 2:
        return None, None

    # 3. Lee el encabezado común (tipo y versión)
    msg_type = body_bytes[0]
    version = body_bytes[1]

    if version != PROTOCOL_VERSION:
        print(f"Advertencia: Versión de protocolo no soportada ({version})")
        # El servidor debería manejar esto enviando un ERROR

    # Retornas el tipo y el resto de los bytes (sin el encabezado)
    payload = body_bytes[2:]
    return msg_type, payload

"""
    Construye el enmarcado de longitud, agrega el encabezado (tipo + versión)
    y lo envía por el socket TCP.
"""
def send_tcp_message(sock, msg_type, payload=b""):
    # El cuerpo total es: Tipo (1) + Versión (1) + Payload (N)
    body = struct.pack('>BB', msg_type, PROTOCOL_VERSION) + payload
    
    # El prefijo de longitud es un u16 (2 bytes) del tamaño total del cuerpo
    msg_length = len(body)
    framed_message = struct.pack('>H', msg_length) + body
    
    try:
        sock.sendall(framed_message)
        return True
    except Exception as e:
        print(f"Error enviando mensaje: {e}")
        return False


"""
    Empaqueta un string como 1 byte (u8) de longitud seguido de N bytes UTF-8.
"""
def pack_str(text):
    encoded = text.encode('utf-8')
    length = len(encoded)
    # Si el nombre tiene más de 255 caracteres, lo truncamos para que quepa en u8
    if length > 255:
        encoded = encoded[:255]
        length = 255
    return struct.pack('>B', length) + encoded

"""
    Desempaqueta un string desde buffer empezando en offset.
    Retorna (texto_decodificado, nuevo_offset).
"""
def unpack_str(buffer, offset=0):
    length = struct.unpack_from('>B', buffer, offset)[0]
    offset += 1

    texto = buffer[offset:offset+length].decode('utf-8')
    offset += length
    
    return texto, offset