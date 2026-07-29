---
title: "Metodología: Cerebro Digital para repos"
purpose: "Bootstrap portable — pégalo en cualquier repo y pide al agente que lo ejecute"
version: 1
---

# Cerebro Digital del repo — instrucciones para el agente

> Copia este archivo en la raíz (o en `docs/`) del repo que quieres documentar
> y pide al agente algo como: *"Sigue las instrucciones de este archivo para
> crear el cerebro digital de este repo"*. El agente debe ejecutar los pasos
> de la sección **Tareas del agente** usando el contexto real del repo — no
> debe inventar estructura ni contenido que no exista.

> **¿El repo ya tiene `docs/brain/` creado (ej. en otra máquina) y solo cambió
> esta plantilla?** No pidas recrear el cerebro. Di algo como: *"Este repo ya
> tiene cerebro digital. Revisa `docs/templates/digital-brain-methodology.md`
> y sincroniza únicamente `.github/copilot-instructions.md` con el paso 5 (o
> `AGENTS.md` si aplica), sin tocar los archivos de `docs/brain/`."* Ver la
> sección **Modo actualización de instrucciones** más abajo.

## Qué es un "cerebro digital"

Una base de conocimiento estructurada en Markdown, versionada junto al
código (no en notas sueltas ni en Confluence/Teams), pensada para que un
agente de IA la navegue de forma eficiente y determinista, en vez de
depender solo de búsqueda semántica difusa (RAG). Se compone de:

1. **Carpeta `docs/brain/`** con un archivo por tema/concepto.
2. **Frontmatter YAML** en cada archivo (metadatos estructurados).
3. **Enlaces explícitos** entre archivos (grafo de conocimiento), tipo
   wikilink `[[archivo]]` dentro del mismo repo, o rutas relativas hacia
   otros repos de la misma aplicación.
4. Un **hub** (`_index.md`) como punto de entrada.

### Por qué no es "solo RAG"

El agente sigue enlaces y metadatos explícitos en vez de inferir relaciones
por similitud semántica → respuestas más deterministas, menos tokens
gastados recuperando contexto irrelevante, trazabilidad clara de qué
documento sustenta qué afirmación.

## Estructura estándar

```
docs/brain/
  _index.md          ← hub: qué es el repo, mapa de contenido, enlaces a otros repos de la app
  <tema>.md           ← un archivo por concepto/proceso/componente/decisión
  ...
```

## Frontmatter obligatorio

```yaml
---
title: "Nombre del concepto"
type: hub | component | infra | process | decision | howto
app: <nombre de la aplicación/dominio a la que pertenece este repo>
repo: <nombre del repo>
tags: [tag1, tag2]
related:
  - "[[otro-archivo-del-mismo-repo]]"
  - "../otro-repo-hermano/docs/brain/_index.md"   # solo si aplica
updated: <YYYY-MM-DD>
owner: <usuario o equipo>
---
```

## Convenciones de enlace

- Mismo repo → wikilink `[[archivo]]` (sin extensión `.md`).
- Repo hermano de la misma aplicación (si viven como carpetas hermanas en el
  mismo workspace/organización) → ruta relativa completa.
- Documentos preexistentes relevantes del repo (READMEs, ADRs, runbooks) →
  enlázalos con markdown normal (`[texto](../../ARCHIVO.md)`), no los
  dupliques ni los reescribas dentro de `docs/brain/`.

---

## Tareas del agente

Ejecuta estos pasos usando el contexto real del repo actual (explóralo antes
de escribir nada; no inventes estructura, nombres de carpetas ni procesos
que no existan):

1. **Inventario rápido**: identifica qué tipo de repo es (código de
   aplicación, infraestructura, documentación de procesos, etc.), su
   estructura de carpetas principal, stack tecnológico, y si tiene pipeline
   de CI/CD.
2. **Crear `docs/brain/_index.md`** con: qué es el repo, para qué sirve, y
   un mapa de contenido enlazando a los demás archivos que vas a crear.
3. **Crear 2-5 archivos temáticos** en `docs/brain/` según lo que encuentres
   relevante (ej. `arquitectura.md`, `convenciones.md`, `ci-cd.md`,
   `testing.md`) — solo los que aporten valor real, no relleno.
4. **Si el repo tiene pipeline de CI/CD**: pregunta si se desea excluir
   `docs/brain/` de la detección de cambios que dispara build/test/deploy.
   Si el usuario confirma:
   - Verifica primero si existe algún **control/policy obligatorio a nivel
     de organización** (ej. quality gates de SonarQube, checks de seguridad)
     que exija que *todo* PR tenga cierto análisis asociado — si existe,
     no lo saltes por completo; ajusta el pipeline para que ese análisis
     obligatorio se siga ejecutando (aunque sea trivial) y solo se salten
     los pasos específicos de código (tests, build, deploy).
   - **Usa condiciones evaluadas en runtime** (`condition:` en Azure
     Pipelines, `if:` en GitHub Actions con contexto de steps previos) para
     saltar pasos según una carpeta detectada en un paso anterior del mismo
     job — **no** uses expresiones de *compile-time* (`${{ if }}` en Azure
     Pipelines) para evaluar variables que se calculan en runtime dentro del
     mismo pipeline, porque esas expresiones se resuelven antes de que la
     variable exista y el resultado es incorrecto siempre (rompe el pipeline
     para todos los casos, no solo el de documentación).
