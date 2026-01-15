"""
MCP Server para Reportes de Acceso - Control de Entrada/Salida de Empleados

Servidor FastMCP con 12 herramientas para consultar empleados, registros,
generar reportes de horas y resúmenes de nómina.
"""

import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastmcp import FastMCP

from database import db

# Configurar logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("mcp-acceso")

from utils import (
    LIMITE_SEMANAL,
    calcular_horas_dia,
    calcular_valor_horas,
    get_current_date,
    get_month_range,
    get_quincena_range,
    get_week_range,
)


@asynccontextmanager
async def lifespan(app: FastMCP):
    """Gestiona el ciclo de vida del servidor: conexión/desconexión de BD"""
    await db.connect()
    yield
    await db.disconnect()


# Crear servidor MCP
mcp = FastMCP(
    "mcp-reportes-acceso",
    instructions="""
    Servidor MCP para consultar y generar reportes del sistema de control de acceso.

    Funcionalidades:
    - Consultar y buscar empleados
    - Consultar registros de entrada/salida por fecha o rango
    - Calcular horas trabajadas con desglose de extras y recargos
    - Generar reportes semanales y mensuales
    - Generar resúmenes de nómina quincenal
    - Estadísticas de asistencia

    Los restaurantes disponibles son: Bandidos, Sumo, Leños y Parrilla
    """,
    lifespan=lifespan
)


# =============================================================================
# HELPER DE LOGGING PARA HERRAMIENTAS
# =============================================================================

def log_tool_call(tool_name: str, **kwargs):
    """Loguea una llamada a herramienta con todos sus argumentos"""
    logger.info("=" * 60)
    logger.info(f"TOOL CALL: {tool_name}")
    logger.info(f"ARGUMENTOS RECIBIDOS:")
    for key, value in kwargs.items():
        logger.info(f"  {key}: {value} (tipo: {type(value).__name__})")
    logger.info("=" * 60)


# =============================================================================
# HERRAMIENTAS DE EMPLEADOS
# =============================================================================

@mcp.tool(tags={"empleados"})
async def consultar_empleados(
    activos_solo: bool = True,
    restaurante: Optional[str] = None,
    departamento: Optional[str] = None,
    **kwargs
) -> dict:
    """
    Lista empleados del sistema con filtros opcionales por restaurante y departamento.

    Args:
        activos_solo: Solo empleados activos (default: True)
        restaurante: Filtrar por restaurante (Bandidos, Sumo, Leños y Parrilla)
        departamento: Filtrar por departamento

    Returns:
        Lista de empleados con sus datos
    """
    # Log para debug
    log_tool_call("consultar_empleados", activos_solo=activos_solo, restaurante=restaurante, departamento=departamento, **kwargs)
    if kwargs:
        logger.warning(f"ARGUMENTOS EXTRA IGNORADOS: {kwargs}")

    query = """
        SELECT
            id,
            codigo_empleado,
            nombre,
            apellido,
            email,
            telefono,
            departamento,
            cargo,
            liquida_dominical,
            dia_descanso,
            punto_trabajo,
            activo,
            created_at
        FROM empleados
        WHERE (CAST(:activo AS boolean) = FALSE OR activo = :activo)
          AND (CAST(:restaurante AS text) IS NULL OR punto_trabajo ILIKE ('%' || CAST(:restaurante AS text) || '%'))
          AND (CAST(:departamento AS text) IS NULL OR departamento = :departamento)
        ORDER BY apellido, nombre
    """

    params = {
        'activo': activos_solo,
        'restaurante': restaurante,
        'departamento': departamento
    }

    results = await db.execute(query, params)

    empleados = []
    for row in results:
        empleados.append({
            'id': str(row['id']),
            'codigo_empleado': row['codigo_empleado'],
            'nombre_completo': f"{row['nombre']} {row['apellido']}",
            'nombre': row['nombre'],
            'apellido': row['apellido'],
            'email': row['email'],
            'telefono': row['telefono'],
            'departamento': row['departamento'],
            'cargo': row['cargo'],
            'punto_trabajo': row['punto_trabajo'],
            'liquida_dominical': row['liquida_dominical'],
            'dia_descanso': row['dia_descanso'],
            'activo': row['activo']
        })

    return {
        'total': len(empleados),
        'filtros': {
            'activos_solo': activos_solo,
            'restaurante': restaurante,
            'departamento': departamento
        },
        'empleados': empleados
    }


