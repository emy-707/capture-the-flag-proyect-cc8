# Capture The Flag — CC8

Implementación cliente-servidor del juego **"Captura la Bandera"**, desarrollada según la especificación acordada en el curso **PRFC-CC8-2026 (v3.0.0)**. El proyecto permite hospedar una partida como servidor o conectarse como cliente, e interopera con las implementaciones de cualquier otro grupo que respete el mismo protocolo.

## Integrantes

| Nombre | Carné |
|---|---|
| Emely Batres | 22004903 |
| Victor Arias | 15001915 |

## Tecnologías

| | |
|---|---|
| Lenguaje | Python |
| Conexión en red | Sockets (TCP + UDP) |
| Librería gráfica | Pygame |
| Formato de mensajes | Binario, big-endian (`struct`) |

## Descripción del juego

Todos los jugadores compiten de forma individual por una única bandera ubicada en el centro de un círculo. Para ganar, un jugador debe:

1. Entrar al círculo central.
2. Tomar la bandera (tecla de interacción).
3. Salir **completamente** del círculo llevándola.

Cualquier otro jugador puede robar la bandera acercándose al portador e interactuando; el robo es instantáneo y no existe tiempo de inmunidad. Si el portador se desconecta, la bandera cae en su última posición y puede volver a tomarse.

## Arquitectura

- Arquitectura cliente-servidor: un único servidor por partida, hasta 100 jugadores conectados directamente a él.
- El servidor mantiene el estado oficial del juego y valida todas las acciones; los clientes solo envían dirección de movimiento (`INPUT`) e intención de interactuar (`INTERACT`), nunca posiciones.
- El servidor **no participa como jugador**: únicamente hospeda y visualiza la partida (modo espectador).
- Descubrimiento de servidores por **UDP broadcast** en el puerto `5001`, y comunicación de la partida completa por **TCP** en el puerto `5000`.
- Los mensajes viajan como bytes (no JSON), con un encabezado común de tipo (`u8`) + versión de protocolo (`u8`), enmarcados en TCP con un prefijo de longitud `u16`.

```
main.py                    # Punto de entrada: elegir modo Servidor o Cliente
├── server/
│   └── main.py             # Lógica del servidor (ciclo de juego, validaciones, motor de espectador)
├── client/
│   └── main.py             # Lógica del cliente (lobby, entrada de teclado, motor gráfico)
└── common/
    └── protocol.py         # Framing TCP, empaquetado/desempaquetado de mensajes, versión del protocolo
```

## Protocolo de comunicación

Este proyecto implementa la versión **3** del protocolo (`PROTOCOL_VERSION = 3` en `protocol.py`), definida en el documento `PRFC-CC8-2026`. Los mensajes principales:

| Mensaje | Código | Sentido |
|---|---|---|
| `DISCOVER_REQUEST` / `DISCOVER_RESPONSE` | `0x01` / `0x02` | Descubrimiento (UDP) |
| `JOIN` | `0x10` | Cliente → Servidor |
| `INPUT` | `0x11` | Cliente → Servidor (dirección activa) |
| `INTERACT` | `0x12` | Cliente → Servidor (tomar/robar bandera) |
| `LEAVE` | `0x13` | Cliente → Servidor |
| `JOIN_ACCEPTED` / `JOIN_REJECTED` | `0x20` / `0x21` | Servidor → Cliente |
| `LOBBY_STATE` | `0x22` | Servidor → Cliente |
| `GAME_COUNTDOWN` | `0x23` | Servidor → Cliente |
| `GAME_STARTED` | `0x24` | Servidor → Cliente |
| `GAME_STATE` | `0x25` | Servidor → Cliente (por cada tick) |
| `FLAG_PICKED_UP` / `FLAG_STOLEN` | `0x26` / `0x27` | Servidor → Cliente |
| `PLAYER_DISCONNECTED` | `0x28` | Servidor → Cliente |
| `GAME_OVER` | `0x29` | Servidor → Cliente |
| `ERROR` | `0x2A` | Servidor → Cliente |

Funciones clave en `common/protocol.py`:

- `recv_exact(sock, n)`: lee exactamente `n` bytes del socket, insistiendo hasta reunirlos (TCP no garantiza fronteras de mensaje).
- `receive_tcp_message(sock)` / `send_tcp_message(sock, msg_type, payload)`: arman y desarman el enmarcado (prefijo `u16` de longitud + encabezado tipo/versión).
- `pack_str(text)` / `unpack_str(buffer, offset)`: empaquetan strings como un `u8` de longitud seguido de bytes UTF-8.

La especificación completa (reglas del juego, formato exacto de cada mensaje byte a byte, parámetros configurables, etc.) está en `PRFC-VERSION-3.md`.

## Requisitos

```bash
pip install pygame
```

Python 3.10+ recomendado.

## Cómo ejecutar

Desde la raíz del proyecto:

```bash
python main.py
```

El menú inicial permite elegir entre:

- **Modo Servidor**: hospeda una partida nueva. Queda escuchando en el puerto TCP `5000` y respondiendo al descubrimiento en el puerto UDP `5001`. Al presionar `Enter` en la consola del servidor inicia la cuenta regresiva y la partida.
- **Modo Cliente**: busca servidores disponibles en la red local (o permite conexión manual por IP/puerto), muestra la lista de partidas encontradas y, al elegir una, conecta vía TCP y entra a la sala de espera.

Controles del cliente:

| Tecla | Acción |
|---|---|
| Flechas / WASD | Moverse (arriba, abajo, izquierda, derecha) |
| Barra espaciadora | Interactuar (tomar / robar la bandera) |

## Historial de desarrollo

1. **Estructura inicial de carpetas y README** — organización del proyecto en `common/`, `server/` y `client/`.
2. **Implementación de TCP/UDP entre cliente y servidor** — se reemplazó el transporte inicial en JSON por un protocolo binario, y se implementaron las funciones base de recepción/envío (`recv_exact`, `receive_tcp_message`, `send_tcp_message`) y de conversión (`pack_str`, `unpack_str`).
3. **Bucle no bloqueante y handshake bidireccional** — `JOIN` / `JOIN_ACCEPTED` / `JOIN_REJECTED`, validación de versión de protocolo y asignación de `playerId`, usando sockets no bloqueantes (`setblocking(False)`).
4. **Broadcast y `LOBBY_STATE`** — descubrimiento de servidores por UDP broadcast (`DISCOVER_REQUEST` / `DISCOVER_RESPONSE`) y notificación de cambios en la sala de espera.
5. **Cuenta regresiva** — el anfitrión inicia la partida manualmente desde la consola del servidor.
6. **Motor gráfico** — integración de Pygame con socket no bloqueante también del lado del cliente, para mantener 60 FPS sin depender del ritmo del servidor.
7. **Lógica final de juego** — bandera, acciones de tomar/robar, cálculo de si el portador sale completamente del círculo, y fin de partida (`GAME_OVER`).

## Repositorio

https://github.com/emy-707/capture-the-flag-proyect-cc8