5. **Crear/actualizar `.github/copilot-instructions.md`** (o `AGENTS.md` si
   el repo ya usa esa convención) en la raíz del repo, agregando una
   instrucción corta y persistente con **dos responsabilidades** (leer y
   mantener), por ejemplo:
   ```markdown
   ## Cerebro digital del repo

   - Antes de responder preguntas sobre este repo, revisa
     `docs/brain/_index.md` y sigue sus enlaces si el tema es relevante.
   - Si tu cambio de código vuelve desactualizado, incorrecto o incompleto
     algún archivo de `docs/brain/`, actualízalo como parte del mismo PR
     (no lo dejes para después) y actualiza su campo `updated` en el
     frontmatter.
   - Si detectas que falta documentar un concepto nuevo relevante
     (componente, proceso, decisión), proponle al usuario crear un archivo
     nuevo en `docs/brain/` en vez de dejarlo sin documentar.
   ```
   Esto asegura que sesiones futuras (en cualquier máquina, para cualquier
   colaborador que clone el repo) carguen el cerebro automáticamente Y lo
   mantengan al día, sin depender de que alguien lo pida explícitamente.
6. **Reporta al usuario**: qué archivos creaste, qué carpetas/temas cubriste,
   y qué decisiones tomaste (ej. si excluiste o no `docs/brain/` del CI/CD y
   por qué).

## Modo actualización de instrucciones (solo cuando `docs/brain/` ya existe)

Úsalo cuando el usuario pida explícitamente sincronizar/actualizar
instrucciones tras un cambio de esta plantilla (típicamente al abrir el repo
en otra máquina) — **no** reejecutes el bootstrap completo ni toques los
archivos temáticos de `docs/brain/`:

1. Verifica que `docs/brain/_index.md` ya existe. Si no existe, esto no
   aplica — ejecuta el bootstrap completo (sección **Tareas del agente**)
   en su lugar.
2. Localiza el archivo de instrucciones persistente del repo
   (`.github/copilot-instructions.md` o `AGENTS.md`, el que ya use el repo).
3. Compara el contenido actual de su sección "Cerebro digital del repo"
   contra el bloque de ejemplo del paso 5 de esta plantilla.
4. Si difieren, actualiza **solo esa sección** (no reescribas el resto del
   archivo de instrucciones si tiene contenido adicional del repo ajeno al
   cerebro digital).
5. No modifiques ningún archivo dentro de `docs/brain/` en este modo, ni su
   frontmatter `updated` — esos campos solo cambian cuando el contenido que
   describen cambia realmente.
6. Reporta al usuario si hubo diferencia y qué se actualizó (o confirma que
   ya estaba al día).

## Actualización del cerebro (mantenimiento continuo)

El cerebro se degrada si nadie lo actualiza. La responsabilidad de
mantenerlo al día es del **agente**, disparada por la instrucción
persistente del paso 5 — el humano no debería tener que acordarse de
pedirlo. Reglas concretas:

1. **Actualización reactiva (la más importante)**: cada vez que el agente
   haga un cambio de código/infra/proceso que contradiga o vuelva obsoleto
   algo escrito en `docs/brain/`, debe actualizar ese archivo **en el mismo
   PR**, no en uno aparte. Esto incluye cambiar el campo `updated` en el
   frontmatter a la fecha del cambio.
2. **Detección de desactualización (drift check)**: cuando el usuario pida
   revisar si el cerebro sigue vigente (ej. *"¿el cerebro está
   actualizado?"*), el agente debe:
   - Comparar la fecha `updated` de cada archivo de `docs/brain/` contra la
     fecha del último cambio real de lo que ese archivo documenta (ej.
     último commit relevante en la carpeta/archivo que describe).
   - Señalar los archivos cuyo contenido ya no coincide con el código/
     proceso actual, y proponer (no aplicar sin confirmar, salvo que sea un
     ajuste menor) los cambios necesarios.
3. **Nuevo concepto sin documentar**: si el agente crea o modifica algo que
   claramente merece un archivo nuevo en `docs/brain/` (nuevo componente,
   nuevo proceso, decisión de arquitectura importante) y no existe, debe
   proponer crearlo en vez de ignorarlo.
4. **Nunca dejar el cerebro obsoleto "a propósito"**: si por alcance de la
   tarea no se puede actualizar de inmediato, el agente debe decírselo
   explícitamente al usuario (ej. *"esto deja desactualizado
   `docs/brain/arquitectura.md`, ¿lo actualizo ahora o en otro PR?"*) en vez
   de omitirlo silenciosamente.
5. **Repos hermanos**: si actualizar un hub de aplicación implica tocar el
   `_index.md` de un repo distinto (ej. el hub de infra que enlaza a varios
   repos de código), el agente debe avisar que ese otro repo también
   necesita actualizarse, aunque no pueda hacerlo en el mismo PR (por estar
   en otro repositorio).

## Mantenimiento estructural

- Si el repo es parte de una aplicación con varios repos hermanos (ej. infra
  + varios repos de código), el hub de cada repo debe enlazar al hub de los
  demás, y uno de ellos (normalmente el de infra) actúa como hub de la
  aplicación completa.