@mcp.tool(tags={"empleados"})
async def buscar_empleado(termino: str, **kwargs) -> dict:
    """
    Busca empleados por código, nombre o apellido.

    Args:
        termino: Texto a buscar (código, nombre o apellido)

    Returns:
        Lista de empleados que coinciden con la búsqueda
    """
    # Log para debug
    log_tool_call("buscar_empleado", termino=termino, **kwargs)
    if kwargs:
        logger.warning(f"ARGUMENTOS EXTRA IGNORADOS: {kwargs}")

    query = """
        SELECT
            id,
            codigo_empleado,
            nombre,
            apellido,
            cargo,
            departamento,
            punto_trabajo,
            activo
        FROM empleados
        WHERE codigo_empleado ILIKE '%' || :termino || '%'
           OR nombre ILIKE '%' || :termino || '%'
           OR apellido ILIKE '%' || :termino || '%'
        ORDER BY
            CASE WHEN codigo_empleado ILIKE :termino THEN 0 ELSE 1 END,
            apellido, nombre
        LIMIT 20
    """

    results = await db.execute(query, {'termino': termino})

    empleados = []
    for row in results:
        empleados.append({
            'id': str(row['id']),
            'codigo_empleado': row['codigo_empleado'],
            'nombre_completo': f"{row['nombre']} {row['apellido']}",
            'cargo': row['cargo'],
            'departamento': row['departamento'],
            'punto_trabajo': row['punto_trabajo'],
            'activo': row['activo']
        })

    return {
        'termino_busqueda': termino,
        'resultados': len(empleados),
        'empleados': empleados
    }


# =============================================================================
# HERRAMIENTAS DE REGISTROS
# =============================================================================

@mcp.tool(tags={"registros"})
async def consultar_registros_fecha(
    fecha: str,
    empleado_id: Optional[str] = None,
    restaurante: Optional[str] = None,
    tipo: Optional[str] = None
) -> dict:
    """
    Consulta registros de entrada/salida de una fecha específica.

    Args:
        fecha: Fecha en formato YYYY-MM-DD
        empleado_id: UUID del empleado (opcional)
        restaurante: Filtrar por restaurante (opcional)
        tipo: Tipo de registro: ENTRADA o SALIDA (opcional)

    Returns:
        Lista de registros con datos del empleado
    """
    query = """
        SELECT
            r.id,
            r.empleado_id,
            e.codigo_empleado,
            e.nombre || ' ' || e.apellido AS empleado_nombre,
            e.cargo,
            e.departamento,
            r.tipo_registro,
            r.punto_trabajo,
            r.fecha_registro,
            r.hora_registro,
            r.timestamp_registro,
            r.confianza_reconocimiento,
            r.observaciones
        FROM registros r
        JOIN empleados e ON r.empleado_id = e.id
        WHERE r.fecha_registro = :fecha
          AND (CAST(:empleado_id AS uuid) IS NULL OR r.empleado_id = CAST(:empleado_id AS uuid))
          AND (CAST(:restaurante AS text) IS NULL OR r.punto_trabajo ILIKE ('%' || CAST(:restaurante AS text) || '%'))
          AND (CAST(:tipo AS text) IS NULL OR r.tipo_registro = :tipo)
        ORDER BY r.hora_registro
    """

    params = {
        'fecha': datetime.strptime(fecha, '%Y-%m-%d').date(),
        'empleado_id': empleado_id,
        'restaurante': restaurante,
        'tipo': tipo
    }

    results = await db.execute(query, params)

    registros = []
    for row in results:
        registros.append({
            'id': str(row['id']),
            'empleado_id': str(row['empleado_id']),
            'codigo_empleado': row['codigo_empleado'],
            'empleado_nombre': row['empleado_nombre'],
            'cargo': row['cargo'],
            'departamento': row['departamento'],
            'tipo_registro': row['tipo_registro'],
            'punto_trabajo': row['punto_trabajo'],
            'fecha_registro': str(row['fecha_registro']),
            'hora_registro': str(row['hora_registro']),
            'confianza': float(row['confianza_reconocimiento']) if row['confianza_reconocimiento'] else None,
            'observaciones': row['observaciones']
        })

    return {
        'fecha': fecha,
        'filtros': {
            'empleado_id': empleado_id,
            'restaurante': restaurante,
            'tipo': tipo
        },
        'total_registros': len(registros),
        'registros': registros
    }


