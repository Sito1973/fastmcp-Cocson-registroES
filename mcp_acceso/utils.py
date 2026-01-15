"""
Utilidades para cálculo de horas trabajadas, rangos de fechas y valores de nómina
"""

import os
from datetime import date, datetime, time, timedelta
from typing import Any

import pytz

# Configuración de zona horaria
TIMEZONE = pytz.timezone(os.getenv("TIMEZONE", "America/Bogota"))

# Constantes para cálculo de horas
HORA_INICIO_NOCTURNO = time(21, 0)  # 9 PM
HORA_FIN_NOCTURNO = time(6, 0)      # 6 AM
HORAS_ORDINARIAS_DIA = 8
LIMITE_SEMANAL = 48


def get_current_date() -> date:
    """Obtiene la fecha actual en la zona horaria configurada"""
    return datetime.now(TIMEZONE).date()


def get_current_datetime() -> datetime:
    """Obtiene la fecha y hora actual en la zona horaria configurada"""
    return datetime.now(TIMEZONE)


def get_week_range(fecha: date) -> tuple[date, date]:
    """
    Obtiene el rango de la semana (lunes a domingo) para una fecha dada.
    """
    # Lunes = 0, Domingo = 6
    inicio = fecha - timedelta(days=fecha.weekday())
    fin = inicio + timedelta(days=6)
    return inicio, fin


def get_month_range(anio: int, mes: int) -> tuple[date, date]:
    """
    Obtiene el rango del mes (primer y último día).
    """
    inicio = date(anio, mes, 1)
    if mes == 12:
        fin = date(anio + 1, 1, 1) - timedelta(days=1)
    else:
        fin = date(anio, mes + 1, 1) - timedelta(days=1)
    return inicio, fin


def get_quincena_range(anio: int, mes: int, quincena: int) -> tuple[date, date]:
    """
    Obtiene el rango de la quincena.
    Quincena 1: días 1-15
    Quincena 2: días 16-fin de mes
    """
    if quincena == 1:
        inicio = date(anio, mes, 1)
        fin = date(anio, mes, 15)
    else:
        inicio = date(anio, mes, 16)
        _, fin = get_month_range(anio, mes)
    return inicio, fin


def es_hora_nocturna(hora: time) -> bool:
    """
    Determina si una hora está en horario nocturno (9 PM - 6 AM).
    """
    return hora >= HORA_INICIO_NOCTURNO or hora < HORA_FIN_NOCTURNO


def es_domingo(fecha: date) -> bool:
    """
    Determina si una fecha es domingo.
    """
    return fecha.weekday() == 6


def calcular_horas_dia(registros: list[dict], fecha: date) -> dict[str, Any]:
    """
    Calcula las horas trabajadas de un día con desglose de tipos de horas.

    Args:
        registros: Lista de registros con tipo_registro y hora_registro
        fecha: Fecha del día

    Returns:
        Diccionario con desglose de horas
    """
    resultado = {
        'fecha': str(fecha),
        'horas_trabajadas': 0,
        'horas_ordinarias': 0,
        'horas_extra_diurna': 0,
        'horas_extra_nocturna': 0,
        'horas_recargo_nocturno': 0,
        'horas_dominical': 0,
        'es_domingo': es_domingo(fecha),
        'intervalos': []
    }

    if not registros:
        return resultado

    # Emparejar entradas con salidas
    entradas = []
    salidas = []

    for reg in registros:
        tipo = reg.get('tipo_registro', reg.get('tipo', ''))
        hora = reg.get('hora_registro', reg.get('hora'))

        # Convertir hora si es string
        if isinstance(hora, str):
            hora = datetime.strptime(hora, '%H:%M:%S').time()

        if tipo == 'ENTRADA':
            entradas.append(hora)
        elif tipo == 'SALIDA':
            salidas.append(hora)

    # Emparejar entrada-salida
    intervalos = []
    for i, entrada in enumerate(entradas):
        if i < len(salidas):
            salida = salidas[i]
            intervalos.append({
                'entrada': str(entrada),
                'salida': str(salida)
            })

            # Calcular horas del intervalo
            entrada_dt = datetime.combine(fecha, entrada)
            salida_dt = datetime.combine(fecha, salida)

            # Si la salida es antes de la entrada, asumimos que cruzó medianoche
            if salida_dt < entrada_dt:
                salida_dt += timedelta(days=1)

            horas = (salida_dt - entrada_dt).total_seconds() / 3600
            resultado['horas_trabajadas'] += horas

            # Clasificar las horas
            horas_clasificadas = clasificar_horas(entrada, salida, fecha, horas)
            resultado['horas_ordinarias'] += horas_clasificadas['ordinarias']
            resultado['horas_extra_diurna'] += horas_clasificadas['extra_diurna']
            resultado['horas_extra_nocturna'] += horas_clasificadas['extra_nocturna']
            resultado['horas_recargo_nocturno'] += horas_clasificadas['recargo_nocturno']
            resultado['horas_dominical'] += horas_clasificadas['dominical']

    resultado['intervalos'] = intervalos

    # Redondear valores
    for key in ['horas_trabajadas', 'horas_ordinarias', 'horas_extra_diurna',
                'horas_extra_nocturna', 'horas_recargo_nocturno', 'horas_dominical']:
        resultado[key] = round(resultado[key], 2)

    return resultado


