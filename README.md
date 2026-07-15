# Capture the flag - CC8

Este repositorio contiene la implementación en Python del proyecto "Captura la Bandera" para el curso CC8. El proyecto consiste en una arquitectura cliente-servidor donde los jugadores compiten individualmente para capturar y sacar una bandera del tablero.

## Características Técnicas
* **Arquitectura:** Cliente-Servidor
* **Protocolo de Transporte:** TCP
* **Formato de Mensajes:** JSON codificado en UTF-8, enviado en una sola línea y terminado con `\n`
* **Puerto del Servidor:** 5000 (por defecto)
* **Intervalo de Movimiento del Servidor (Tick):** 200 ms

## Estructura del Proyecto y Registro de Archivos

El código está organizado modularmente para separar la lógica de red, las reglas del juego y la interfaz gráfica:

* **`main.py`**: Punto de entrada principal. Permite al usuario elegir entre el modo "CREAR PARTIDA" (Servidor) o "UNIRSE A PARTIDA" (Cliente).
* **`common/`**: Módulo de recursos compartidos.
  * `protocol.py`: (Pendiente) Contiene las funciones `send_message` y `receive_message` encargadas de estandarizar el envío y recepción de JSON vía TCP respetando el formato de línea única con `\n`.
  * `constants.py`: (Pendiente) Almacenará estados estandarizados (WAITING, RUNNING) y direcciones (UP, DOWN, LEFT, RIGHT).
* **`server/`**: Módulo del servidor (Fuente oficial del estado del juego).
  * `server_core.py`: (Pendiente) Maneja el socket TCP principal y utiliza hilos (`threading`) para escuchar múltiples conexiones entrantes simultáneamente.
  * `game_state.py`: (Pendiente) Almacenará la matriz del tablero, posición de obstáculos y bandera.
  * `game_loop.py`: (Pendiente) Ejecutará el ciclo continuo de movimientos y resolución de colisiones.
* **`client/`**: Módulo del jugador (Front-end).
  * `client_core.py`: (Pendiente) Manejará la conexión TCP del jugador hacia el servidor.
  * `ui.py`: (Pendiente) Renderizará el tablero basándose en el estado dictado por el servidor.

## Instrucciones de Ejecución (Fase de Pruebas)

### Requisitos
* Python 3.x
* No requiere librerías externas de momento (utiliza `socket`, `json` y `threading` de la librería estándar).