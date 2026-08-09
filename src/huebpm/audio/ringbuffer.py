"""Ring buffer de audio mono con marca de tiempo por muestra.

El callback de WASAPI escribe aqui y nunca hace analisis. El hilo de analisis
lee bloques con un contador monotonico de muestras, que es lo que permite
timestamps estables aunque el hilo de analisis se atrase un poco.
"""

from __future__ import annotations

import threading

import numpy as np


class RingBuffer:
    """Buffer circular de float32 mono, seguro entre dos hilos."""

    def __init__(self, capacity: int) -> None:
        self._buf = np.zeros(capacity, dtype=np.float32)
        self._capacity = capacity
        self._write_pos = 0
        self._total_written = 0
        self._lock = threading.Lock()

    @property
    def total_written(self) -> int:
        """Muestras totales escritas desde el arranque (nunca se reinicia)."""
        with self._lock:
            return self._total_written

    def write(self, data: np.ndarray) -> None:
        received = len(data)
        if received == 0:
            return
        if received >= self._capacity:
            # Bloque mas grande que el buffer: solo cabe la cola. Pero el
            # contador global tiene que avanzar por TODAS las muestras
            # recibidas, no por las que se guardan: es la referencia temporal
            # de todo el analisis, y si se queda corto los timestamps se
            # desfasan de forma permanente.
            data = data[-self._capacity :]
        n = len(data)

        with self._lock:
            end = self._write_pos + n
            if end <= self._capacity:
                self._buf[self._write_pos : end] = data
            else:
                split = self._capacity - self._write_pos
                self._buf[self._write_pos :] = data[:split]
                self._buf[: n - split] = data[split:]
            self._write_pos = end % self._capacity
            self._total_written += received

    def read_since(self, sample_index: int, max_samples: int) -> tuple[np.ndarray, int]:
        """Devuelve las muestras desde `sample_index` y el nuevo indice.

        Si el lector se atraso mas que la capacidad del buffer, se salta hacia
        adelante (se pierden muestras) en vez de devolver basura.
        """
        with self._lock:
            total = self._total_written
            oldest = max(0, total - self._capacity)
            start = max(sample_index, oldest)
            available = total - start
            if available <= 0:
                return np.empty(0, dtype=np.float32), start
            n = min(available, max_samples)

            read_pos = (self._write_pos - (total - start)) % self._capacity
            end = read_pos + n
            if end <= self._capacity:
                out = self._buf[read_pos:end].copy()
            else:
                split = self._capacity - read_pos
                out = np.concatenate((self._buf[read_pos:], self._buf[: n - split]))
            return out, start + n
