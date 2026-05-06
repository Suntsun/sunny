# Claude Orchestrator Skills

---

# SKILL-01: Rol de orquestador en sistemas de automatización

## Objetivo
Mantener a Claude en su rol de coordinador dentro de un flujo de trabajo estructurado. Claude orquesta, delega a OpenCode para ejecución en disco, y toma decisiones de conflicto. Esto garantiza trazabilidad, responsabilidad clara y flujos reproducibles en cualquier proyecto de automatización.

## Cuándo Usarla
Siempre que el proyecto involucre múltiples pasos técnicos encadenados: diseño, implementación, testing y ejecución. Se activa especialmente cuando hay una tarea de ejecución concreta que debe ir a OpenCode.

## Instrucciones

### Formato obligatorio de respuesta
Toda respuesta relevante sigue esta estructura:
- **PLAN:** descomposición de la tarea en pasos concretos
- **ASIGNACIÓN:** qué agente hace qué (Claude diseña, OpenCode ejecuta)
- **FLUJO DE EJECUCIÓN:** orden de pasos con dependencias
- **DECISIÓN FINAL:** cuando hay ambigüedad o conflicto

### Delegación
- **Claude (chat):** diseño, auditoría, decisiones, prompts, documentación
- **Claude Code / OpenCode:** ejecución en disco, instalación de deps, pytest, comandos de terminal
- **Consulta externa:** solo si Claude no tiene suficiente contexto técnico especializado y el usuario lo aprueba

### Lo que Claude nunca hace directamente
- Ejecutar comandos en terminal
- Escribir archivos en disco
- Tomar decisiones arquitectónicas estructurales sin documentarlas

## Ejemplos
**Correcto:** "ASIGNACIÓN → Claude: diseña el fix y lo redacta. OpenCode: aplica el archivo y ejecuta pytest."
**Incorrecto:** Claude improvisa una solución técnica compleja sin delegarla ni documentarla.

## Notas Importantes
Si el usuario pide a Claude que "haga" algo que requiere ejecución real, Claude redacta el prompt exacto para OpenCode y espera confirmación del resultado antes de continuar.

---

# SKILL-02: Gestión de contexto entre sesiones

## Objetivo
Garantizar continuidad del proyecto entre sesiones sin pérdida de estado. Claude no tiene memoria persistente — el documento de handoff es el mecanismo de continuidad. Aplica a cualquier proyecto de larga duración.

## Cuándo Usarla
Al inicio de cada sesión nueva (verificar handoff recibido) y al cierre de cada sesión significativa (generar handoff actualizado).

## Instrucciones

### Contenido mínimo de un handoff
- Estado de componentes (completados, en progreso, pendientes)
- Conteo de tests y rojos conocidos
- Tech debt registrado (tabla DEP-N)
- Convenciones aprendidas en el proyecto
- Quirks conocidos de herramientas y entorno
- Próximo paso concreto

### Al recibir un handoff
1. Confirmar comprensión en formato PLAN/ASIGNACIÓN/FLUJO/DECISIÓN
2. Identificar lagunas o inconsistencias
3. Pedir documentación adicional si se necesitan detalles técnicos profundos
4. No iniciar cambios hasta que el usuario indique cómo arrancar

### Al generar un handoff
Actualizar todos los campos que hayan cambiado. Nunca omitir DEPs nuevos ni convenciones descubiertas en la sesión.

## Ejemplos
Sesión termina con bug encontrado → handoff incluye el bug como DEP nuevo con ID, descripción y prioridad antes de cerrar.

## Notas Importantes
El README del proyecto es la fuente de verdad técnica. El handoff es el estado operativo. Ambos deben estar sincronizados al cierre de cada sesión relevante.

---

# SKILL-03: Registro y gestión de tech debt

## Objetivo
Capturar deuda técnica sin bloquear el avance. Registrar cada limitación conocida con suficiente contexto para resolverla en el momento adecuado. Aplicable a cualquier proyecto de software.

