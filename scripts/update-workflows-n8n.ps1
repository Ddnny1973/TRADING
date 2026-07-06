#requires -Version 5.1
<#
.SYNOPSIS
    Actualiza ambos workflows en n8n via API (repo → n8n PUSH)

.DESCRIPTION
    Script para sincronizar los JSONs del repo a la instancia de n8n en producción.
    - Hace backup automático antes de actualizar
    - Maneja encoding UTF-8 correcto (PowerShell fix)
    - Actualiza workflow1-market-decision y workflow2-monitor

.PARAMETER N8nUrl
    URL base de n8n (default: https://n8n.gestorconsultoria.com.co)

.PARAMETER ApiKey
    API Key de n8n (si no se proporciona, se pide interactivamente)

.PARAMETER RepoRoot
    Ruta raíz del repo (default: detecta automáticamente)

.EXAMPLE
    .\scripts\update-workflows-n8n.ps1 -ApiKey "sk_live_xxx"

.EXAMPLE
    .\scripts\update-workflows-n8n.ps1  # Pide la API key al ejecutar

.NOTES
    Ejecutar desde la raíz del proyecto TRADING:
    cd "d:\Datos\IA Projects\TRADING"
    .\scripts\update-workflows-n8n.ps1
#>

param(
    [string]$N8nUrl = "https://n8n.gestorconsultoria.com.co",
    [string]$ApiKey,
    [string]$RepoRoot = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
)

$ErrorActionPreference = "Stop"

# ==========================================
# CONFIGURACIÓN
# ==========================================

$workflows = @(
    @{
        Name = "Workflow 1 - Market Decision"
        JsonFile = Join-Path $RepoRoot "n8n-workflows\workflow1-market-decision.json"
        Id = "yggk1wajL1tsmABi"
    },
    @{
        Name = "Workflow 2 - Grid Monitor"
        JsonFile = Join-Path $RepoRoot "n8n-workflows\workflow2-monitor.json"
        Id = "96qAStQwfrHAVXRd"
    }
)

$backupDir = Join-Path $RepoRoot "n8n-workflows"

# ==========================================
# FUNCIONES
# ==========================================

function Get-ApiKey {
    <# Pide la API key de forma segura sin guardarla en el historial #>
    Write-Host "`n⚠️  Ingresa tu n8n API Key (no se guardará en el historial):" -ForegroundColor Yellow
    $secureKey = Read-Host "API Key" -AsSecureString
    $cred = New-Object System.Management.Automation.PSCredential("apikey", $secureKey)
    return $cred.GetNetworkCredential().Password
}

function New-Backup {
    param(
        [string]$WorkflowId,
        [string]$WorkflowName,
        [hashtable]$Headers
    )

    Write-Host "  📦 Haciendo backup..." -ForegroundColor Cyan

    try {
        $resp = Invoke-RestMethod `
            -Uri "$N8nUrl/api/v1/workflows/$WorkflowId" `
            -Headers $Headers `
            -ErrorAction Stop

        $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
        $backupFile = Join-Path $backupDir "backup-$($WorkflowName -replace ' ', '-')-$timestamp.json"

        $resp | ConvertTo-Json -Depth 50 | Out-File $backupFile -Encoding utf8 -Force
        Write-Host "    ✅ Backup guardado: $(Split-Path -Leaf $backupFile)" -ForegroundColor Green
        return $true
    }
    catch {
        Write-Host "    ❌ Error en backup: $_" -ForegroundColor Red
        return $false
    }
}

function Update-Workflow {
    param(
        [string]$WorkflowId,
        [string]$WorkflowName,
        [string]$JsonFile,
        [hashtable]$Headers
    )

    Write-Host "`n🔄 Actualizando $WorkflowName..." -ForegroundColor Cyan

    # Validar que el archivo existe
    if (-not (Test-Path $JsonFile)) {
        Write-Host "  ❌ Archivo no encontrado: $JsonFile" -ForegroundColor Red
        return $false
    }

    try {
        # 1. Hacer backup
        if (-not (New-Backup -WorkflowId $WorkflowId -WorkflowName $WorkflowName -Headers $Headers)) {
            return $false
        }

        # 2. Leer JSON del repo (UTF-8 explícito)
        Write-Host "  📖 Leyendo JSON del repo..." -ForegroundColor Cyan
        $workflowJson = Get-Content $JsonFile -Raw -Encoding UTF8 | ConvertFrom-Json

        # 3. Construir body con solo campos permitidos por API
        $bodyObject = @{
            name        = $workflowJson.name
            nodes       = $workflowJson.nodes
            connections = $workflowJson.connections
            settings    = @{
                executionOrder = $workflowJson.settings.executionOrder
            }
        }

        # 4. Convertir a JSON y luego a bytes UTF-8 (fix PowerShell)
        $bodyJson = $bodyObject | ConvertTo-Json -Depth 50
        $bodyBytes = [System.Text.Encoding]::UTF8.GetBytes($bodyJson)

        # 5. Enviar PUT request
        Write-Host "  📤 Enviando a n8n..." -ForegroundColor Cyan
        $response = Invoke-RestMethod `
            -Uri "$N8nUrl/api/v1/workflows/$WorkflowId" `
            -Method PUT `
            -Headers $Headers `
            -Body $bodyBytes `
            -ContentType "application/json; charset=utf-8" `
            -ErrorAction Stop

        Write-Host "  ✅ $WorkflowName actualizado exitosamente" -ForegroundColor Green
        Write-Host "    ID: $($response.id)" -ForegroundColor Green
        Write-Host "    Nombre: $($response.name)" -ForegroundColor Green
        return $true
    }
    catch {
        Write-Host "  ❌ Error actualizando workflow: $_" -ForegroundColor Red
        return $false
    }
}

# ==========================================
# MAIN
# ==========================================

Write-Host "`n========================================================" -ForegroundColor Cyan
Write-Host "   Actualizar Workflows en n8n (repo -> produccion)" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan

Write-Host "`n📂 Repo root: $RepoRoot" -ForegroundColor Gray

# Validar que estamos en el directorio correcto
if (-not (Test-Path (Join-Path $RepoRoot "n8n-workflows"))) {
    Write-Host "`n❌ Directorio 'n8n-workflows' no encontrado en: $RepoRoot" -ForegroundColor Red
    Write-Host "   Asegúrate de ejecutar este script desde la raíz del proyecto:" -ForegroundColor Yellow
    Write-Host "   cd 'd:\Datos\IA Projects\TRADING'" -ForegroundColor Yellow
    Write-Host "   .\scripts\update-workflows-n8n.ps1" -ForegroundColor Yellow
    exit 1
}

# Obtener API key si no se proporcionó
if (-not $ApiKey) {
    $ApiKey = Get-ApiKey
}

if (-not $ApiKey) {
    Write-Host "`n❌ API Key no proporcionada. Abortando." -ForegroundColor Red
    exit 1
}

# Construir headers
$headers = @{
    "X-N8N-API-KEY" = $ApiKey
    "Content-Type"  = "application/json; charset=utf-8"
}

# Verificar conexión
Write-Host "`n🔍 Verificando conexión a n8n..." -ForegroundColor Cyan
try {
    $testReq = Invoke-RestMethod `
        -Uri "$N8nUrl/api/v1/workflows" `
        -Headers $headers `
        -ErrorAction Stop
    Write-Host "  ✅ Conectado a: $N8nUrl" -ForegroundColor Green
}
catch {
    Write-Host "  ❌ No se puede conectar a n8n: $_" -ForegroundColor Red
    exit 1
}

# Actualizar cada workflow
$successCount = 0
foreach ($workflow in $workflows) {
    if (Update-Workflow `
        -WorkflowId $workflow.Id `
        -WorkflowName $workflow.Name `
        -JsonFile $workflow.JsonFile `
        -Headers $headers) {
        $successCount++
    }
}

# Resumen
Write-Host "`n========================================================" -ForegroundColor Cyan
Write-Host "   RESUMEN" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan

if ($successCount -eq $workflows.Count) {
    Write-Host "`n✅ Todos los workflows fueron actualizados exitosamente" -ForegroundColor Green
    Write-Host "`n📌 Proximos pasos:" -ForegroundColor Yellow
    Write-Host "   1. Verifica en n8n UI que los cambios se reflejaron"
    Write-Host "   2. Ejecuta Workflow 1 manualmente para validar"
    Write-Host "   3. Ejecuta Workflow 2 para verificar monitoreo"
    Write-Host "   4. Revisa los logs de Telegram para notificaciones"
}
else {
    Write-Host "`n❌ Solo $successCount de $($workflows.Count) workflows se actualizaron" -ForegroundColor Red
    Write-Host "   Revisa los errores arriba para mas detalles" -ForegroundColor Red
}
