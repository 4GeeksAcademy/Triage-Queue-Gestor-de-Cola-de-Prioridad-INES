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
from typing import Callable


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

MENU = """\
=== Triage Queue ===
1. Añadir nuevo paciente
2. Llamar al siguiente paciente
3. Ver la cola actual
4. Ver estadísticas de la cola
5. Salir"""


def ask_name(input_fn: Callable[[str], str], print_fn: Callable[[str], None]) -> str:
    while True:
        name = input_fn("Nombre del paciente: ").strip()
        if name:
            return name
        print_fn("El nombre no puede estar vacío.")


def ask_level(input_fn: Callable[[str], str], print_fn: Callable[[str], None]) -> int:
    while True:
        raw = input_fn("Nivel de triaje (1=crítico, 2=urgente, 3=estándar): ").strip()
        try:
            return TriageLevel(int(raw))
        except ValueError:
            print_fn(f"Nivel inválido: {raw!r}. Usa 1, 2 o 3.")


def add_patient(queue: TriageQueue, input_fn, print_fn) -> None:
    patient = Patient(ask_name(input_fn, print_fn), ask_level(input_fn, print_fn))
    queue.enqueue(patient)
    print_fn(f"Registrado: {patient}")


def call_next(queue: TriageQueue, print_fn) -> None:
    try:
        print_fn(f"Atendiendo a: {queue.dequeue()}")
    except EmptyQueueError as e:
        print_fn(f"Error: {e}")


def show_queue(queue: TriageQueue, print_fn) -> None:
    patients = queue.list_queue()
    if not patients:
        print_fn("La cola está vacía.")
        return
    for i, p in enumerate(patients, 1):
        print_fn(f"{i}. {p}")


def show_stats(queue: TriageQueue, print_fn) -> None:
    stats = queue.stats()
    for level, count in stats.items():
        print_fn(f"Nivel {level.value} ({level.label}): {count}")
    print_fn(f"Total: {sum(stats.values())}")


def run_menu(
    queue: TriageQueue,
    input_fn: Callable[[str], str] = input,
    print_fn: Callable[[str], None] = print,
) -> None:
    """Bucle del menú. input_fn y print_fn son inyectables para poder testear."""
    while True:
        print_fn("\n" + MENU)
        try:
            option = input_fn("Elige una opción: ").strip()
            if option == "1":
                add_patient(queue, input_fn, print_fn)
            elif option == "2":
                call_next(queue, print_fn)
            elif option == "3":
                show_queue(queue, print_fn)
            elif option == "4":
                show_stats(queue, print_fn)
            elif option == "5":
                print_fn("Hasta luego.")
                return
            else:
                print_fn(f"Opción inválida: {option!r}. Elige un número del 1 al 5.")
        except (EOFError, KeyboardInterrupt):
            print_fn("\nHasta luego.")
            return


def main() -> None:
    run_menu(TriageQueue())


if __name__ == "__main__":
    main()
