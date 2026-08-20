# Creates the sample master data in an Odoo instance.
#
# Reads the connection details from .env, asks for the API key at startup and
# passes it to the Python script as an environment variable only. The key is
# neither stored nor echoed.
#
# The script creates the custom fields, the products with their weights and
# materials, the bill of material and a manufacturing order - all taken from
# the PLM export in docs/sample_data. It is repeatable: existing records are
# updated rather than duplicated.
#
# Usage:  powershell -ExecutionPolicy Bypass -File setup-odoo.ps1
#
# Copyright (c) 2025 Heinz Nixdorf Institute
# Copyright (c) 2025 Paderborn University
# Copyright (c) 2025 Contributors to the Eclipse Foundation
#
# See the NOTICE file(s) distributed with this work for additional
# information regarding copyright ownership.
#
# This program and the accompanying materials are made available under the
# terms of the Apache License, Version 2.0 which is available at
# https://www.apache.org/licenses/LICENSE-2.0.
#
# SPDX-License-Identifier: Apache-2.0

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$repo = Resolve-Path "$PSScriptRoot\.."

# --- Take values from .env --------------------------------------------------
$envFile = Join-Path $PSScriptRoot ".env"
if (-not (Test-Path $envFile)) {
    Write-Host "No .env found." -ForegroundColor Red
    Write-Host "Copy .env.example to .env and fill in the ERP section first:"
    Write-Host "  copy .env.example .env"
    exit 1
}
Get-Content $envFile -Encoding UTF8 | ForEach-Object {
    if ($_ -match '^\s*([A-Z0-9_]+)\s*=\s*(.*)$') {
        $name = $Matches[1]; $value = $Matches[2].Trim()
        if ($value) { Set-Item -Path "env:$name" -Value $value }
    }
}

# --- Check what is needed ---------------------------------------------------
$missing = @()
foreach ($name in "SDI_ODOO_URL", "SDI_ODOO_DB", "SDI_ODOO_USER") {
    if (-not (Get-Item "env:$name" -ErrorAction SilentlyContinue)) { $missing += $name }
}
if ($missing.Count -gt 0) {
    Write-Host "Missing in .env: $($missing -join ', ')" -ForegroundColor Red
    exit 1
}

# --- Ask for the API key ----------------------------------------------------
# Create it in Odoo under Settings -> Users -> Account Security -> New API Key.
if (-not $env:SDI_ODOO_APIKEY) {
    $secure = Read-Host -AsSecureString "Odoo API key (input is not shown)"
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    $env:SDI_ODOO_APIKEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
}
if (-not $env:SDI_ODOO_APIKEY) {
    Write-Host "No API key entered - stopping." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Connection:" -ForegroundColor Cyan
Write-Host "  Server   : $env:SDI_ODOO_URL"
Write-Host "  Database : $env:SDI_ODOO_DB"
Write-Host "  User     : $env:SDI_ODOO_USER"
Write-Host ""

python "$repo\src\setup_odoo_testdata.py"

# The key lives only in this process; it is dropped when the window closes.
$env:SDI_ODOO_APIKEY = $null