## Cuándo Usarla
Cuando se detecta una limitación, workaround, funcionalidad incompleta o decisión técnica subóptima que no se resuelve en el momento.

## Instrucciones

### Formato de registro
| ID | Descripción | Prioridad |
|---|---|---|
| DEP-N | Descripción clara y accionable | Baja / Media / Alta |

### Criterios de prioridad
- **Alta:** bloquea funcionalidad core o tiene riesgo real
- **Media:** afecta experiencia de usuario o mantenibilidad
- **Baja:** cosmético, estilístico o mejora menor

### Cuándo resolver
- Alta: en el ciclo actual
- Media: en fase de polish post-testing
- Baja: backlog, se agrupa y resuelve en batch

### Límite operativo
No acumular más de 15 DEPs sin hacer una sesión de resolución.

## Ejemplos
Bug de herramienta con archivos grandes → DEP con workaround documentado, prioridad baja.
Dependencia no declarada en pyproject.toml → DEP-12, prioridad baja, polish post-testing.

## Notas Importantes
Los DEPs cosméticos se pueden agrupar y resolver en batch. No escalar prioridad por presión — solo por impacto real.

---

# SKILL-04: Auditoría de código antes de ejecución

## Objetivo
Interceptar errores en código generado o propuesto antes de que lleguen a ejecución real. Ahorra ciclos de debugging y mantiene la suite de tests limpia.

## Cuándo Usarla
Siempre que se vaya a ejecutar código nuevo o modificado en OpenCode, especialmente tests y módulos con dependencias cruzadas.

## Instrucciones

### Checklist de auditoría general
1. **Firmas de métodos:** en Python, verificar que mocks de métodos de instancia incluyen `self`
2. **Catálogos sincronizados:** si el código toca un sistema con múltiples puntos de registro (ej. validators, configs, plugins), verificar que todos están actualizados
3. **Imports para testabilidad:** verificar que los imports permiten monkeypatch limpio
4. **Tamaño de archivo:** verificar límites de la herramienta de escritura (ver SKILL-05)
5. **Dependencias nuevas:** si el código introduce una nueva dep, documentarla y aprobarla antes de ejecutar

### Proceso
1. Claude recibe el código propuesto
2. Aplica checklist
3. Si hay problema: corrige y documenta la corrección
4. Si está limpio: pasa a OpenCode con instrucciones exactas de ejecución

## Ejemplos
Código genera `def mock_method():` en lugar de `def mock_method(self):` → Claude lo corrige antes de pasar a ejecución.

## Notas Importantes
La auditoría no es opcional aunque el código parezca correcto. Los errores de descriptor protocol en Python son silenciosos hasta que el test falla.

---

# SKILL-05: Diseño anticipado para limitaciones de herramientas

## Objetivo
Incorporar los límites conocidos de las herramientas en el diseño de tareas antes de ejecutarlas, no después de que fallen. Aplica especialmente a OpenCode y cualquier herramienta con límites de tamaño o conexión.

## Cuándo Usarla
Al diseñar cualquier tarea que involucre creación o escritura de archivos, especialmente en proyectos con archivos de configuración, tests o documentación extensos.

## Instrucciones

### Protocolo para archivos grandes
1. Claude estima el tamaño del archivo antes de asignar a OpenCode
2. Si supera ~6 KB o ~200 líneas: planificar pegado manual por el usuario
3. OpenCode solo recibe comandos de ejecución en ese caso, no escritura de contenido
4. Indicarlo explícitamente en el PLAN antes de ejecutar

### Diseño de tests
- Mantener archivos de test en bloques ≤ 200 líneas
- Si un módulo requiere más tests, dividir en múltiples archivos desde el diseño

### Generalización a otros proyectos
Antes de iniciar un proyecto, documentar los límites conocidos de cada herramienta del stack en el handoff inicial.

## Ejemplos
Crear test de 250 líneas → Claude indica desde el PLAN que el usuario pegará manualmente y OpenCode solo ejecutará `pytest tests/test_archivo.py`.

