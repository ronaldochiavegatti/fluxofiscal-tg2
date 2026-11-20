# Empacota a pasta app/ (do jeito que está no disco, incluindo mudanças ainda
# não commitadas) e envia para a VPS. Rode no PowerShell, da pasta app/:
#
#   .\deploy\enviar.ps1 -Ip 203.0.113.10
#
# Não envia .env (a VPS gera o próprio, com segredos novos), node_modules,
# builds nem caches. Os volumes da VPS (bancos) são preservados.
param(
    [Parameter(Mandatory = $true)][string]$Ip,
    [string]$Usuario = "root",
    [string]$Destino = "/opt/fluxofiscal"
)
$ErrorActionPreference = "Stop"

$app = Split-Path -Parent $PSScriptRoot
$pacote = Join-Path $env:TEMP "fluxofiscal-deploy.tgz"

Write-Host "==> Empacotando $app"
# tar.exe do Windows explícito: o do Git Bash, se vier antes no PATH, lê
# "C:\..." como host remoto e falha.
& "$env:SystemRoot\System32\tar.exe" -czf $pacote -C $app `
    --exclude=node_modules --exclude=dist --exclude=coverage `
    --exclude=.env --exclude=docker-compose.override.yml `
    --exclude=__pycache__ --exclude=.pytest_cache --exclude=.mypy_cache `
    --exclude=.ruff_cache --exclude=.venv --exclude=venv --exclude=htmlcov `
    --exclude=.coverage --exclude=mutants --exclude=.mutmut-cache .
if ($LASTEXITCODE -ne 0) { throw "tar falhou" }
"{0:N1} MB" -f ((Get-Item $pacote).Length / 1MB) | Write-Host

Write-Host "==> Enviando para ${Usuario}@${Ip}:$Destino"
scp $pacote "${Usuario}@${Ip}:/tmp/fluxofiscal-deploy.tgz"
if ($LASTEXITCODE -ne 0) { throw "scp falhou" }

# Extrai por cima (o .env da VPS não está no pacote, então sobrevive).
ssh "${Usuario}@${Ip}" "mkdir -p $Destino && tar -xzf /tmp/fluxofiscal-deploy.tgz -C $Destino && rm /tmp/fluxofiscal-deploy.tgz && sed -i 's/\r$//' $Destino/deploy/instalar.sh"
if ($LASTEXITCODE -ne 0) { throw "extração na VPS falhou" }

Write-Host ""
Write-Host "==> Código na VPS. Para instalar/atualizar:"
Write-Host "    ssh ${Usuario}@${Ip}"
Write-Host "    cd $Destino && bash deploy/instalar.sh"
