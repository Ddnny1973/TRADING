# Script de Actualización de Workflows en n8n

**Archivo:** `update-workflows-n8n.ps1`  
**Propósito:** Sincronizar ambos workflows (repo → n8n producción) via API  
**Plataforma:** PowerShell 5.1+ (Windows)

---

## ⚠️ IMPORTANTE

**Este script NO está en el repo** (está en `.gitignore`). Debes crearlo localmente en tu máquina:

```bash
# Está en:
d:\Datos\IA Projects\TRADING\update-workflows-n8n.ps1

# No se sincroniza a GitHub por seguridad (contiene API keys)
```

---

## Requisitos Previos

1. ✅ PowerShell 5.1 o superior
2. ✅ API Key de n8n (obtenida en Settings → n8n API → Create API Key)
3. ✅ Los JSONs actualizados en `n8n-workflows/`
4. ✅ Acceso de lectura/escritura a `https://n8n.gestorconsultoria.com.co/api/v1/workflows`

---

## Cómo Usar

### Opción 1: Con API Key en el comando (menos seguro)
```powershell
.\update-workflows-n8n.ps1 -ApiKey "sk_live_xxxxx"
```

### Opción 2: Pedir API Key al ejecutar (recomendado)
```powershell
.\update-workflows-n8n.ps1
# Luego pega tu API Key cuando se pida (no se guardará en historial)
```

### Opción 3: Con n8n URL personalizada
```powershell
.\update-workflows-n8n.ps1 -N8nUrl "http://localhost:5678" -ApiKey "sk_live_xxxxx"
```

---

## Qué Hace El Script

1. ✅ **Verifica conexión** a n8n
2. ✅ **Hace backup automático** de ambos workflows (antes de actualizar)
3. ✅ **Lee los JSONs** del repo con encoding UTF-8 correcto
4. ✅ **Envía via API PUT** a n8n (maneja emojis, tildes, etc.)
5. ✅ **Valida respuesta** y muestra resumen

### Archivos que actualiza:
- `workflow1-market-decision.json` → `yggk1wajL1tsmABi`
- `workflow2-monitor.json` → `96qAStQwfrHAVXRd`

### Backups creados:
```
n8n-workflows/backup-Workflow-1---Market-Decision-20260705-143522.json
n8n-workflows/backup-Workflow-2---Grid-Monitor-20260705-143522.json
```

---

## Salida Esperada

```
╔════════════════════════════════════════════════════════════╗
║   Actualizar Workflows en n8n (repo → producción)          ║
╚════════════════════════════════════════════════════════════╝

🔍 Verificando conexión a n8n...
  ✅ Conectado a: https://n8n.gestorconsultoria.com.co

🔄 Actualizando Workflow 1 - Market Decision...
  📦 Haciendo backup...
    ✅ Backup guardado: n8n-workflows/backup-Workflow-1---Market-Decision-20260705-143522.json
  📖 Leyendo JSON del repo...
  📤 Enviando a n8n...
  ✅ Workflow 1 - Market Decision actualizado exitosamente
    ID: yggk1wajL1tsmABi
    Nombre: workflow1-market-decision

🔄 Actualizando Workflow 2 - Grid Monitor...
  📦 Haciendo backup...
    ✅ Backup guardado: n8n-workflows/backup-Workflow-2---Grid-Monitor-20260705-143522.json
  📖 Leyendo JSON del repo...
  📤 Enviando a n8n...
  ✅ Workflow 2 - Grid Monitor actualizado exitosamente
    ID: 96qAStQwfrHAVXRd
    Nombre: workflow2-monitor

╔════════════════════════════════════════════════════════════╗
║   RESUMEN                                                  ║
╚════════════════════════════════════════════════════════════╝

✅ Todos los workflows fueron actualizados exitosamente

📌 Próximos pasos:
   1. Verifica en n8n UI que los cambios se reflejaron
   2. Ejecuta Workflow 1 manualmente para validar
   3. Ejecuta Workflow 2 para verificar monitoreo
   4. Revisa los logs de Telegram para notificaciones
```

---

## Códigos de Salida

| Código | Significado |
|--------|------------|
| `0` | ✅ Éxito - Todos los workflows actualizados |
| `1` | ❌ Error - No se pudieron actualizar los workflows |

---

## Troubleshooting