@mcp.tool(tags={"registros"})
async def consultar_registros_rango(
    fecha_inicio: str,
    fecha_fin: str,
    empleado_id: Optional[str] = None,
    restaurante: Optional[str] = None
) -> dict:
    """
    Consulta registros en un rango de fechas.

    Args:
        fecha_inicio: Fecha inicio YYYY-MM-DD
        fecha_fin: Fecha fin YYYY-MM-DD
        empleado_id: UUID del empleado (opcional)
        restaurante: Filtrar por restaurante (opcional)

    Returns:
        Lista de registros ordenados por fecha y hora
    """
    query = """
        SELECT
            r.id,
            r.empleado_id,
            e.codigo_empleado,
            e.nombre || ' ' || e.apellido AS empleado_nombre,
            r.tipo_registro,
            r.punto_trabajo,
            r.fecha_registro,
            r.hora_registro,
            r.observaciones
        FROM registros r
        JOIN empleados e ON r.empleado_id = e.id
        WHERE r.fecha_registro BETWEEN :fecha_inicio AND :fecha_fin
          AND (CAST(:empleado_id AS uuid) IS NULL OR r.empleado_id = CAST(:empleado_id AS uuid))
          AND (CAST(:restaurante AS text) IS NULL OR r.punto_trabajo ILIKE ('%' || CAST(:restaurante AS text) || '%'))
        ORDER BY r.fecha_registro, r.hora_registro
    """

    params = {
        'fecha_inicio': datetime.strptime(fecha_inicio, '%Y-%m-%d').date(),
        'fecha_fin': datetime.strptime(fecha_fin, '%Y-%m-%d').date(),
        'empleado_id': empleado_id,
        'restaurante': restaurante
    }

    results = await db.execute(query, params)

    registros = []
    for row in results:
        registros.append({
            'id': str(row['id']),
            'empleado_id': str(row['empleado_id']),
            'codigo_empleado': row['codigo_empleado'],
            'empleado_nombre': row['empleado_nombre'],
            'tipo_registro': row['tipo_registro'],
            'punto_trabajo': row['punto_trabajo'],
            'fecha_registro': str(row['fecha_registro']),
            'hora_registro': str(row['hora_registro']),
            'observaciones': row['observaciones']
        })

    return {
        'periodo': {
            'inicio': fecha_inicio,
            'fin': fecha_fin
        },
        'filtros': {
            'empleado_id': empleado_id,
            'restaurante': restaurante
        },
        'total_registros': len(registros),
        'registros': registros
    }


@mcp.tool(tags={"registros"})
async def obtener_ultimo_registro(empleado_id: str) -> dict:
    """
    Obtiene el último registro de un empleado para saber si debe marcar entrada o salida.

    Args:
        empleado_id: UUID del empleado

    Returns:
        Último registro y siguiente acción esperada (ENTRADA o SALIDA)
    """
    query = """
        SELECT
            r.tipo_registro,
            r.fecha_registro,
            r.hora_registro,
            r.punto_trabajo,
            e.nombre || ' ' || e.apellido AS empleado_nombre
        FROM registros r
        JOIN empleados e ON r.empleado_id = e.id
        WHERE r.empleado_id = CAST(:empleado_id AS uuid)
        ORDER BY r.fecha_registro DESC, r.hora_registro DESC
        LIMIT 1
    """

    result = await db.execute_one(query, {'empleado_id': empleado_id})

    if result:
        siguiente_accion = 'SALIDA' if result['tipo_registro'] == 'ENTRADA' else 'ENTRADA'
        return {
            'empleado_id': empleado_id,
            'empleado_nombre': result['empleado_nombre'],
            'ultimo_registro': {
                'tipo': result['tipo_registro'],
                'fecha': str(result['fecha_registro']),
                'hora': str(result['hora_registro']),
                'punto_trabajo': result['punto_trabajo']
            },
            'siguiente_accion': siguiente_accion
        }
    else:
        return {
            'empleado_id': empleado_id,
            'empleado_nombre': None,
            'ultimo_registro': None,
            'siguiente_accion': 'ENTRADA',
            'mensaje': 'No hay registros para este empleado'
        }


