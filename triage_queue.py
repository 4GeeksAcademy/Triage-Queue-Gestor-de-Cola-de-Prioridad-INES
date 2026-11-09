"""Triage Queue: gestor de cola de prioridad para urgencias.

Diseño
------
Hay solo tres niveles de triaje, así que la cola de prioridad se modela con
una cola FIFO (``deque``) por nivel:

* encolar    -> O(1): se añade al final de la cola de su nivel.
* desencolar -> O(1): se toma de la primera cola no vacía (nivel 1, 2, 3).
* peek       -> O(1).
* stats      -> O(1).
* listar     -> O(n): concatenación de las tres colas.

Un paciente crítico que llega a mitad de proceso pasa delante de los de nivel
2 y 3 sin reordenar nada, y el orden de llegada dentro de cada nivel lo
garantiza la propia estructura FIFO.

Todas las operaciones están protegidas con un ``Lock`` para que dos hilos
(o dos puestos de enfermería) no corrompan la cola al actualizarla a la vez.
"""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum


class TriageLevel(IntEnum):
    CRITICAL = 1
    URGENT = 2
    STANDARD = 3

    @property
    def label(self) -> str:
        return {1: "crítico", 2: "urgente", 3: "estándar"}[self.value]


class EmptyQueueError(Exception):
    """Se intentó atender o consultar a un paciente con la cola vacía."""


@dataclass(frozen=True)
class Patient:
    """Paciente en urgencias. Se valida al crearlo.

    ``triage_level`` es 1 (crítico), 2 (urgente) o 3 (estándar); se guarda como
    ``TriageLevel``, que es un ``int``. ``arrived_at`` es ahora por defecto.
    """

    name: str
    triage_level: TriageLevel
    arrived_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self) -> None:
        name = self.name.strip() if isinstance(self.name, str) else ""
        if not name:
            raise ValueError("El nombre del paciente no puede estar vacío.")
        try:
            level = TriageLevel(self.triage_level)
        except ValueError:
            raise ValueError(
                f"Nivel de triaje inválido: {self.triage_level!r} (usa 1, 2 o 3)."
            ) from None
        # La dataclass es inmutable, así que se normaliza con object.__setattr__.
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "triage_level", level)

    def __str__(self) -> str:
        hora = self.arrived_at.strftime("%H:%M:%S")
        return f"{self.name} [nivel {self.triage_level.value} - {self.triage_level.label}] llegó {hora}"


class TriageQueue:
    def __init__(self) -> None:
        self._queues: dict[TriageLevel, deque[Patient]] = {
            level: deque() for level in TriageLevel
        }
        self._lock = threading.Lock()

    def enqueue(self, patient: Patient) -> None:
        """Añade un paciente: va al final de la cola de su nivel de triaje."""
        if not isinstance(patient, Patient):
            raise TypeError(
                f"enqueue espera un Patient, no {type(patient).__name__}."
            )
        with self._lock:
            self._queues[patient.triage_level].append(patient)

    def dequeue(self) -> Patient:
        """Retira y devuelve al siguiente paciente a atender."""
        with self._lock:
            queue = self._first_non_empty()
            if queue is None:
                raise EmptyQueueError("No hay pacientes en espera.")
            return queue.popleft()

    def peek(self) -> Patient:
        """Devuelve al siguiente paciente sin retirarlo."""
        with self._lock:
            queue = self._first_non_empty()
            if queue is None:
                raise EmptyQueueError("No hay pacientes en espera.")
            return queue[0]

    def list_queue(self) -> list[Patient]:
        """Todos los pacientes en espera, en el orden en que serán atendidos."""
        with self._lock:
            return [p for level in TriageLevel for p in self._queues[level]]

    def stats(self) -> dict[TriageLevel, int]:
        """Número de pacientes en espera por nivel de triaje."""
        with self._lock:
            return {level: len(q) for level, q in self._queues.items()}

    def __len__(self) -> int:
        with self._lock:
            return sum(len(q) for q in self._queues.values())

    def _first_non_empty(self) -> deque[Patient] | None:
        # Debe llamarse con el lock adquirido. Itera en orden 1, 2, 3.
        for level in TriageLevel:
            if self._queues[level]:
                return self._queues[level]
        return None


# --------------------------------------------------------------------------
# Interfaz de terminal
# --------------------------------------------------------------------------

AYUDA = """\
Comandos:
  add <nivel> <nombre>   Registrar paciente (1=crítico, 2=urgente, 3=estándar)
  next                   Llamar al siguiente paciente (lo retira de la cola)
  peek                   Ver quién es el siguiente sin retirarlo
  list                   Listar la cola en orden de atención
  stats                  Pacientes en espera por nivel
  help                   Mostrar esta ayuda
  quit                   Salir"""


def handle_command(queue: TriageQueue, line: str) -> str | None:
    """Ejecuta un comando y devuelve el texto a mostrar. None = salir."""
    parts = line.strip().split(maxsplit=2)
    if not parts:
        return ""
    cmd = parts[0].lower()

    try:
        if cmd == "add":
            if len(parts) < 3:
                return "Uso: add <nivel> <nombre>"
            try:
                level = int(parts[1])
            except ValueError:
                return f"Nivel inválido: {parts[1]!r} (usa 1, 2 o 3)."
            patient = Patient(parts[2], level)
            queue.enqueue(patient)
            return f"Registrado: {patient}"
        if cmd == "next":
            return f"Atendiendo a: {queue.dequeue()}"
        if cmd == "peek":
            return f"Siguiente: {queue.peek()}"
        if cmd == "list":
            patients = queue.list_queue()
            if not patients:
                return "La cola está vacía."
            return "\n".join(f"{i}. {p}" for i, p in enumerate(patients, 1))
        if cmd == "stats":
            stats = queue.stats()
            lines = [f"Nivel {l.value} ({l.label}): {n}" for l, n in stats.items()]
            lines.append(f"Total: {sum(stats.values())}")
            return "\n".join(lines)
        if cmd == "help":
            return AYUDA
        if cmd in ("quit", "exit"):
            return None
        return f"Comando desconocido: {cmd!r}. Escribe 'help'."
    except (ValueError, EmptyQueueError) as e:
        return f"Error: {e}"


def main() -> None:
    queue = TriageQueue()
    print("Triage Queue - gestor de cola de prioridad")
    print(AYUDA)
    while True:
        try:
            line = input("\ntriage> ")
        except (EOFError, KeyboardInterrupt):
            print()
            break
        output = handle_command(queue, line)
        if output is None:
            break
        if output:
            print(output)


if __name__ == "__main__":
    main()