## Notas Importantes
Este skill debe aplicarse en la fase PLAN, no cuando la herramienta ya ha fallado. El workaround del pegado manual está probado y es fiable.

---

# SKILL-06: Diagnóstico estructurado de fallos en producción

## Objetivo
Ante cualquier fallo en ejecución real, identificar causa raíz, componente afectado y fix mínimo sin escalar innecesariamente a refactoring. Mantener el avance con intervenciones quirúrgicas.

## Cuándo Usarla
Cuando un comando, test o ejecución falla en producción real o en CI. También cuando el comportamiento es incorrecto aunque no haya error explícito.

## Instrucciones

### Proceso de diagnóstico
1. Leer el error completo — no asumir la causa antes de leerlo
2. Identificar: ¿es bug de código, configuración o entorno?
3. Localizar el componente exacto afectado
4. Proponer fix mínimo que no rompa otras partes
5. Si no se resuelve inmediatamente, registrar como DEP

### Clasificación de fallos
- **Entorno:** variable no expandida, PATH incorrecto, venv no activo, servicio no corriendo
- **Configuración:** archivo de config incorrecto, dep no declarada, ruta hardcodeada
- **Código:** lógica incorrecta, edge case no cubierto, integración rota

### Fix mínimo vs refactoring
Aplicar siempre fix mínimo en fase de testing. El refactoring va al backlog como DEP si es necesario.

## Ejemplos
`%USERPROFILE%\Desktop` no se expande → fix mínimo: aplicar `os.path.expandvars()` en el punto exacto donde se usa la ruta. No refactorizar todo el plugin.

## Notas Importantes
Los logs estructurados del proyecto son la primera fuente de diagnóstico. Siempre pedirlos antes de asumir la causa.

---

# SKILL-07: Verificación de entorno antes de testing

## Objetivo
Garantizar que el entorno de ejecución está completamente operativo antes de iniciar cualquier fase de testing. Evita falsos negativos por problemas de entorno que no son bugs del código.

## Cuándo Usarla
Al inicio de cualquier sesión de testing, especialmente tras cambios de máquina, reinstalaciones o sesiones nuevas donde el estado del entorno es desconocido.

## Instrucciones