@mcp.tool(tags={"registros"})
async def empleados_sin_salida(fecha: Optional[str] = None) -> dict:
    """
    Lista empleados con entrada pero sin salida registrada en una fecha.

    Args:
        fecha: Fecha YYYY-MM-DD (default: hoy)

    Returns:
        Lista de empleados pendientes de marcar salida
    """
    if fecha is None:
        fecha = str(get_current_date())

    query = """
        WITH entradas AS (
            SELECT
                empleado_id,
                MIN(hora_registro) AS primera_entrada,
                punto_trabajo
            FROM registros
            WHERE fecha_registro = :fecha
              AND tipo_registro = 'ENTRADA'
            GROUP BY empleado_id, punto_trabajo
        ),
        salidas AS (
            SELECT DISTINCT empleado_id
            FROM registros
            WHERE fecha_registro = :fecha
              AND tipo_registro = 'SALIDA'
        )
        SELECT
            e.id AS empleado_id,
            e.codigo_empleado,
            e.nombre || ' ' || e.apellido AS empleado_nombre,
            en.primera_entrada AS hora_entrada,
            en.punto_trabajo,
            EXTRACT(EPOCH FROM (NOW() - (CAST(:fecha AS date) + en.primera_entrada))) / 3600 AS horas_transcurridas
        FROM entradas en
        JOIN empleados e ON en.empleado_id = e.id
        LEFT JOIN salidas s ON en.empleado_id = s.empleado_id
        WHERE s.empleado_id IS NULL
        ORDER BY en.primera_entrada
    """

    results = await db.execute(query, {'fecha': fecha})

    empleados = []
    for row in results:
        empleados.append({
            'empleado_id': str(row['empleado_id']),
            'codigo_empleado': row['codigo_empleado'],
            'empleado_nombre': row['empleado_nombre'],
            'hora_entrada': str(row['hora_entrada']),
            'punto_trabajo': row['punto_trabajo'],
            'horas_transcurridas': round(float(row['horas_transcurridas']), 2) if row['horas_transcurridas'] else 0
        })

    return {
        'fecha': fecha,
        'total_sin_salida': len(empleados),
        'empleados': empleados
    }


# =============================================================================
# HERRAMIENTAS DE REPORTES
# =============================================================================

@mcp.tool(tags={"reportes"})
async def calcular_horas_trabajadas_dia(empleado_id: str, fecha: str) -> dict:
    """
    Calcula horas trabajadas de un empleado en un día específico con desglose de extras y recargos.

    Args:
        empleado_id: UUID del empleado
        fecha: Fecha YYYY-MM-DD

    Returns:
        Desglose completo de horas trabajadas
    """
    # Obtener datos del empleado
    empleado_query = """
        SELECT nombre || ' ' || apellido AS nombre, liquida_dominical
        FROM empleados WHERE id = CAST(:empleado_id AS uuid)
    """
    empleado = await db.execute_one(empleado_query, {'empleado_id': empleado_id})

    if not empleado:
        return {'error': f'Empleado {empleado_id} no encontrado'}

    # Obtener registros del día
    registros_query = """
        SELECT
            tipo_registro,
            hora_registro,
            observaciones
        FROM registros
        WHERE empleado_id = CAST(:empleado_id AS uuid)
          AND fecha_registro = :fecha
        ORDER BY hora_registro
    """

    registros = await db.execute(registros_query, {
        'empleado_id': empleado_id,
        'fecha': datetime.strptime(fecha, '%Y-%m-%d').date()
    })

    if not registros:
        return {
            'empleado_id': empleado_id,
            'empleado_nombre': empleado['nombre'],
            'fecha': fecha,
            'mensaje': 'No hay registros para esta fecha',
            'horas_trabajadas': 0
        }

    # Calcular horas
    fecha_obj = datetime.strptime(fecha, '%Y-%m-%d').date()
    resultado = calcular_horas_dia(registros, fecha_obj)

    # Agregar info del empleado
    resultado['empleado_id'] = empleado_id
    resultado['empleado_nombre'] = empleado['nombre']
    resultado['liquida_dominical'] = empleado['liquida_dominical']

    # Agregar registros crudos para referencia
    resultado['registros'] = [
        {'tipo': r['tipo_registro'], 'hora': str(r['hora_registro']), 'obs': r['observaciones']}
        for r in registros
    ]

    return resultado


