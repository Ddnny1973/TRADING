# Instrucciones para agentes de IA en este repo

## Cerebro digital del repo

- Antes de responder preguntas sobre este repo, revisa
  [`docs/brain/_index.md`](../docs/brain/_index.md) y sigue sus enlaces si el
  tema es relevante para la solicitud (infraestructura multi-servidor,
  sincronización repo→n8n, decisiones técnicas).
- Si tu cambio de código vuelve desactualizado, incorrecto o incompleto
  algún archivo de `docs/brain/`, actualízalo como parte del mismo PR (no lo
  dejes para después) y actualiza su campo `updated` en el frontmatter.
- Si detectas que falta documentar un concepto nuevo relevante (componente,
  proceso, decisión), proponle al usuario crear un archivo nuevo en
  `docs/brain/` en vez de dejarlo sin documentar.

Para documentación de producto (setup, API, workflows, trading logic), usa
la estructura numerada en [`docs/00-START/`](../docs/00-START/) a
[`docs/90-APPENDICES/`](../docs/90-APPENDICES/), empezando por
[`docs/00-START/02-tabla-contenidos.md`](../docs/00-START/02-tabla-contenidos.md).
