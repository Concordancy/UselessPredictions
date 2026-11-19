# Runs the database scripts against the server named in the credentials file.
# Usage:  .\Deploy.ps1                (schema + seed)
#         .\Deploy.ps1 -Scripts Seed.sql
param(
    [string]   $CredentialsPath = (Join-Path $PSScriptRoot '..\..\UPCredentials.txt'),
    [string[]] $Scripts         = @('Schema.sql', 'Seed.sql')
)

$ErrorActionPreference = 'Stop'

$line = Get-Content -LiteralPath $CredentialsPath | Where-Object { $_ -match '^\s*DBUPData\s*=' } | Select-Object -First 1
if (-not $line) { throw "No DBUPData entry found in $CredentialsPath" }

$settings = @{}
[regex]::Match($line, '"(.+)"').Groups[1].Value.Split(';') | ForEach-Object {
    $pair = $_.Split('=', 2)
    if ($pair.Count -eq 2) { $settings[$pair[0].Trim()] = $pair[1].Trim() }
}

$env:SQLCMDPASSWORD = $settings['Password']
try {
    foreach ($script in $Scripts) {
        $path = Join-Path $PSScriptRoot $script
        Write-Host "Running $script ..."
        # -b stop on error, -I quoted identifiers on, -C trust server certificate, -f 65001 UTF-8 input
        & sqlcmd -S $settings['Data Source'] -d $settings['Initial Catalog'] -U $settings['User ID'] -b -I -C -f 65001 -i $path
        if ($LASTEXITCODE -ne 0) { throw "$script failed (sqlcmd exit code $LASTEXITCODE)" }
    }
    Write-Host 'Done.'
}
finally {
    Remove-Item Env:SQLCMDPASSWORD -ErrorAction SilentlyContinue
}
