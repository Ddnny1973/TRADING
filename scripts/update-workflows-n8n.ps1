#requires -Version 5.1
param(
    [string]$N8nUrl = "https://n8n.gestorconsultoria.com.co",
    [string]$ApiKey,
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = "Stop"

$workflows = @(
    @{
        Name     = "Workflow 1 - Market Decision"
        JsonFile = Join-Path $RepoRoot "n8n-workflows\workflow1-market-decision.json"
        Id       = "yggk1wajL1tsmABi"
    },
    @{
        Name     = "Workflow 2 - Grid Monitor"
        JsonFile = Join-Path $RepoRoot "n8n-workflows\workflow2-monitor.json"
        Id       = "96qAStQwfrHAVXRd"
    }
)

$backupDir = Join-Path $RepoRoot "n8n-workflows"

function Get-N8nApiKey {
    Write-Host ""
    Write-Host "Ingresa tu n8n API Key:" -ForegroundColor Yellow
    $secureKey = Read-Host "API Key" -AsSecureString
    $cred = New-Object System.Management.Automation.PSCredential("apikey", $secureKey)
    return $cred.GetNetworkCredential().Password
}

function Invoke-Backup {
    param([string]$WorkflowId, [string]$WorkflowName, [hashtable]$Headers)

    Write-Host "  Haciendo backup de $WorkflowName ..." -ForegroundColor Cyan
    try {
        $resp = Invoke-RestMethod -Uri "$N8nUrl/api/v1/workflows/$WorkflowId" -Headers $Headers -ErrorAction Stop
        $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
        $safeName = $WorkflowName -replace ' ', '-'
        $backupFile = Join-Path $backupDir "backup-$safeName-$timestamp.json"
        $resp | ConvertTo-Json -Depth 50 | Out-File $backupFile -Encoding utf8 -Force
        Write-Host "  Backup guardado: $(Split-Path -Leaf $backupFile)" -ForegroundColor Green
        return $true
    } catch {
        Write-Host "  ERROR en backup: $_" -ForegroundColor Red
        return $false
    }
}

function Send-Workflow {
    param([string]$WorkflowId, [string]$WorkflowName, [string]$JsonFile, [hashtable]$Headers)

    Write-Host ""
    Write-Host "Actualizando $WorkflowName ..." -ForegroundColor Cyan

    if (-not (Test-Path $JsonFile)) {
        Write-Host "  ERROR: Archivo no encontrado: $JsonFile" -ForegroundColor Red
        return $false
    }

    $backupOk = Invoke-Backup -WorkflowId $WorkflowId -WorkflowName $WorkflowName -Headers $Headers
    if (-not $backupOk) { return $false }

    try {
        Write-Host "  Leyendo JSON del repo ..." -ForegroundColor Cyan
        $workflowJson = Get-Content $JsonFile -Raw -Encoding UTF8 | ConvertFrom-Json

        $bodyObject = @{
            name        = $workflowJson.name
            nodes       = $workflowJson.nodes
            connections = $workflowJson.connections
            settings    = @{ executionOrder = $workflowJson.settings.executionOrder }
        }

        $bodyJson  = $bodyObject | ConvertTo-Json -Depth 50
        $bodyBytes = [System.Text.Encoding]::UTF8.GetBytes($bodyJson)

        Write-Host "  Enviando a n8n ..." -ForegroundColor Cyan
        $response = Invoke-RestMethod `
            -Uri "$N8nUrl/api/v1/workflows/$WorkflowId" `
            -Method PUT `
            -Headers $Headers `
            -Body $bodyBytes `
            -ContentType "application/json; charset=utf-8" `
            -ErrorAction Stop

        Write-Host "  OK: $WorkflowName actualizado (id=$($response.id))" -ForegroundColor Green
        return $true
    } catch {
        Write-Host "  ERROR actualizando workflow: $_" -ForegroundColor Red
        return $false
    }
}

# ---- MAIN ----

Write-Host ""
Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host "  Actualizar Workflows en n8n (repo -> produccion)"     -ForegroundColor Cyan
Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host "Repo root: $RepoRoot" -ForegroundColor Gray

if (-not (Test-Path (Join-Path $RepoRoot "n8n-workflows"))) {
    Write-Host "ERROR: carpeta 'n8n-workflows' no encontrada en: $RepoRoot" -ForegroundColor Red
    return
}

if (-not $ApiKey) { $ApiKey = Get-N8nApiKey }
if (-not $ApiKey) {
    Write-Host "ERROR: API Key no proporcionada." -ForegroundColor Red
    return
}

$headers = @{
    "X-N8N-API-KEY" = $ApiKey
    "Content-Type"  = "application/json; charset=utf-8"
}

Write-Host ""
Write-Host "Verificando conexion a n8n ..." -ForegroundColor Cyan
try {
    Invoke-RestMethod -Uri "$N8nUrl/api/v1/workflows" -Headers $headers -ErrorAction Stop | Out-Null
    Write-Host "Conectado a: $N8nUrl" -ForegroundColor Green
} catch {
    Write-Host "ERROR: No se puede conectar a n8n: $_" -ForegroundColor Red
    return
}

$successCount = 0
foreach ($wf in $workflows) {
    $ok = Send-Workflow -WorkflowId $wf.Id -WorkflowName $wf.Name -JsonFile $wf.JsonFile -Headers $headers
    if ($ok) { $successCount++ }
}

Write-Host ""
Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host "  RESUMEN: $successCount de $($workflows.Count) workflows actualizados" -ForegroundColor Cyan
Write-Host "=======================================================" -ForegroundColor Cyan

if ($successCount -eq $workflows.Count) {
    Write-Host "Todos los workflows fueron actualizados exitosamente." -ForegroundColor Green
} else {
    Write-Host "Algunos workflows fallaron. Revisa los errores arriba." -ForegroundColor Red
}
