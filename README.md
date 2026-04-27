# deadline-chaser

Backend de un agente de seguimiento de deadlines para tareas regulatorias.
Esta primera iteración expone solo lógica de base de datos: lectura de
personas, trabajos pendientes y cálculo de holgura en horas hábiles.

## Stack

- Python 3.11+
- PostgreSQL (corriendo en Docker, `localhost:5432`)
- `psycopg[binary]`, `python-dotenv`, `pytest`

## Esquema

Cinco tablas en el schema `public`:

- `roles`, `areas` — catálogos
- `personas` — con `nivel_roce` (`bajo` | `medio` | `alto`, tipo `nivel_roce_enum`) y
  `lead_time_promedio_horas`
- `trabajos` — `descripcion`, `deadline`, `estado`, `holgura_horas`,
  `persona_asignada_id`
- `mensajes` — historial de envíos al asignado de un trabajo

## Setup

```bash
# 1. activar venv ya existente
source venv/Scripts/activate          # Git Bash en Windows
# o: venv\Scripts\activate.bat        # CMD

# 2. completar credenciales
#    editar .env y poner POSTGRES_PASSWORD=<tu_password>

# 3. instalar dependencias
pip install -e .
```

## Smoke test

```bash
python scripts/test_connection.py
```

Imprime:

1. Personas con su rol y área.
2. Trabajos pendientes con su asignado y deadline.
3. Holgura en horas hábiles (lun–vie 09:00–18:00) del primer trabajo
   pendiente.

## Estructura

```
core/        # lógica reutilizable (db, queries)
scripts/     # entrypoints manuales
tests/       # pytest
```
