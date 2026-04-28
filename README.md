# deadline-chaser

AI agent that coordinates humans to deliver bank regulatory reporting on time. Built on a real domain — Chilean banking compliance — with synthetic data and a stylized version of the actual workflow the author lived during 3 years at Banco de Chile's fraud prevention team.

## What it does

The agent monitors pending regulatory tasks in a bank's compliance pipeline and decides when (and to whom) to send follow-up emails. It generates personalized emails with Excel attachments containing data inconsistencies that need to be corrected, reads responses, validates the corrections, and either closes the case or escalates with context-specific clarifications.

The specific data format used in this project (LSC glosa structure: `IOC NNNNNN RUT XXXXXXXX X ID NNNNNN XXX`) is a simplified version inspired by real internal formats. The exact formats banks use are confidential. What is not confidential — and what this project aims to demonstrate — is the universal problem: every bank in LATAM has compliance teams chasing humans across departments to fix data inconsistencies before regulatory deadlines.

Key design principle: **deterministic routing in Python, creative generation with LLM**. The LLM only writes prose; all decisions about who to email, when, and how urgent are made by Python with explicit rules.

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  PostgreSQL (Docker)                                         │
│  - trabajos        (pending tasks)                           │
│  - personas        (with response archetypes)                │
│  - mensajes        (sent + received)                         │
│  - tipos_trabajo                                             │
└──────────────────────────────────────────────────────────────┘
                            ↑ ↓
┌──────────────────────────────────────────────────────────────┐
│  ORCHESTRATOR (scripts/job_diario.py)                        │
│                                                              │
│  1. Read pending tasks                                       │
│  2. Classify zone (p97/p84/p50/critico)                      │
│  3. Check throttle per zone                                  │
│  4. Decide action based on state                             │
└──────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────┐
│  AGENT (core/agente.py)                                      │
│                                                              │
│  ROUTING (Python, deterministic)                             │
│  ├─ ROUTING_MATRIX: zone + tipo + roce → TO/CC               │
│  └─ Resolve persona_id → email aliases                       │
│                                                              │
│  GENERATION (OpenAI GPT-4o-mini, creative)                   │
│  ├─ System prompt: voice + format + intent                   │
│  └─ User prompt: recipient + intention + tone                │
│                                                              │
│  EXCEL ATTACHMENT (core/excel_generator.py)                  │
│  └─ openpyxl RichText: red-marked errors                     │
└──────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────┐
│  GMAIL API (core/enviar.py)                                  │
│  └─ OAuth, aliases, Reply-To header                          │
└──────────────────────────────────────────────────────────────┘
                              ↓
                  PERSONS RECEIVE EMAIL
                  (Yolanda, Carlos, Pedro...)
                              ↓
┌──────────────────────────────────────────────────────────────┐
│  RESPONSE PROCESSING                                         │
│                                                              │
│  simulador.py    → archetypes (certero/mixto/caotico)        │
│  validador.py    → glosa format + RUT módulo 11              │
│  pelota detector → derivation patterns                       │
└──────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────┐
│  STATE UPDATE (core/lectura_respuestas.py)                   │
│                                                              │
│  ├─ respondido_ok      → close task                          │
│  ├─ con_errores        → send aclaracion email               │
│  ├─ derivado           → return responsibility               │
│  └─ respuesta_ambigua  → flag for review                     │
└──────────────────────────────────────────────────────────────┘
                              ↑
                              └─── back to ORCHESTRATOR
```

## Why deterministic routing + creative generation

A common failure mode in LLM agents is letting the model decide things that are not creative — like routing emails or applying business rules — and watching it contradict its own instructions. In this project, all routing decisions (who receives the email, who goes in CC, when to send, when to wait) are made in Python with explicit rules in a `ROUTING_MATRIX`. The LLM only sees the resolved recipient and writes the prose.

This split has three concrete benefits:
- **Auditable**: every routing decision traces back to a single rule, not "the LLM decided"
- **Testable**: the router is pure Python; tests run without OpenAI calls
- **Cheap to extend**: a new edge case adds one row to the matrix, no prompt rewrites

## Stack

- Python 3.11
- PostgreSQL 18 (Docker)
- OpenAI GPT-4o-mini for email drafting
- Gmail API (OAuth) for sending emails
- LangChain for LLM orchestration
- openpyxl for Excel generation with rich text

## Quickstart

```bash
# 1. Clone and set up environment
git clone https://github.com/jplubbert/deadline-chaser
cd deadline-chaser
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 2. Configure environment variables
cp .env.example .env
# Edit .env with your OpenAI API key and Postgres password

# 3. Set up Postgres (Docker)
docker run -d --name postgres-deadline-chaser \
  -e POSTGRES_PASSWORD=your_password \
  -e TZ=America/Santiago \
  -p 5432:5432 postgres:18

# 4. Initialize schema
python scripts/setup_db.py

# 5. Configure Gmail OAuth
# Place credentials.json from Google Cloud Console in the project root
python scripts/test_gmail.py  # generates token.json on first run