def clasificar_horas(entrada: time, salida: time, fecha: date, total_horas: float) -> dict[str, float]:
    """
    Clasifica las horas trabajadas en diferentes tipos.
    """
    clasificacion = {
        'ordinarias': 0,
        'extra_diurna': 0,
        'extra_nocturna': 0,
        'recargo_nocturno': 0,
        'dominical': 0
    }

    # Si es domingo y liquida dominical
    if es_domingo(fecha):
        clasificacion['dominical'] = total_horas
        return clasificacion

    # Calcular horas nocturnas
    horas_nocturnas = calcular_horas_nocturnas(entrada, salida, fecha)
    horas_diurnas = total_horas - horas_nocturnas

    # Horas ordinarias (máximo 8)
    if total_horas <= HORAS_ORDINARIAS_DIA:
        clasificacion['ordinarias'] = horas_diurnas
        clasificacion['recargo_nocturno'] = horas_nocturnas
    else:
        # Hay horas extras
        clasificacion['ordinarias'] = min(horas_diurnas, HORAS_ORDINARIAS_DIA)

        horas_extra_total = total_horas - HORAS_ORDINARIAS_DIA
        if horas_extra_total > 0:
            # Distribuir extras entre diurnas y nocturnas
            proporcion_nocturna = horas_nocturnas / total_horas if total_horas > 0 else 0
            clasificacion['extra_nocturna'] = horas_extra_total * proporcion_nocturna
            clasificacion['extra_diurna'] = horas_extra_total * (1 - proporcion_nocturna)
            clasificacion['recargo_nocturno'] = horas_nocturnas - clasificacion['extra_nocturna']

    return clasificacion


def calcular_horas_nocturnas(entrada: time, salida: time, fecha: date) -> float:
    """
    Calcula las horas trabajadas en horario nocturno (9 PM - 6 AM).
    """
    entrada_dt = datetime.combine(fecha, entrada)
    salida_dt = datetime.combine(fecha, salida)

    if salida_dt < entrada_dt:
        salida_dt += timedelta(days=1)

    horas_nocturnas = 0
    current = entrada_dt

    while current < salida_dt:
        hora_actual = current.time()
        if es_hora_nocturna(hora_actual):
            horas_nocturnas += 1/60  # Incrementar por minuto
        current += timedelta(minutes=1)

    return round(horas_nocturnas, 2)


def calcular_valor_horas(horas: dict[str, float], config: dict[str, Any]) -> dict[str, float]:
    """
    Calcula el valor monetario de las horas trabajadas.

    Args:
        horas: Diccionario con tipos de horas
        config: Configuración con valores por hora

    Returns:
        Diccionario con valores calculados
    """
    valor_hora_ordinaria = float(config.get('valor_hora_ordinaria', 0))
    valor_hora_extra_diurna = float(config.get('valor_hora_extra_diurna', 0))
    valor_hora_extra_nocturna = float(config.get('valor_hora_extra_nocturna', 0))

    # Factores de recargo según legislación colombiana
    factor_recargo_nocturno = 1.35
    factor_dominical = 1.75

    valores = {
        'valor_ordinarias': round(horas.get('horas_ordinarias', 0) * valor_hora_ordinaria, 2),
        'valor_extra_diurna': round(horas.get('horas_extra_diurna', 0) * valor_hora_extra_diurna, 2),
        'valor_extra_nocturna': round(horas.get('horas_extra_nocturna', 0) * valor_hora_extra_nocturna, 2),
        'valor_recargo_nocturno': round(
            horas.get('horas_recargo_nocturno', 0) * valor_hora_ordinaria * factor_recargo_nocturno, 2
        ),
        'valor_dominical': round(
            horas.get('horas_dominical', 0) * valor_hora_ordinaria * factor_dominical, 2
        ),
    }

    valores['total'] = round(sum(valores.values()), 2)

    return valores
