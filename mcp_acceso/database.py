"""
Módulo de conexión a base de datos PostgreSQL con asyncpg
"""

import os
from contextlib import asynccontextmanager
from typing import Any, Optional

import asyncpg


class Database:
    """Clase para manejar conexiones a PostgreSQL"""

    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None
        self._database_url = os.getenv(
            "DATABASE_URL",
            os.getenv("DATABASE_URL_FALLBACK")
        )

    @property
    def database_url(self) -> str:
        """Obtiene la URL de la base de datos"""
        if not self._database_url:
            raise ValueError("DATABASE_URL o DATABASE_URL_FALLBACK no configurada")
        # Convertir de SQLAlchemy URL a asyncpg URL si es necesario
        url = self._database_url
        if url.startswith("postgresql+asyncpg://"):
            url = url.replace("postgresql+asyncpg://", "postgresql://")
        return url

    async def connect(self):
        """Establece el pool de conexiones"""
        if self.pool is None:
            self.pool = await asyncpg.create_pool(
                self.database_url,
                min_size=2,
                max_size=10,
                command_timeout=60
            )

    async def disconnect(self):
        """Cierra el pool de conexiones"""
        if self.pool:
            await self.pool.close()
            self.pool = None

    @asynccontextmanager
    async def acquire(self):
        """Context manager para adquirir una conexión del pool"""
        if self.pool is None:
            await self.connect()
        async with self.pool.acquire() as conn:
            yield conn

    async def execute(self, query: str, params: dict[str, Any]) -> list[dict]:
        """
        Ejecuta una consulta y retorna todos los resultados como lista de dicts.

        Convierte parámetros nombrados (:param) a posicionales ($1, $2, ...)
        """
        converted_query, values = self._convert_named_params(query, params)

        async with self.acquire() as conn:
            rows = await conn.fetch(converted_query, *values)
            return [dict(row) for row in rows]

    async def execute_one(self, query: str, params: dict[str, Any]) -> Optional[dict]:
        """
        Ejecuta una consulta y retorna un solo resultado.
        """
        converted_query, values = self._convert_named_params(query, params)

        async with self.acquire() as conn:
            row = await conn.fetchrow(converted_query, *values)
            return dict(row) if row else None

    def _convert_named_params(self, query: str, params: dict[str, Any]) -> tuple[str, list]:
        """
        Convierte parámetros nombrados estilo :param a estilo $N de asyncpg.
        También maneja los CAST con parámetros nombrados.
        """
        import re

        # Encontrar todos los parámetros nombrados
        pattern = r':(\w+)'
        param_names = re.findall(pattern, query)

        # Crear mapeo de nombre a posición
        seen = {}
        values = []

        for name in param_names:
            if name not in seen:
                seen[name] = len(values) + 1
                values.append(params.get(name))

        # Reemplazar :param por $N
        def replacer(match):
            name = match.group(1)
            return f"${seen[name]}"

        converted_query = re.sub(pattern, replacer, query)

        return converted_query, values


# Instancia global de la base de datos
db = Database()
