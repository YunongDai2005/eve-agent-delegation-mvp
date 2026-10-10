$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$env:PUPPETEER_SKIP_DOWNLOAD = 'true'
# Adjust executablePath in this config for your installed Chromium browser.
foreach ($name in @('architecture', 'langgraph')) {
    npm.cmd exec --yes --package=@mermaid-js/mermaid-cli@12.0.0 -- mmdc -i "docs/$name.mmd" -o "docs/$name.svg" -p docs/puppeteer.example.json -b white
    if ($LASTEXITCODE -ne 0) { throw "Mermaid export failed: $name" }
}
npm.cmd exec --yes --package=@mermaid-js/mermaid-cli@12.0.0 -- mmdc -i docs/architecture.mmd -o docs/architecture.png -p docs/puppeteer.example.json -b white
if ($LASTEXITCODE -ne 0) { throw 'Mermaid PNG export failed' }
