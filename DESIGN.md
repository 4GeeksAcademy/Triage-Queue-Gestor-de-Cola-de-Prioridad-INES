# Notas de diseño

## 1. Estructura de datos: una `deque` por nivel de triaje

`TriageQueue` guarda un `dict` con tres `collections.deque` (niveles 1, 2 y 3).

| Operación | Coste | Cómo |
|---|---|---|
| `enqueue` | O(1) normal, O(n) en el caso raro | Se añade al final de la cola de su nivel. |
| `dequeue` / `peek` | O(1) | Se toma el primero de la primera cola no vacía (1, 2, 3). |
| `stats` | O(1) | Longitud de cada cola. |
| `list_queue` | O(n) | Concatenación de las tres colas. |

El caso raro de `enqueue` es un paciente cuyo `arrived_at` es anterior al de otros ya encolados en su mismo nivel. Entonces se inserta en su sitio con `bisect_right`.

**Alternativas descartadas**

- **Una sola `deque`:** insertar un crítico por delante de los de nivel 2 y 3 obliga a recorrerla o a reordenarla. Es O(n) en el caso que más importa, que es la llegada de un crítico.
- **Lista ordenada (`insort`):** cada alta cuesta O(n), por el desplazamiento de elementos, y sacar el primero con `pop(0)` también es O(n).
- **`heapq` con clave `(nivel, llegada, nº de secuencia)`:** es correcto y es la opción general para prioridades arbitrarias. Cuesta O(log n) al encolar y al desencolar. Pero `list_queue` necesita ordenar una copia (O(n log n)) y `stats` necesita contadores aparte. Además, el desempate FIFO hay que codificarlo a mano con el número de secuencia.
- **Tres colas separadas (la elegida):** hay solo tres niveles fijos, así que "la prioridad" se reduce a mirar las colas en orden. El FIFO dentro de cada nivel lo da la propia estructura, sin desempates. Si los niveles fueran muchos o dinámicos, pasaría a `heapq`.

Solo se usa la biblioteca estándar: `collections`, `bisect`, `dataclasses`, `datetime`, `enum`, `threading` y `typing`.

## 2. Concurrencia: un worker extrae mientras otro encola un crítico

**Mecanismo.** Un único `threading.Lock` protege toda la estructura. `enqueue`, `dequeue`, `peek`, `list_queue`, `stats` y `__len__` toman el lock, y ninguna operación lo mantiene más tiempo del necesario.

**Orden de mutación en `dequeue`.** Elegir al paciente y retirarlo es un único paso, dentro de la misma sección crítica:

1. Se adquiere el lock.
2. Se localiza la primera cola no vacía.
3. Se hace `popleft()` sobre ella: el paciente deja de estar en la estructura.
4. Se libera el lock y se devuelve el paciente.

Nunca se hace "mirar, soltar el lock y luego retirar". Ese patrón comprobar-y-actuar es lo que permitiría que dos workers vean al mismo paciente como "el siguiente" y lo procesen dos veces. Aquí, quien toma el lock primero lo retira, y el siguiente worker ya no lo ve.

**Qué pasa con la carrera concreta.** El lock serializa las dos operaciones, y los dos resultados posibles son válidos:

- **`enqueue` del crítico primero:** el crítico queda al frente y el `dequeue` lo extrae.
- **`dequeue` primero:** el worker se lleva al que era el siguiente, y el crítico será el siguiente en salir.

En ningún caso se pierde un paciente ni se entrega dos veces, y el orden de prioridad se mantiene.

**Límites.**

- **`peek` no es una reserva:** si dos workers hacen `peek` y luego `dequeue`, el segundo puede recibir a otro paciente distinto del que vio. Para atender hay que usar solo el valor que devuelve `dequeue()`. `peek` es solo informativo.
- **Alcance del `Lock`:** protege entre hilos de un mismo proceso. Con varios procesos o máquinas haría falta un almacén compartido, como una base de datos o un broker de mensajes, con extracción atómica, por ejemplo `SELECT ... FOR UPDATE SKIP LOCKED`.
