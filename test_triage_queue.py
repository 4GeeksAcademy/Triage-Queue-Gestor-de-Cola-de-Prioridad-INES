import threading
import unittest
from datetime import datetime, timedelta

from triage_queue import (
    EmptyQueueError,
    TriageLevel,
    TriageQueue,
    handle_command,
)


def fake_clock():
    """Reloj determinista: cada llamada avanza un minuto."""
    t = datetime(2026, 1, 1, 8, 0, 0)

    def clock():
        nonlocal t
        t += timedelta(minutes=1)
        return t

    return clock


class TriageQueueTests(unittest.TestCase):
    def setUp(self):
        self.q = TriageQueue(clock=fake_clock())

    def names(self):
        return [p.name for p in self.q.list_queue()]

    def test_enqueue_records_name_level_and_arrival(self):
        p = self.q.enqueue("Ana", 2)
        self.assertEqual(p.name, "Ana")
        self.assertEqual(p.triage_level, TriageLevel.URGENT)
        self.assertEqual(p.arrived_at, datetime(2026, 1, 1, 8, 1, 0))

    def test_priority_order(self):
        self.q.enqueue("estandar", 3)
        self.q.enqueue("urgente", 2)
        self.q.enqueue("critico", 1)
        self.assertEqual(self.names(), ["critico", "urgente", "estandar"])

    def test_fifo_within_same_level(self):
        for n in ["a", "b", "c"]:
            self.q.enqueue(n, 2)
        self.assertEqual([self.q.dequeue().name for _ in range(3)], ["a", "b", "c"])

    def test_critical_arriving_mid_processing_jumps_queue(self):
        self.q.enqueue("e1", 3)
        self.q.enqueue("u1", 2)
        self.assertEqual(self.q.dequeue().name, "u1")
        self.q.enqueue("c1", 1)
        self.assertEqual(self.names(), ["c1", "e1"])

    def test_peek_does_not_remove(self):
        self.q.enqueue("Ana", 3)
        self.assertEqual(self.q.peek().name, "Ana")
        self.assertEqual(len(self.q), 1)

    def test_empty_queue_errors(self):
        with self.assertRaises(EmptyQueueError):
            self.q.dequeue()
        with self.assertRaises(EmptyQueueError):
            self.q.peek()
        self.assertEqual(self.q.list_queue(), [])

    def test_stats(self):
        for n, lvl in [("a", 1), ("b", 3), ("c", 3)]:
            self.q.enqueue(n, lvl)
        self.assertEqual(
            self.q.stats(),
            {TriageLevel.CRITICAL: 1, TriageLevel.URGENT: 0, TriageLevel.STANDARD: 2},
        )
        self.q.dequeue()
        self.assertEqual(self.q.stats()[TriageLevel.CRITICAL], 0)

    def test_validation(self):
        for bad in (0, 4, -1, "x", None):
            with self.assertRaises(ValueError):
                self.q.enqueue("Ana", bad)
        with self.assertRaises(ValueError):
            self.q.enqueue("   ", 1)
        self.assertEqual(len(self.q), 0)

    def test_tickets_are_unique_and_increasing(self):
        tickets = [self.q.enqueue(f"p{i}", 1 + i % 3).ticket for i in range(6)]
        self.assertEqual(tickets, [1, 2, 3, 4, 5, 6])

    def test_concurrent_enqueue_loses_nothing(self):
        q = TriageQueue()

        def worker(k):
            for i in range(200):
                q.enqueue(f"w{k}-{i}", 1 + i % 3)

        threads = [threading.Thread(target=worker, args=(k,)) for k in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(q), 1600)
        tickets = [p.ticket for p in q.list_queue()]
        self.assertEqual(len(set(tickets)), 1600)


class CliTests(unittest.TestCase):
    def test_commands(self):
        q = TriageQueue()
        self.assertIn("Registrado", handle_command(q, "add 3 Juan Pérez"))
        handle_command(q, "add 1 María")
        self.assertIn("María", handle_command(q, "peek"))
        self.assertTrue(handle_command(q, "list").startswith("1. "))
        self.assertIn("Total: 2", handle_command(q, "stats"))
        self.assertIn("María", handle_command(q, "next"))
        self.assertIn("Juan Pérez", handle_command(q, "next"))
        self.assertIn("Error", handle_command(q, "next"))
        self.assertIn("Uso", handle_command(q, "add 1"))
        self.assertIn("inválido", handle_command(q, "add x Ana"))
        self.assertIn("Error", handle_command(q, "add 9 Ana"))
        self.assertIsNone(handle_command(q, "quit"))


if __name__ == "__main__":
    unittest.main()