### Checklist de entorno (orden obligatorio)
1. Entorno virtual activo (prompt muestra `(.venv)`)
2. Dependencias instaladas (`pip show <paquete>` o smoke test directo)
3. Servicios externos corriendo (Ollama, bases de datos, APIs locales)
4. Modelos o recursos externos disponibles (`ollama list` o equivalente)
5. Comando entry point funcional (`<comando> --help`)
6. Smoke test de suite completa (`pytest tests\`)

### Resultado esperado del smoke test
Documentar en el handoff el resultado base: N tests verdes, M rojos conocidos. Cualquier desviación es una señal de alerta antes de testing en producción.

## Ejemplos
Sesión nueva → antes de cualquier comando real, ejecutar checklist completo. Si `sunny --help` falla, resolver antes de continuar.

## Notas Importantes
No saltar pasos aunque parezcan obvios. El problema más frecuente es el venv no activo o el PATH incorrecto — se detecta en 10 segundos si se verifica primero.

---

# SKILL-08: Escalado progresivo de comandos en testing

## Objetivo
Diseñar la secuencia de testing end-to-end de menor a mayor riesgo e impacto. Detectar problemas en comandos inocuos antes de ejecutar acciones con consecuencias reales.

## Cuándo Usarla
Al iniciar cualquier fase de testing en producción real, especialmente en sistemas que interactúan con el sistema de archivos, procesos del sistema o interfaces de usuario.

## Instrucciones

### Secuencia de escalado
1. **Conversación pura:** sin acción real, solo respuesta del LLM
2. **Acción de lectura:** listar, leer, consultar — sin modificar nada
3. **Acción de escritura inocua:** crear archivo temporal, mover algo reversible
4. **Acción con confirmación:** operaciones que el sistema pide confirmar
5. **Acción destructiva:** solo después de que todos los niveles anteriores funcionen

### Criterios para subir de nivel
- El nivel anterior completó sin errores
- Los logs muestran el flujo esperado
- El comportamiento del LLM es coherente con la instrucción

### Documentación por nivel
Registrar el output de cada nivel antes de subir al siguiente. Si algo falla, resolver antes de continuar.

## Ejemplos
Primer test real → `sunny "qué hora es"` (conversación). Solo si funciona → `sunny "lista archivos del escritorio"` (lectura). Solo si funciona → acción de escritura.

## Notas Importantes
Nunca empezar por comandos destructivos en producción real aunque el código esté teóricamente probado. Los tests sintéticos no cubren todo el espacio de inputs del LLM.

---

# SKILL-09: Mantenimiento de convenciones del proyecto

## Objetivo
Tratar las convenciones establecidas en un proyecto como restricciones duras, no como sugerencias. Evita regresiones silenciosas cuando el proyecto crece o cambia de fase.

## Cuándo Usarla
Siempre que se proponga un cambio que toque áreas marcadas como sensibles o que afecte a componentes con múltiples puntos de sincronización.

## Instrucciones

### Tipos de convenciones a proteger
- **Sincronización múltiple:** componentes que deben actualizarse en N sitios simultáneamente
- **Comportamiento de seguridad:** confirmaciones obligatorias, operaciones reversibles vs permanentes
- **Versionado:** nunca editar versiones anteriores, crear versiones nuevas
- **Dependencias:** no añadir deps sin discusión y documentación

### Proceso ante un cambio propuesto
1. Identificar qué convenciones afecta
2. Verificar que el cambio las respeta o propone una actualización explícita
3. Si rompe una convención: documentar por qué y actualizar la convención formalmente
4. Nunca romper una convención silenciosamente

### Convenciones específicas de sunny
- Doble confirmación obligatoria: comprensión + plan destructivo
- `delete` vía send2trash, nunca permanente
- Catálogo de plugins sincronizado en 3 sitios: validator.py, system_v1.txt, _actions del plugin
- System prompts versionados: crear v2, v3... nunca editar el anterior
- Una sola conexión SQLite con threading.Lock para escrituras

## Ejemplos
Cambio en un plugin → verificar que validator.py y system_v1.txt también se actualizan. Si no, el cambio está incompleto.

## Notas Importantes
Las convenciones existen porque algo salió mal sin ellas. No eliminarlas sin entender por qué se crearon.

---

# SKILL-10: Documentación continua y README como fuente de verdad

## Objetivo
Mantener la documentación técnica sincronizada con el estado real del proyecto. El README es el contrato del sistema — debe reflejar lo que existe, no lo que se planeó.

## Cuándo Usarla
Al cerrar cualquier módulo, resolver un DEP significativo, cambiar una convención o completar una fase del proyecto.

## Instrucciones

### Contenido mínimo del README de proyecto
- Diagramas de arquitectura (Mermaid o equivalente)
- Contratos de cada componente (inputs, outputs, efectos)
- Flujo de ejecución detallado
- Decisiones de diseño con su razón
- Áreas sensibles con advertencias explícitas
- Tech debt activo

### Protocolo de actualización
1. Al cerrar un módulo: actualizar su contrato en el README
2. Al resolver un DEP: eliminarlo de la tabla o marcarlo como resuelto
3. Al cambiar una convención: actualizar la sección correspondiente
4. Al completar una fase: añadir resumen de la fase al historial

### Para futuros proyectos
Crear el README desde el inicio, no al final. La estructura mínima se establece en la primera sesión del proyecto.

## Ejemplos
Módulo cerrado → README actualizado con su contrato antes de marcar la tarea como completa. DEP resuelto → eliminado de la tabla en el mismo commit o sesión.

## Notas Importantes
Un README desactualizado es peor que no tener README — genera confianza falsa. Si no hay tiempo para actualizarlo, registrar como DEP con prioridad media.
