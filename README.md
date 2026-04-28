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

## Future work

The following features are designed but not implemented in the current MVP:

- **In-cell validation with VBA macros**: the Excel attachment could include a validation column that uses VBA macros to verify glosa format in real-time as the user types. Implementation requires generating .xlsm files with embedded VBA code that validates regex patterns + computes Chilean RUT DV (módulo 11). Out of scope for MVP because corporate banking environments typically block macros by default, requiring per-deployment security coordination.

- **Real-time Gmail reading**: today the agent sends real emails but reads responses from a simulator. Adding Gmail API read access (gmail.readonly scope already configured) would close the loop with real responses. Pending: parse In-Reply-To headers to link replies to original emails, persist as messages in DB.

- **Predictive compliance via RAG over Ley 20.009 + CMF Compendium**: when an IOC enters the system, the agent could query a separate RAG service to generate the legal timeline (max dates for blocking card, first payment, second payment, demand, etc.) and proactively request data from LSC before each milestone. This connects deadline-chaser with the parallel project (RAG over banking regulation).

- **Cross-source data validation**: before alerting LSC about temporal inconsistencies, the agent could query the bank's IOC tables (Microsoft SQL on BCHBD38) to cross-check dates from accounting entries vs IOC tables. Reduces noise by only escalating when both sources disagree.