@mcp.tool(tags={"reportes"})
async def reporte_horas_semanal(
    empleado_id: Optional[str] = None,
    fecha_semana: Optional[str] = None,
    restaurante: Optional[str] = None
) -> dict:
    """
    Genera reporte semanal de horas trabajadas por empleado con alertas de exceso (>48h).

    Args:
        empleado_id: UUID del empleado (opcional, todos si no se especifica)
        fecha_semana: Cualquier fecha de la semana YYYY-MM-DD (default: semana actual)
        restaurante: Filtrar por restaurante (opcional)

    Returns:
        Reporte semanal con totales y alertas
    """
    # Determinar rango de la semana
    if fecha_semana:
        fecha_ref = datetime.strptime(fecha_semana, '%Y-%m-%d').date()
    else:
        fecha_ref = get_current_date()

    inicio_semana, fin_semana = get_week_range(fecha_ref)

    # Obtener registros de la semana
    query = """
        SELECT
            r.empleado_id,
            e.codigo_empleado,
            e.nombre || ' ' || e.apellido AS empleado_nombre,
            e.liquida_dominical,
            e.dia_descanso,
            r.fecha_registro,
            r.tipo_registro,
            r.hora_registro,
            r.observaciones,
            EXTRACT(DOW FROM r.fecha_registro) AS dia_semana
        FROM registros r
        JOIN empleados e ON r.empleado_id = e.id
        WHERE r.fecha_registro BETWEEN :inicio AND :fin
          AND (CAST(:empleado_id AS uuid) IS NULL OR r.empleado_id = CAST(:empleado_id AS uuid))
          AND (CAST(:restaurante AS text) IS NULL OR r.punto_trabajo ILIKE ('%' || CAST(:restaurante AS text) || '%'))
          AND e.activo = TRUE
        ORDER BY e.apellido, e.nombre, r.fecha_registro, r.hora_registro
    """

    results = await db.execute(query, {
        'inicio': inicio_semana,
        'fin': fin_semana,
        'empleado_id': empleado_id,
        'restaurante': restaurante
    })

    # Agrupar por empleado
    empleados_data = {}
    for row in results:
        emp_id = str(row['empleado_id'])
        if emp_id not in empleados_data:
            empleados_data[emp_id] = {
                'empleado_id': emp_id,
                'codigo': row['codigo_empleado'],
                'nombre': row['empleado_nombre'],
                'liquida_dominical': row['liquida_dominical'] if row['liquida_dominical'] is not None else False,
                'registros_por_fecha': {}
            }

        fecha = str(row['fecha_registro'])
        if fecha not in empleados_data[emp_id]['registros_por_fecha']:
            empleados_data[emp_id]['registros_por_fecha'][fecha] = []

        empleados_data[emp_id]['registros_por_fecha'][fecha].append({
            'tipo_registro': row['tipo_registro'],
            'hora_registro': row['hora_registro']
        })

    # Calcular horas por empleado
    reportes = []
    for emp_id, data in empleados_data.items():
        dias = []
        totales = {
            'horas_trabajadas': 0,
            'horas_ordinarias': 0,
            'horas_extra_diurna': 0,
            'horas_extra_nocturna': 0,
            'horas_recargo_nocturno': 0,
            'horas_dominical': 0
        }

        for fecha_str, registros in data['registros_por_fecha'].items():
            fecha_obj = datetime.strptime(fecha_str, '%Y-%m-%d').date()
            horas_dia = calcular_horas_dia(registros, fecha_obj)
            horas_dia['fecha'] = fecha_str
            dias.append(horas_dia)

            for key in totales:
                totales[key] += horas_dia.get(key, 0)

        # Redondear totales
        for key in totales:
            totales[key] = round(totales[key], 2)

        # Verificar exceso de horas
        alerta_exceso = totales['horas_trabajadas'] > LIMITE_SEMANAL
        horas_exceso = max(0, totales['horas_trabajadas'] - LIMITE_SEMANAL)

        reportes.append({
            'empleado_id': emp_id,
            'codigo': data['codigo'],
            'nombre': data['nombre'],
            'semana_inicio': str(inicio_semana),
            'semana_fin': str(fin_semana),
            'dias': dias,
            'totales': totales,
            'alerta_exceso': alerta_exceso,
            'horas_exceso': round(horas_exceso, 2)
        })

    return {
        'semana': {
            'inicio': str(inicio_semana),
            'fin': str(fin_semana)
        },
        'filtros': {
            'empleado_id': empleado_id,
            'restaurante': restaurante
        },
        'total_empleados': len(reportes),
        'reportes': reportes
    }


