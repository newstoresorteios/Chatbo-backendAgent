# Cria 1 pedido de teste no Mercos sandbox via PulseDesk
# Uso: powershell -ExecutionPolicy Bypass -File .\scripts\test_criar_pedido.ps1

$ErrorActionPreference = "Stop"
$BaseUrl = "https://xnamai-backendagent.onrender.com/api"

Write-Host "1) Login..." -ForegroundColor Cyan
$loginBody = '{"email":"admin@pulsedesk.com","password":"admin123"}'
$login = Invoke-RestMethod -Uri "$BaseUrl/auth/login" -Method POST -ContentType "application/json" -Body $loginBody

$token = $login.token
if (-not $token) { $token = $login.access_token }
if (-not $token) { $token = $login.accessToken }
if (-not $token) {
  Write-Host "Nao achei token. Resposta do login:" -ForegroundColor Red
  $login | ConvertTo-Json -Depth 5
  exit 1
}
Write-Host "Login OK" -ForegroundColor Green

$headers = @{
  Authorization = "Bearer $token"
  "Content-Type" = "application/json"
}

# IDs reais do sandbox XNAMAI
$pedidoJson = @"
{
  "cliente_id": 9282664,
  "data_emissao": "2026-07-09",
  "condicao_pagamento": "a vista",
  "observacoes": "Teste PulseDesk homologacao",
  "itens": [
    {
      "produto_id": 20386166,
      "quantidade": 1,
      "preco_tabela": 29.9
    }
  ]
}
"@

Write-Host "2) Criando pedido (cliente 9282664 / produto Cabo HDMI 20386166)..." -ForegroundColor Cyan
try {
  $resultado = Invoke-RestMethod -Uri "$BaseUrl/mercos/pedidos" -Method POST -Headers $headers -Body $pedidoJson
  Write-Host "SUCESSO" -ForegroundColor Green
  $resultado | ConvertTo-Json -Depth 8
}
catch {
  Write-Host "FALHOU" -ForegroundColor Red
  Write-Host $_.Exception.Message
  if ($_.ErrorDetails.Message) {
    Write-Host $_.ErrorDetails.Message
  }
  exit 1
}
