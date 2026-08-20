# Starts Node-RED with the flows of the SDI-KIT.
#
# Credentials are asked for at startup, passed to the Node-RED process as an
# environment variable only, and neither stored nor echoed.
#
# Usage:  powershell -ExecutionPolicy Bypass -File start-nodered.ps1

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$repo = Resolve-Path "$PSScriptRoot\.."

# --- Take values from .env if present ---------------------------------------
$envFile = Join-Path $PSScriptRoot ".env"
if (Test-Path $envFile) {
    Get-Content $envFile -Encoding UTF8 | ForEach-Object {
        if ($_ -match '^\s*([A-Z0-9_]+)\s*=\s*(.*)$') {
            $name = $Matches[1]; $value = $Matches[2].Trim()
            if ($value) { Set-Item -Path "env:$name" -Value $value }
        }
    }
    Write-Host "Configuration taken from .env" -ForegroundColor Cyan
}

# --- Defaults for anything .env does not set --------------------------------
if (-not $env:SDI_AAS_URL)      { $env:SDI_AAS_URL = "http://localhost:8081" }
if (-not $env:SDI_AAS_BASE)     { $env:SDI_AAS_BASE = "localhost/demo/aas" }
if (-not $env:SDI_OPENLCA_URL)  { $env:SDI_OPENLCA_URL = "http://localhost:8080" }
if (-not $env:SDI_PYTHON)       { $env:SDI_PYTHON = "python" }
if (-not $env:SDI_EMA_SCRIPT)   { $env:SDI_EMA_SCRIPT = "$repo\src\ema_export_to_json.py" }
if (-not $env:SDI_EMA_EXPORT)   { $env:SDI_EMA_EXPORT = "$repo\docs\sample_data\ema_plantsimulation_data.xlsx" }

# --- Turn relative paths into absolute ones ----------------------------------
# The flows run with Node-RED's working directory, not with the repository as
# the reference point. A relative path in .env would therefore not resolve, and
# the flow would report empty input instead of a missing file.
foreach ($name in "SDI_EMA_SCRIPT", "SDI_EMA_EXPORT", "SDI_PLM_SCRIPT",
                  "SDI_PLM_BASE_SHELL", "SDI_PLM_OUTPUT", "SDI_PLM_WORK_DIR") {
    $wert = (Get-Item "env:$name" -ErrorAction SilentlyContinue).Value
    if ($wert -and -not [System.IO.Path]::IsPathRooted($wert)) {
        $absolut = Join-Path $PSScriptRoot $wert
        try { $absolut = (Resolve-Path $absolut -ErrorAction Stop).Path } catch { }
        Set-Item -Path "env:$name" -Value $absolut
        Write-Host "  $name resolved to $absolut" -ForegroundColor DarkGray
    }
}

# --- Ask for the Odoo key only if an ERP connection is configured ------------
if ($env:SDI_ODOO_DB -and -not $env:SDI_ODOO_APIKEY) {
    $secure = Read-Host -AsSecureString "Odoo API key (input is not shown)"
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    $env:SDI_ODOO_APIKEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
}

# --- Ask for the PLM password only if a PLM connection is configured --------
# A server without a user name is a half-filled configuration; say so rather
# than starting up and letting the flow fail with HTTP 401 later.
if ($env:SDI_PLM_URL -and -not $env:SDI_PLM_USER) {
    Write-Host "SDI_PLM_URL is set but SDI_PLM_USER is empty." -ForegroundColor Yellow
    Write-Host "  The PLM flow will fail with HTTP 401. Fill in SDI_PLM_USER in .env,"
    Write-Host "  or clear SDI_PLM_URL if you do not want to use the PLM connection."
    Write-Host ""
}
if ($env:SDI_PLM_USER -and -not $env:SDI_PLM_PASSWORD) {
    $secure = Read-Host -AsSecureString "PLM password for $env:SDI_PLM_USER (input is not shown)"
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    $env:SDI_PLM_PASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
}

Write-Host ""
Write-Host "Configuration:" -ForegroundColor Cyan
Write-Host "  AAS server     : $env:SDI_AAS_URL"
Write-Host "  openLCA        : $env:SDI_OPENLCA_URL"
Write-Host "  Product system : $(if ($env:SDI_OPENLCA_PRODUCT_SYSTEM) { $env:SDI_OPENLCA_PRODUCT_SYSTEM } else { 'not set' })"
Write-Host "  Odoo           : $(if ($env:SDI_ODOO_DB) { $env:SDI_ODOO_DB } else { 'not configured' })"
Write-Host "  PLM            : $(if ($env:SDI_PLM_URL) { $env:SDI_PLM_URL } else { 'not configured' })"
Write-Host ""
Write-Host "Node-RED is starting on http://localhost:1880 ..." -ForegroundColor Cyan

# The output is written to a log file as well, so a run can be looked at
# afterwards without scrolling back through the console.
$logFile = Join-Path $PSScriptRoot "nodered\node-red.log"
Write-Host "  Log            : $logFile"
Write-Host ""

# Tee-Object of Windows PowerShell 5.1 has no -Encoding parameter and would
# write UTF-16. Writing each line explicitly keeps the log readable.
Set-Content -Path $logFile -Value "" -Encoding UTF8
node-red -u "$PSScriptRoot\nodered" -s "$PSScriptRoot\nodered\settings.js" 2>&1 |
    ForEach-Object {
        Write-Host $_
        # Writing the log must never stop the server. A single failed write -
        # the file briefly locked by another program, for instance - would
        # otherwise end the pipeline and take Node-RED down with it, in the
        # middle of a run and without any hint of the real cause.
        try {
            Add-Content -Path $logFile -Value ([string]$_) -Encoding UTF8 -ErrorAction Stop
        } catch {
            Write-Host "  (log line could not be written: $($_.Exception.Message))"
        }
    }
