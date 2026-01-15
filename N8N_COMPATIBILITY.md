# Compatibilidad con n8n MCP Client

Este documento explica cómo se solucionó el problema de compatibilidad entre FastMCP y el nodo MCP Client de n8n.

## El Problema

El servidor MCP funciona perfectamente con clientes como **ChatKit de OpenAI**, pero falla con el **MCP Client de n8n**.

### Síntomas
- ChatKit: Las herramientas se ejecutan correctamente
- n8n: Responde `202 Accepted` pero las herramientas nunca se ejecutan
- Error en logs: `Unexpected keyword argument: success, toolCallId`

### Causa Raíz

n8n MCP Client tiene un **bug conocido** donde envía parámetros extra en los argumentos de las herramientas que no deberían estar ahí:

```json
{
  "tool": "obtener_ultimo_registro",
  "codigo_empleado": "10018084",
  "toolCallId": "toolu_01MUbkKTztLBvDaLdqyoC6gH",
  "sessionId": "abc123",
  "success": true,
  "action": "mcp",
  "chatInput": "..."
}
```

Los parámetros `toolCallId`, `sessionId`, `success`, `action`, y `chatInput` son metadatos internos de n8n que **no deberían** enviarse como argumentos de la herramienta.

### Referencias
- GitHub Issue #21500: [MCP Tool node sends extra parameters](https://github.com/n8n-io/n8n/issues/21500)
- GitHub Issue #21716: [MCP Client validation errors](https://github.com/n8n-io/n8n/issues/21716)
- GitHub Issue #22787: [Parameters leaking to tool calls](https://github.com/n8n-io/n8n/issues/22787)

## La Solución

Se implementó un **Middleware de FastMCP** que intercepta las llamadas a herramientas y filtra los parámetros extra antes de la validación.

### Código del Middleware

```python
from fastmcp import FastMCP
from fastmcp.server.middleware import Middleware, MiddlewareContext

# Parámetros que n8n envía incorrectamente
N8N_EXTRA_PARAMS = {'toolCallId', 'sessionId', 'success', 'action', 'chatInput'}


class N8NCompatibilityMiddleware(Middleware):
    """Middleware que filtra parámetros extra enviados por n8n MCP Client"""

    async def on_call_tool(self, context: MiddlewareContext, call_next):
        """Intercepta llamadas a herramientas y filtra parámetros de n8n"""
        message = context.message

        # Verificar si hay argumentos para filtrar
        if hasattr(message, 'arguments') and message.arguments:
            original_args = dict(message.arguments)
            filtered_args = {
                k: v for k, v in original_args.items()
                if k not in N8N_EXTRA_PARAMS
            }

            # Si se filtraron parámetros, loguearlo
            removed = set(original_args.keys()) - set(filtered_args.keys())
            if removed:
                print(f">>> [N8N-FIX] Removidos parámetros extra: {removed}", flush=True)
                # Actualizar los argumentos
                message.arguments = filtered_args

        return await call_next(context)
```

### Uso del Middleware

```python
mcp = FastMCP(
    "mi-servidor-mcp",
    instructions="...",
    lifespan=lifespan,
    middleware=[N8NCompatibilityMiddleware()]  # <-- Agregar aquí
)
```

## Cómo Funciona

1. **Intercepción**: El middleware intercepta todas las llamadas a herramientas via `on_call_tool`
2. **Filtrado**: Examina los argumentos y remueve los que están en `N8N_EXTRA_PARAMS`
3. **Logging**: Si se removieron parámetros, lo registra en los logs
4. **Continuación**: Pasa la llamada limpia al siguiente handler

## Verificación

Cuando n8n llama a una herramienta, verás en los logs:

```
>>> [N8N-FIX] Removidos parámetros extra: {'success', 'toolCallId'}
>>> [2026-01-15 10:30:45] TOOL: obtener_ultimo_registro(codigo_empleado='10018084')
```

## Alternativas Consideradas

### 1. Usar `**kwargs` en las herramientas
**No funciona** - FastMCP no soporta `**kwargs` en las funciones de herramientas.

### 2. Modificar la validación de FastMCP
**No recomendado** - Requiere modificar el código fuente de FastMCP.

### 3. Middleware (Solución elegida)
**Mejor opción** - No modifica FastMCP, es mantenible y se puede remover cuando n8n arregle el bug.

## Notas Adicionales

- Este es un **workaround** temporal hasta que n8n arregle el bug
- El middleware es **transparente** para otros clientes MCP que funcionan correctamente
- Se recomienda monitorear las actualizaciones de n8n para remover el middleware cuando ya no sea necesario

## Configuración de n8n

Para usar el servidor MCP con n8n:

1. **Endpoint**: `https://tu-servidor.com/mcp`
2. **Server Transport**: `HTTP Streamable`
3. **Authentication**: `None` (o configurar según necesidad)
4. **Tools to Include**: `All`
