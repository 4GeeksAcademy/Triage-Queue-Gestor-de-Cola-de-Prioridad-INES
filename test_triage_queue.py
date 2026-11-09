import threading
import unittest
from datetime import datetime, timedelta

from triage_queue import (
    EmptyQueueError,
    Patient,
    TriageLevel,
    TriageQueue,
    run_menu,
)

T0 = datetime(2026, 1, 1, 8, 0, 0)


class TriageQueueTests(unittest.TestCase):
    def setUp(self):
        self.q = TriageQueue()
        self.minute = 0

    def add(self, name, level):
        """Crea un paciente con hora de llegada creciente y lo encola."""
        self.minute += 1
        p = Patient(name, level, T0 + timedelta(minutes=self.minute))
        self.q.enqueue(p)
        return p

    def names(self):
        return [p.name for p in self.q.list_queue()]

    def test_patient_fields(self):
        p = Patient("Ana", 2, T0)
        self.assertEqual(p.name, "Ana")
        self.assertEqual(p.triage_level, 2)
        self.assertIsInstance(p.triage_level, int)
        self.assertEqual(p.arrived_at, T0)

    def test_arrived_at_defaults_to_now(self):
        before = datetime.now()
        p = Patient("Ana", 1)
        self.assertGreaterEqual(p.arrived_at, before)
        self.assertLessEqual(p.arrived_at, datetime.now())

    def test_patient_validation(self):
        for bad in (0, 4, -1, "x", None):
            with self.assertRaises(ValueError):
                Patient("Ana", bad)
        for bad_name in ("   ", "", None):
            with self.assertRaises(ValueError):
                Patient(bad_name, 1)

    def test_enqueue_rejects_non_patient(self):
        with self.assertRaises(TypeError):
            self.q.enqueue("Ana")
        self.assertEqual(len(self.q), 0)

    def test_priority_order(self):
        self.add("estandar", 3)
        self.add("urgente", 2)
        self.add("critico", 1)
        self.assertEqual(self.names(), ["critico", "urgente", "estandar"])

    def test_fifo_within_same_level(self):
        for n in ["a", "b", "c"]:
            self.add(n, 2)
        self.assertEqual([self.q.dequeue().name for _ in range(3)], ["a", "b", "c"])

    def test_critical_arriving_mid_processing_jumps_queue(self):
        self.add("e1", 3)
        self.add("u1", 2)
        self.assertEqual(self.q.dequeue().name, "u1")
        self.add("c1", 1)
        self.assertEqual(self.names(), ["c1", "e1"])

    def test_peek_does_not_remove(self):
        self.add("Ana", 3)
        self.assertEqual(self.q.peek().name, "Ana")
        self.assertEqual(len(self.q), 1)

    def test_empty_queue_errors(self):
        with self.assertRaisesRegex(EmptyQueueError, "No hay pacientes"):
            self.q.dequeue()
        with self.assertRaises(EmptyQueueError):
            self.q.peek()
        self.assertEqual(self.q.list_queue(), [])

    def test_stats(self):
        for n, lvl in [("a", 1), ("b", 3), ("c", 3)]:
            self.add(n, lvl)
        self.assertEqual(self.q.stats(), {1: 1, 2: 0, 3: 2})
        self.q.dequeue()
        self.assertEqual(self.q.stats()[1], 0)

    def test_concurrent_enqueue_loses_nothing(self):
        def worker(k):
            for i in range(200):
                self.q.enqueue(Patient(f"w{k}-{i}", 1 + i % 3))

        threads = [threading.Thread(target=worker, args=(k,)) for k in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(self.q), 1600)
        self.assertEqual(len({p.name for p in self.q.list_queue()}), 1600)


class MenuTests(unittest.TestCase):
    def run_session(self, answers, queue=None):
        """Ejecuta el menú con respuestas simuladas; devuelve (cola, salida)."""
        queue = queue or TriageQueue()
        it = iter(answers)
        out = []

        def fake_input(_prompt):
            try:
                return next(it)
            except StopIteration:
                raise EOFError from None  # como input() sin más entrada

        run_menu(queue, input_fn=fake_input, print_fn=out.append)
        return queue, "\n".join(out)

    def test_full_flow(self):
        q, out = self.run_session(
            ["1", "Juan Pérez", "3", "1", "María", "1",
             "3", "4", "2", "2", "2", "5"]
        )
        self.assertEqual(len(q), 0)
        self.assertIn("Registrado: Juan Pérez", out)
        self.assertIn("1. María", out)  # María primero en la lista
        self.assertIn("Total: 2", out)
        self.assertLess(out.index("Atendiendo a: María"), out.index("Atendiendo a: Juan Pérez"))
        self.assertIn("Error: No hay pacientes en espera.", out)
        self.assertIn("Hasta luego.", out)

    def test_empty_queue_views(self):
        _, out = self.run_session(["3", "4", "5"])
        self.assertIn("La cola está vacía.", out)
        self.assertIn("Total: 0", out)

    def test_invalid_inputs_reprompt(self):
        # opción inválida, nombre vacío, nivel inválido (texto y fuera de rango)
        q, out = self.run_session(["9", "1", "  ", "Ana", "x", "7", "2", "5"])
        self.assertIn("Opción inválida", out)
        self.assertIn("El nombre no puede estar vacío.", out)
        self.assertEqual(out.count("Nivel inválido"), 2)
        self.assertEqual([(p.name, p.triage_level) for p in q.list_queue()], [("Ana", 2)])

    def test_eof_exits_cleanly(self):
        _, out = self.run_session([])  # sin entrada: EOF
        self.assertIn("Hasta luego.", out)


if __name__ == "__main__":
    unittest.main()
