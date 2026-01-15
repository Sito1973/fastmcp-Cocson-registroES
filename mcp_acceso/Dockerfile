# Dockerfile para MCP Server de Reportes de Acceso
# Optimizado para despliegue en Easypanel

FROM python:3.11-slim

# Establecer variables de entorno
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Directorio de trabajo
WORKDIR /app

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Instalar uv para manejo moderno de dependencias
RUN pip install uv

# Copiar pyproject.toml primero para aprovechar cache de Docker
COPY pyproject.toml .

# Instalar dependencias usando uv (más rápido que pip)
RUN uv pip install --system -e .

# Copiar el código de la aplicación
COPY . .

# Puerto por defecto (configurado en Easypanel)
ENV PORT=80
EXPOSE ${PORT}

# Variables de entorno requeridas (se configuran en Easypanel)
# DATABASE_URL_FALLBACK - URL de conexión a PostgreSQL
# TIMEZONE - Zona horaria (default: America/Bogota)

# Comando para ejecutar el servidor MCP
# El servidor usa streamable-http por defecto (configurado en server.py)
CMD ["python", "server.py"]