@mcp.tool(tags={"reportes"})
async def reporte_horas_mensual(
    anio: int,
    mes: int,
    empleado_id: Optional[str] = None,
    restaurante: Optional[str] = None
) -> dict:
    """
    Genera reporte mensual consolidado de horas y valores por empleado.

    Args:
        anio: Año (ej: 2024)
        mes: Mes (1-12)
        empleado_id: UUID del empleado (opcional)
        restaurante: Filtrar por restaurante (opcional)

    Returns:
        Reporte mensual consolidado
    """
    inicio_mes, fin_mes = get_month_range(anio, mes)

    meses = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
             "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
    periodo = f"{meses[mes]} {anio}"

    query = """
        SELECT
            r.empleado_id,
            e.codigo_empleado,
            e.nombre,
            e.apellido,
            e.cargo,
            e.departamento,
            e.liquida_dominical,
            r.fecha_registro,
            r.tipo_registro,
            r.hora_registro,
            r.observaciones,
            EXTRACT(DOW FROM r.fecha_registro) AS dia_semana,
            EXTRACT(WEEK FROM r.fecha_registro) AS semana_num
        FROM registros r
        JOIN empleados e ON r.empleado_id = e.id
        WHERE EXTRACT(YEAR FROM r.fecha_registro) = :anio
          AND EXTRACT(MONTH FROM r.fecha_registro) = :mes
          AND (CAST(:empleado_id AS uuid) IS NULL OR r.empleado_id = CAST(:empleado_id AS uuid))
          AND (CAST(:restaurante AS text) IS NULL OR r.punto_trabajo ILIKE ('%' || CAST(:restaurante AS text) || '%'))
          AND e.activo = TRUE
        ORDER BY e.apellido, e.nombre, r.fecha_registro, r.hora_registro
    """

    results = await db.execute(query, {
        'anio': anio,
        'mes': mes,
        'empleado_id': empleado_id,
        'restaurante': restaurante
    })

    # Agrupar por empleado
    empleados_data = {}
    for row in results:
        emp_id = str(row['empleado_id'])
        if emp_id not in empleados_data:
            empleados_data[emp_id] = {
                'empleado_id': emp_id,
                'codigo': row['codigo_empleado'],
                'nombre': f"{row['nombre']} {row['apellido']}",
                'cargo': row['cargo'],
                'departamento': row['departamento'],
                'liquida_dominical': row['liquida_dominical'],
                'registros_por_fecha': {}
            }

        fecha = str(row['fecha_registro'])
        if fecha not in empleados_data[emp_id]['registros_por_fecha']:
            empleados_data[emp_id]['registros_por_fecha'][fecha] = []

        empleados_data[emp_id]['registros_por_fecha'][fecha].append({
            'tipo_registro': row['tipo_registro'],
            'hora_registro': row['hora_registro']
        })

    # Calcular por empleado
    reportes = []
    for emp_id, data in empleados_data.items():
        resumen = {
            'dias_trabajados': len(data['registros_por_fecha']),
            'total_horas': 0,
            'horas_ordinarias': 0,
            'horas_extra_diurna': 0,
            'horas_extra_nocturna': 0,
            'recargo_nocturno': 0,
            'horas_dominical': 0
        }

        for fecha_str, registros in data['registros_por_fecha'].items():
            fecha_obj = datetime.strptime(fecha_str, '%Y-%m-%d').date()
            horas_dia = calcular_horas_dia(registros, fecha_obj)

            resumen['total_horas'] += horas_dia['horas_trabajadas']
            resumen['horas_ordinarias'] += horas_dia['horas_ordinarias']
            resumen['horas_extra_diurna'] += horas_dia['horas_extra_diurna']
            resumen['horas_extra_nocturna'] += horas_dia['horas_extra_nocturna']
            resumen['recargo_nocturno'] += horas_dia['horas_recargo_nocturno']
            resumen['horas_dominical'] += horas_dia['horas_dominical']

        # Redondear
        for key in resumen:
            if key != 'dias_trabajados':
                resumen[key] = round(resumen[key], 2)

        reportes.append({
            'empleado_id': emp_id,
            'codigo': data['codigo'],
            'nombre': data['nombre'],
            'cargo': data['cargo'],
            'departamento': data['departamento'],
            'periodo': periodo,
            'resumen': resumen
        })

    return {
        'periodo': periodo,
        'rango': {
            'inicio': str(inicio_mes),
            'fin': str(fin_mes)
        },
        'filtros': {
            'empleado_id': empleado_id,
            'restaurante': restaurante
        },
        'total_empleados': len(reportes),
        'reportes': reportes
    }


