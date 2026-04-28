# Dominio: Cumplimiento de Fraude Bancario - Banco de Chile

## Áreas involucradas
- LSC (Línea de Servicio al Cliente): genera glosas iniciales
- Riesgo Operacional (RO): supervisa con visión superior y sistemas propios
- Fiscalía: entrega datos de demandas
- Gobierno de Datos: consolidación
- Prevención de Fraude: dueño del proceso end-to-end ante el regulador

## Glosas LSC

### Volumen
~10.000 glosas/mes

### Formato estricto
- IOC: número de 6 dígitos (identificador del caso)
- RUT: 10 caracteres totales = 8 dígitos + 1 espacio + 1 dígito verificador. Padding con ceros a la izquierda si el RUT base es menor. Ejemplo: 12345678 9
- ID: número de 6 dígitos
- Responsable: inicial nombre + inicial primer apellido + inicial segundo apellido
- Sigla de tipo de pago (solo en cuentas contables de castigo):
  - A05: primer pago al cliente
  - A12: segundo pago al cliente
  - Otras siglas de 3 letras según razón (ej: avenimiento judicial, otras variantes)

### Datos asociados pero fuera de glosa
- Valor del pago: vive en una columna separada (no en el texto de glosa)
- Tipo y razón del pago: derivado de la sigla A05/A12/etc
- Esta data se extrae de la glosa y alimenta el Cuadro de Mando

### Glosa específica por cuenta contable
- Cuentas de castigo: contienen sigla A05/A12/etc indicando tipo de pago
- Cuentas de recupero: tienen su propio formato (no detallado aún)

### Errores comunes
- RUT con dígitos incorrectos
- RUT distinto al asociado a la IOC en sistema (puede ser legítimo si es cuenta bipersonal, hay que justificar)
- Caracteres raros, formato roto
- Sigla mal escrita o ausente

### Flujo de corrección
- Agente devuelve errores diarios por correo al responsable
- Cada error con observación específica
- Campo para reescribir glosa correcta
- Si es cuenta bipersonal: justificación textual en lugar de corrección

## Validación cruzada Fraude/Castigo/Recupero

### Regla invariante (por IOC)
Fraude ≥ Castigo ≥ Recupero

### Tolerancia
Pequeñas diferencias por tipo de cambio si la operación fue en moneda extranjera

### Fuentes de datos
- Base histórica: castigos y recuperos acumulados de todos los meses anteriores
- Base mensual: castigos y recuperos del mes en curso (al cierre se concatena a la histórica)
- Base de fraude: origen pendiente de confirmar

### Manejo de violaciones
- Si se rompe la invariante: caso queda flageado en panel
- LSC debe justificar o corregir
- Riesgo: sin control, se generaban pagos dobles y hasta estafas reales documentadas

### Rol de Riesgo Operacional (RO)
- Supervisaba la cuadratura del Cuadro de Mando con visión superior a Prevención de Fraude
- Tenía sistemas propios para detectar inconsistencias y corregir datos aguas arriba
- Mandaba a corregir datos directamente en el Cuadro de Mando cuando detectaba errores
- Relación simétrica: así como Prevención de Fraude validaba LSC, RO validaba a Prevención de Fraude
- Antes esta función era de Prevención de Fraude internamente; se traspasó a RO buscando más control independiente

## Tablón maestro E24

### Output final
Es el reporte que se envía a la CMF (regulador chileno).

### Construcción
Junta:
- Datos de Fiscalía (planilla de demandas)
- Tablón anterior (stock de casos arrastrados)
- Datos de LSC validados
- 8 cuentas contables (castigos + recuperos por producto TC/TD/TEF + cuenta para gastos/recuperos sin IOC asociada)

### Validaciones temporales (fechas en orden lógico)
- fecha_reclamo < fecha_ingreso_IOC
- fecha_primer_pago dentro del plazo legal
- fecha_segundo_pago dentro del plazo legal
- fecha_bloqueo_tarjeta > fecha_reclamo
- fecha_decision_suspension_pago > fecha_ingreso_IOC
- fecha_demanda > fecha_suspension_pago

### Demandas
Si hay demanda: todos los campos de demanda obligatorios.

### Transformación a "lenguaje E24"
La CMF tiene sus propios campos y reglas. Hay un mapeo de la base maestra interna al formato E24.

### Auditoría
La CMF audita un % bajo de casos. Los errores detectados generan inconsistencias que vuelven a Prevención de Fraude.

## Productos
- TC: Tarjeta de Crédito
- TD: Tarjeta de Débito
- TEF: Transferencia Electrónica de Fondos

## Fiscalía: características operativas
- Entrega lenta, conocido en el banco
- Equipo con digitación manual sin herramientas
- Errores frecuentes:
  - Caracteres raros
  - Columnas que cambian de nombre entre entregas
  - Datos faltantes
- Necesidad: seguimiento agresivo + validación de formato al recibir

## Cuadro de Mando (sistema construido por José Pedro)
- Reemplazó 50+ horas/mes de trabajo manual previo
- Stack técnico: Python + GCP (Storage + Vertex AI) + SQL Developer + Microsoft SQL
- Reportaba diariamente a responsables los errores de glosa específicos
- Inicialmente Power BI → migrado a correo diario por trazabilidad ("cover your own ass")
- Sin estadística sobre nivel de respuesta por persona (oportunidad no implementada en su momento, sí prevista para el agente)

## Estructura organizacional y jerarquía de validación

Existe una cadena de validación encadenada donde cada nivel valida al anterior con sistemas propios:

LSC → Prevención de Fraude → Riesgo Operacional → CMF (regulador)

- LSC es el origen de los datos: sin calidad acá, todo aguas abajo se rompe
- Cumplimiento (Prevención de Fraude) es responsable end-to-end ante el regulador
- Riesgo Operacional valida a Prevención de Fraude con visión superior
- CMF audita un % de los casos finales

## Equipo de desarrollo computacional
- Rol de habilitador
- Recibe "historias" para automatizar procesos
- En este proyecto, el agente toma ese rol de forma autónoma

## Roles que el agente debe poder asumir
1. Validador de glosas (devolver errores específicos a responsables LSC)
2. Coordinador de seguimiento (perseguir entregables de Fiscalía y otros)
3. Detector de violaciones de invariantes (cruce Fraude/Castigo/Recupero con tolerancias por tipo de cambio)
4. Constructor del tablón maestro E24 (consolidación + validaciones temporales)
5. Validador de formato E24 antes de enviar a CMF
6. Tracker de calidad de respuesta por persona (estadística que define perfiles de roce)

## Notas
- Este documento es la fuente de verdad del dominio. Cualquier código del proyecto debe alinearse con esta realidad.
- Los datos reales son confidenciales del banco; el código usa datos sintéticos que respetan el formato real.
- El doc está abierto a iteración: hay piezas marcadas como "pendiente de confirmar" que se completan a medida que se recuerdan o investigan.