### Error: "API Key no proporcionada"
```powershell
# Solución: Proporciona la API key
.\update-workflows-n8n.ps1 -ApiKey "tu-key-aqui"
```

### Error: "No se puede conectar a n8n"
```powershell
# Verifica:
# 1. URL correcta: https://n8n.gestorconsultoria.com.co (o tu instancia)
# 2. API Key válida
# 3. Acceso a internet
.\update-workflows-n8n.ps1 -N8nUrl "http://localhost:5678"
```

### Error: "Archivo no encontrado"
```powershell
# Verifica que estés en el directorio correcto:
cd "d:\Datos\IA Projects\TRADING"
.\update-workflows-n8n.ps1
```

### Error: "Settings must NOT have additional properties"
Este error significa que hay campos internos de n8n en el JSON. El script lo maneja automáticamente, pero si persiste:
- Descarga el workflow de n8n nuevamente
- Reemplaza el JSON en `n8n-workflows/`
- Ejecuta el script de nuevo

---

## Guía de Seguridad

⚠️ **NUNCA** hagas esto:
- ❌ No guardes el script con la API key hardcodeada en GitHub
- ❌ No compartas el script con la API key en Slack/email
- ❌ No dejes el script con la API key en historial de PowerShell

✅ **Sí** haz esto:
- ✅ Corre el script sin `-ApiKey` (te pide interactivamente)
- ✅ Si necesitas usar `-ApiKey`, guarda el valor en una variable de entorno segura
- ✅ El script está en `.gitignore` — no se sincroniza a GitHub

---

## Detalles Técnicos

### Por qué UTF-8 explícito?
PowerShell 5.1 no codifica correctamente caracteres especiales (emojis, tildes) a menos que especifiques UTF-8. Sin esto, los emojis en las notificaciones de Telegram se corrompen.

### Por qué limitar `settings`?
La API pública de n8n solo acepta ciertos campos en `settings`. El script reconstruye manualmente solo los permitidos (`executionOrder`).

### Por qué hacer backup?
Antes de actualizar, el script descarga una copia completa del workflow en producción. Si algo sale mal, puedes restaurar desde `n8n-workflows/backup-*.json`.

---

## Ejemplo Completo

```powershell
# 1. Abre PowerShell como usuario normal (no necesita admin)
# 2. Navega al repo
cd "d:\Datos\IA Projects\TRADING"

# 3. Ejecuta el script (pedirá API key)
.\update-workflows-n8n.ps1

# 4. En el prompt "API Key", pega tu clave (se oculta mientras escribes)
# 5. Presiona Enter
# 6. Espera a que termine (debe tardar 5-10 segundos)

# 7. Verifica que dice "✅ Todos los workflows fueron actualizados exitosamente"

# 8. Abre n8n UI y verifica que los cambios se reflejaron:
#    - Los nodos deben verse actualizados
#    - Las notificaciones deben mostrar los nuevos campos

# 9. Prueba manualmente:
#    - Ejecuta Workflow 1 (debe crear grid con SL correcto)
#    - Ejecuta Workflow 2 (debe hacer refresh sin error 500)
```

---

## FAQ

**P: ¿Necesito ejecutar esto cada vez que cambio un nodo?**  
R: No. Solo si cambias el JSON en el repo. Si editas en n8n UI, usa "Download" para actualizar el repo.

**P: ¿Puedo ejecutar este script en Linux/Mac?**  
R: No directamente. Necesitas PowerShell 7.0+ o usar bash. Ddnny1973 documentó una versión bash en `n8n-workflows/README.md`.

**P: ¿Qué pasa si el script falla a mitad de?**  
R: Todos los cambios se revierten automáticamente en n8n (no hubo actualización exitosa). Los backups quedan en `n8n-workflows/backup-*.json` para referencia.

**P: ¿Cuánto tarda?**  
R: 5-10 segundos por workflow (incluido backup).

---

## Commit Relacionado

```bash
# Los JSONs actualizados están en:
git log --oneline -- n8n-workflows/workflow*.json | head -5

# Este script NO está versionado (está en .gitignore)
git status | grep update-workflows-n8n.ps1
# (no debe aparecer)
```

---

**Última actualización:** 2026-07-05  
**Autor del script:** Claude (basado en receta de Ddnny1973 en `n8n-workflows/README.md`)
