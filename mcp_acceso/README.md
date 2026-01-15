# MCP Server - Reportes de Acceso

Servidor MCP (Model Context Protocol) para consultar y generar reportes del sistema de control de acceso de empleados.

## Herramientas Disponibles

### Empleados
- `consultar_empleados` - Lista empleados con filtros por restaurante/departamento
- `buscar_empleado` - Busca por código, nombre o apellido

### Registros
- `consultar_registros_fecha` - Registros de entrada/salida de una fecha
- `consultar_registros_rango` - Registros en un rango de fechas
- `obtener_ultimo_registro` - Último registro de un empleado
- `empleados_sin_salida` - Empleados pendientes de marcar salida

### Reportes
- `calcular_horas_trabajadas_dia` - Horas trabajadas con desglose
- `reporte_horas_semanal` - Reporte semanal con alertas de exceso
- `reporte_horas_mensual` - Consolidado mensual
- `estadisticas_asistencia` - Estadísticas del período
- `obtener_configuracion` - Parámetros del sistema

### Nómina
- `resumen_nomina_quincenal` - Resumen para liquidación

## Despliegue en Easypanel

### 1. Crear el servicio

En Easypanel, crear un nuevo servicio de tipo "App" con las siguientes configuraciones:

### 2. Variables de entorno

Configurar en Easypanel:

```
DATABASE_URL_FALLBACK=postgresql+asyncpg://cocson:password@host:5432/acceso-cocson
TIMEZONE=America/Bogota
PORT=80
```

### 3. Build desde Dockerfile

Seleccionar "Build from Dockerfile" y apuntar al directorio `mcp_acceso/`.

### 4. Puerto

Exponer el puerto 80 (o el configurado en PORT).

## Ejecución Local

```bash
# Instalar dependencias con uv (recomendado)
uv pip install -e .

# O con pip tradicional
pip install -e .

# Configurar variables de entorno
export DATABASE_URL_FALLBACK="postgresql+asyncpg://user:pass@host:5432/db"
export TIMEZONE="America/Bogota"

# Ejecutar con transporte stdio (para Claude Desktop)
python -m fastmcp run server.py

# Ejecutar con transporte HTTP (para despliegue remoto)
python -m fastmcp run server.py --transport streamable-http --host 0.0.0.0 --port 80

# O usar el archivo de configuración FastMCP
fastmcp run mcp_acceso.fastmcp.json
```

## Configuración en Claude Desktop

Agregar al archivo `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "reportes-acceso": {
      "command": "python",
      "args": ["-m", "fastmcp", "run", "C:/ruta/al/mcp_acceso/server.py"],
      "env": {
        "DATABASE_URL_FALLBACK": "postgresql+asyncpg://...",
        "TIMEZONE": "America/Bogota"
      }
    }
  }
}
```

## Estructura del Proyecto

```
mcp_acceso/
├── __init__.py              # Módulo principal
├── server.py                # Servidor FastMCP con las 12 herramientas
├── database.py              # Conexión a PostgreSQL con asyncpg
├── utils.py                 # Utilidades de cálculo de horas
├── pyproject.toml           # Dependencias y metadata (estándar Python)
├── mcp_acceso.fastmcp.json  # Configuración FastMCP para despliegue
├── Dockerfile               # Para despliegue en contenedor
├── easypanel.json           # Configuración Easypanel
└── .env.example             # Variables de entorno de ejemplo
```

## Restaurantes Soportados

- Bandidos
- Sumo
- Leños y Parrilla
