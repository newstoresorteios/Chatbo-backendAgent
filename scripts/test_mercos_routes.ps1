# Testa rotas Mercos do PulseDesk (sandbox via backend)
# Uso:
#   $env:MERCOS_TEST_EMAIL="admin@..."
#   $env:MERCOS_TEST_PASSWORD="..."
#   $env:MERCOS_TEST_BASE_URL="https://seu-backend.onrender.com/api"  # opcional
#   .\scripts\test_mercos_routes.ps1

$ErrorActionPreference = "Stop"

$BaseUrl = if ($env:MERCOS_TEST_BASE_URL) { $env:MERCOS_TEST_BASE_URL } else { "https://xnamai-backendagent.onrender.com/api" }
$Email = $env:MERCOS_TEST_EMAIL
$Password = $env:MERCOS_TEST_PASSWORD

if (-not $Email -or -not $Password) {
  Write-Host "Defina MERCOS_TEST_EMAIL e MERCOS_TEST_PASSWORD no ambiente." -ForegroundColor Red
  exit 1
}

Write-Host ""
Write-Host "=== 1) Login PulseDesk ===" -ForegroundColor Cyan
$login = Invoke-RestMethod `
  -Uri "$BaseUrl/auth/login" `
  -Method POST `
  -ContentType "application/json" `
  -Body (@{ email = $Email; password = $Password } | ConvertTo-Json)

$token = $null
if ($login.token) { $token = $login.token }
elseif ($login.access_token) { $token = $login.access_token }
elseif ($login.accessToken) { $token = $login.accessToken }

if (-not $token) {
  Write-Host "Login OK, mas nao achei o token. Resposta:" -ForegroundColor Yellow
  $login | ConvertTo-Json -Depth 5
  exit 1
}

$headers = @{ Authorization = "Bearer $token" }
Write-Host "Token OK" -ForegroundColor Green

function Test-Get($nome, $path) {
  Write-Host ""
  Write-Host "=== GET $path ($nome) ===" -ForegroundColor Cyan
  try {
    $r = Invoke-RestMethod -Uri "$BaseUrl$path" -Headers $headers -Method GET
    if ($r -is [System.Array]) {
      Write-Host "OK - $($r.Count) registro(s)" -ForegroundColor Green
    }
    elseif ($r.prontoParaHomologacao -ne $null) {
      Write-Host "OK - prontoParaHomologacao=$($r.prontoParaHomologacao)" -ForegroundColor Green
      $r | ConvertTo-Json -Depth 6
    }
    else {
      Write-Host "OK" -ForegroundColor Green
      ($r | ConvertTo-Json -Depth 4).Substring(0, [Math]::Min(400, ($r | ConvertTo-Json -Depth 4).Length))
    }
  }
  catch {
    Write-Host "FALHOU: $($_.Exception.Message)" -ForegroundColor Red
    if ($_.ErrorDetails.Message) { Write-Host $_.ErrorDetails.Message }
  }
}

Test-Get "clientes" "/mercos/clientes"
Test-Get "produtos" "/mercos/produtos"
Test-Get "pedidos" "/mercos/pedidos"
Test-Get "categorias" "/mercos/categorias"
Test-Get "segmentos" "/mercos/segmentos"
Test-Get "tipos-pedido" "/mercos/tipos-pedido"
Test-Get "tabelas-preco" "/mercos/tabelas-preco"
Test-Get "produtos-tabela-preco" "/mercos/produtos-tabela-preco"
Test-Get "condicoes-pagamento" "/mercos/condicoes-pagamento"
Test-Get "usuarios-mercos" "/mercos/usuarios-mercos"
Test-Get "transportadoras" "/mercos/transportadoras"
Test-Get "politicas-comerciais" "/mercos/politicas-comerciais"
Test-Get "homologacao" "/mercos/homologacao"

Write-Host ""
Write-Host "=== Fim dos testes de leitura ===" -ForegroundColor Cyan
Write-Host "Para testar POST de pedido, use IDs reais de cliente/produto do sandbox." -ForegroundColor Yellow
Write-Host ""