@mcp.tool(tags={"reportes"})
async def estadisticas_asistencia(
    fecha_inicio: str,
    fecha_fin: str,
    restaurante: Optional[str] = None
) -> dict:
    """
    Genera estadísticas generales de asistencia para un período.

    Args:
        fecha_inicio: Fecha inicio YYYY-MM-DD
        fecha_fin: Fecha fin YYYY-MM-DD
        restaurante: Filtrar por restaurante (opcional)

    Returns:
        Estadísticas consolidadas del período
    """
    query = """
        SELECT
            COUNT(*) AS total_registros,
            COUNT(DISTINCT empleado_id) AS empleados_unicos,
            COUNT(*) FILTER (WHERE tipo_registro = 'ENTRADA') AS entradas,
            COUNT(*) FILTER (WHERE tipo_registro = 'SALIDA') AS salidas,
            COUNT(*) FILTER (WHERE observaciones LIKE '%FORZADO%') AS forzados,
            punto_trabajo
        FROM registros
        WHERE fecha_registro BETWEEN :fecha_inicio AND :fecha_fin
          AND (CAST(:restaurante AS text) IS NULL OR punto_trabajo ILIKE ('%' || CAST(:restaurante AS text) || '%'))
        GROUP BY punto_trabajo
    """

    results = await db.execute(query, {
        'fecha_inicio': datetime.strptime(fecha_inicio, '%Y-%m-%d').date(),
        'fecha_fin': datetime.strptime(fecha_fin, '%Y-%m-%d').date(),
        'restaurante': restaurante
    })

    totales = {
        'total_registros': 0,
        'empleados_unicos': 0,
        'entradas': 0,
        'salidas': 0,
        'registros_forzados': 0
    }

    por_restaurante = []
    for row in results:
        totales['total_registros'] += row['total_registros']
        totales['entradas'] += row['entradas']
        totales['salidas'] += row['salidas']
        totales['registros_forzados'] += row['forzados']

        por_restaurante.append({
            'restaurante': row['punto_trabajo'],
            'registros': row['total_registros'],
            'empleados': row['empleados_unicos']
        })

    # Obtener empleados únicos totales
    query_empleados = """
        SELECT COUNT(DISTINCT empleado_id) AS total
        FROM registros
        WHERE fecha_registro BETWEEN :fecha_inicio AND :fecha_fin
          AND (CAST(:restaurante AS text) IS NULL OR punto_trabajo ILIKE ('%' || CAST(:restaurante AS text) || '%'))
    """
    emp_result = await db.execute_one(query_empleados, {
        'fecha_inicio': datetime.strptime(fecha_inicio, '%Y-%m-%d').date(),
        'fecha_fin': datetime.strptime(fecha_fin, '%Y-%m-%d').date(),
        'restaurante': restaurante
    })
    totales['empleados_unicos'] = emp_result['total'] if emp_result else 0

    return {
        'periodo': {
            'inicio': fecha_inicio,
            'fin': fecha_fin
        },
        'totales': totales,
        'por_restaurante': por_restaurante
    }


@mcp.tool(tags={"reportes"})
async def obtener_configuracion(clave: Optional[str] = None) -> dict:
    """
    Obtiene configuraciones del sistema para cálculos de nómina (valores hora, límites, etc).

    Args:
        clave: Nombre de la configuración (opcional, todas si no se especifica)

    Returns:
        Configuración o lista de configuraciones
    """
    query = """
        SELECT clave, valor, descripcion, tipo_dato
        FROM configuracion
        WHERE (CAST(:clave AS text) IS NULL OR clave = :clave)
        ORDER BY clave
    """

    results = await db.execute(query, {'clave': clave})

    if clave and results:
        row = results[0]
        return {
            'clave': row['clave'],
            'valor': row['valor'],
            'descripcion': row['descripcion'],
            'tipo_dato': row['tipo_dato']
        }

    configuraciones = []
    for row in results:
        configuraciones.append({
            'clave': row['clave'],
            'valor': row['valor'],
            'descripcion': row['descripcion'],
            'tipo_dato': row['tipo_dato']
        })

    return {
        'total': len(configuraciones),
        'configuraciones': configuraciones
    }


# =============================================================================
# HERRAMIENTAS DE NÓMINA
# =============================================================================