# 6. Run the daily job
python scripts/job_diario.py
```

## Project structure

```
deadline-chaser/
├── core/
│   ├── agente.py              LLM email drafting + deterministic routing
│   ├── decisiones.py          Throttling decisions per zone
│   ├── enviar.py              Gmail API send with attachments
│   ├── excel_generator.py     Excel attachment with red-marked errors
│   ├── gmail_client.py        OAuth setup
│   ├── lectura_respuestas.py  Process simulated responses
│   ├── mensajes.py            Persistence layer
│   ├── queries.py             DB queries
│   ├── simulador.py           Synthetic data + persona archetypes
│   ├── validador.py           Format validation (RUT módulo 11, glosa regex)
│   └── zonas.py               Statistical zone classification
├── scripts/
│   ├── job_diario.py              Daily orchestrator
│   ├── simular_respuestas.py      Insert simulated responses
│   ├── procesar_respuestas.py     Validate and update task states
│   ├── enviar_correos.py          Manual send
│   └── test_gmail.py              OAuth smoke test
├── dominio-banco.md           Banking compliance domain documentation
├── .env.example
└── README.md
```

## Statistical zone classification

Each pending task gets classified into one of four zones based on remaining business hours and the assigned person's expected response time. The zones drive how aggressively the agent follows up:

| Zone     | Meaning                                | Throttle      |
|----------|----------------------------------------|---------------|
| p97      | Plenty of time, just keep on radar     | Once a week   |
| p84      | Deadline approaching, friendly nudge   | Every 3 days  |
| p50      | Tight, need coordination               | Daily         |
| critico  | Risk of missing the deadline           | AM + PM       |

When a task moves between zones (e.g. p50 → critico), the agent overrides the throttle and sends immediately.

## Persona archetypes (synthetic testing)

To test the full cycle without waiting for real human responses, the simulator includes three archetypes:

| Archetype | First-response success rate | Behavior |
|-----------|------------------------------|----------|
| `certero` | 99% | Responds correctly, on time, proper format |
| `mixto`   | 70% | Sometimes incomplete, sometimes correct, variable format |
| `caotico` | 40% | 4 branches: bad format (30%), pelota (20%), late (10%), ignore (40%) |

Each persona in DB is mapped to one archetype, allowing reproducible end-to-end testing.

## Response validation

When a response arrives (today via simulator, tomorrow via Gmail read API), the agent:

1. **Parses the glosa** using regex over the canonical format `IOC NNNNNN RUT XXXXXXXX X ID NNNNNN XXX`
2. **Validates each component** independently (IOC digits, RUT módulo 11, ID format, responsible initials)
3. **Detects derivation** ("pelota") with regex patterns over Spanish corporate phrases
4. **Updates task state** to one of: `respondido_ok`, `respuesta_con_errores`, `derivado`, `respuesta_ambigua`
5. **Next day's orchestrator** reads the new state and decides whether to close, send clarification, or return responsibility

## Domain context

The author worked for 3 years in Banco de Chile's fraud prevention team, where part of the job was monitoring data quality across the compliance pipeline (LSC, Risk Operations, Legal) and coordinating corrections before monthly reports went to the Chilean banking regulator (CMF).

This project rebuilds a stylized version of that workflow with synthetic data. Full domain documentation in `dominio-banco.md` covers:

- LSC glosa formats and validation rules (Chilean RUT módulo 11)
- Cross-account invariants (Fraude ≥ Castigo ≥ Recupero)
- E24 reporting to CMF (Chilean banking regulator)
- Account structure (TC, TD, TEF, FR with castigo/recupero pairs)

## Future work

The following features are designed but not implemented in the current MVP:

- **In-cell validation with VBA macros**: the Excel attachment could include a validation column that uses VBA macros to verify glosa format in real-time as the user types. Implementation requires generating .xlsm files with embedded VBA code that validates regex patterns + computes Chilean RUT DV (módulo 11). Out of scope for MVP because corporate banking environments typically block macros by default, requiring per-deployment security coordination.

- **Real-time Gmail reading**: today the agent sends real emails but reads responses from a simulator. Adding Gmail API read access (gmail.readonly scope already configured) would close the loop with real responses. Pending: parse `In-Reply-To` headers to link replies to original emails, persist as messages in DB.

- **Predictive compliance via RAG over Ley 20.009 + CMF Compendium**: when an IOC enters the system, the agent could query a separate RAG service to generate the legal timeline (max dates for blocking card, first payment, second payment, demand, etc.) and proactively request data from LSC before each milestone. This connects deadline-chaser with the parallel project (RAG over banking regulation).

- **Cross-source data validation**: before alerting LSC about temporal inconsistencies, the agent could query the bank's IOC tables (Microsoft SQL) to cross-check dates from accounting entries vs IOC tables. Reduces noise by only escalating when both sources disagree.

## Author

José Pedro Lubbert · 3 years at Banco de Chile (Fraud Prevention & Compliance) · [github.com/jplubbert](https://github.com/jplubbert)

Building AI tools for regulatory compliance in LatAm banking.