@mcp.tool(tags={"nomina"})
async def resumen_nomina_quincenal(
    anio: int,
    mes: int,
    quincena: int,
    restaurante: Optional[str] = None
) -> dict:
    """
    Genera resumen para liquidación de nómina quincenal con horas y valores.

    Args:
        anio: Año
        mes: Mes (1-12)
        quincena: 1 (días 1-15) o 2 (días 16-fin de mes)
        restaurante: Filtrar por restaurante (opcional)

    Returns:
        Resumen de nómina por empleado con valores calculados
    """
    inicio, fin = get_quincena_range(anio, mes, quincena)

    meses = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
             "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
    periodo = f"Quincena {quincena} - {meses[mes]} {anio}"

    # Obtener configuración de valores
    config_query = """
        SELECT clave, valor FROM configuracion
        WHERE clave IN ('valor_hora_ordinaria', 'valor_hora_extra_diurna', 'valor_hora_extra_nocturna')
    """
    config_results = await db.execute(config_query, {})
    config = {row['clave']: row['valor'] for row in config_results}

    # Obtener registros de la quincena
    query = """
        SELECT
            r.empleado_id,
            e.codigo_empleado,
            e.nombre || ' ' || e.apellido AS nombre,
            e.cargo,
            e.departamento,
            e.liquida_dominical,
            r.fecha_registro,
            r.tipo_registro,
            r.hora_registro,
            r.observaciones
        FROM registros r
        JOIN empleados e ON r.empleado_id = e.id
        WHERE r.fecha_registro BETWEEN :inicio AND :fin
          AND (CAST(:restaurante AS text) IS NULL OR r.punto_trabajo ILIKE ('%' || CAST(:restaurante AS text) || '%'))
          AND e.activo = TRUE
        ORDER BY e.apellido, e.nombre, r.fecha_registro, r.hora_registro
    """

    results = await db.execute(query, {
        'inicio': inicio,
        'fin': fin,
        'restaurante': restaurante
    })

    # Agrupar por empleado
    empleados_data = {}
    for row in results:
        emp_id = str(row['empleado_id'])
        if emp_id not in empleados_data:
            empleados_data[emp_id] = {
                'empleado_id': emp_id,
                'codigo': row['codigo_empleado'],
                'nombre': row['nombre'],
                'cargo': row['cargo'],
                'departamento': row['departamento'],
                'liquida_dominical': row['liquida_dominical'],
                'registros_por_fecha': {}
            }

        fecha = str(row['fecha_registro'])
        if fecha not in empleados_data[emp_id]['registros_por_fecha']:
            empleados_data[emp_id]['registros_por_fecha'][fecha] = []

        empleados_data[emp_id]['registros_por_fecha'][fecha].append({
            'tipo_registro': row['tipo_registro'],
            'hora_registro': row['hora_registro']
        })

    # Calcular por empleado
    reportes = []
    for emp_id, data in empleados_data.items():
        horas = {
            'ordinarias': 0,
            'extra_diurna': 0,
            'extra_nocturna': 0,
            'recargo_nocturno': 0,
            'dominical': 0
        }

        detalle_dias = []

        for fecha_str, registros in data['registros_por_fecha'].items():
            fecha_obj = datetime.strptime(fecha_str, '%Y-%m-%d').date()
            horas_dia = calcular_horas_dia(registros, fecha_obj)

            horas['ordinarias'] += horas_dia['horas_ordinarias']
            horas['extra_diurna'] += horas_dia['horas_extra_diurna']
            horas['extra_nocturna'] += horas_dia['horas_extra_nocturna']
            horas['recargo_nocturno'] += horas_dia['horas_recargo_nocturno']

            if data['liquida_dominical']:
                horas['dominical'] += horas_dia['horas_dominical']

            # Detalle del día
            if horas_dia['intervalos']:
                detalle_dias.append({
                    'fecha': fecha_str,
                    'entrada': horas_dia['intervalos'][0]['entrada'] if horas_dia['intervalos'] else None,
                    'salida': horas_dia['intervalos'][-1]['salida'] if horas_dia['intervalos'] else None,
                    'horas': horas_dia['horas_trabajadas']
                })

        # Redondear horas
        for key in horas:
            horas[key] = round(horas[key], 2)

        # Calcular valores monetarios
        horas_para_calculo = {
            'horas_ordinarias': horas['ordinarias'],
            'horas_extra_diurna': horas['extra_diurna'],
            'horas_extra_nocturna': horas['extra_nocturna'],
            'horas_recargo_nocturno': horas['recargo_nocturno'],
            'horas_dominical': horas['dominical'],
        }
        valores = calcular_valor_horas(horas_para_calculo, config)

        reportes.append({
            'empleado_id': emp_id,
            'codigo': data['codigo'],
            'nombre': data['nombre'],
            'cargo': data['cargo'],
            'departamento': data['departamento'],
            'dias_trabajados': len(data['registros_por_fecha']),
            'horas': horas,
            'valores': valores,
            'detalle_dias': detalle_dias
        })

    return {
        'periodo': periodo,
        'quincena': quincena,
        'rango': {
            'inicio': str(inicio),
            'fin': str(fin)
        },
        'filtros': {
            'restaurante': restaurante
        },
        'total_empleados': len(reportes),
        'reportes': reportes
    }


# Punto de entrada
if __name__ == "__main__":
    import os
    # Usar streamable-http para despliegue, stdio para desarrollo local
    transport = os.getenv("MCP_TRANSPORT", "streamable-http")
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "80"))

    mcp.run(transport=transport, host=host, port=port)
