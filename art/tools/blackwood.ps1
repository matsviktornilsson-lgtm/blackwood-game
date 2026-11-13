#Requires -Version 7.3
$ErrorActionPreference = 'Stop'
$PSNativeCommandArgumentPassing = 'Standard'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$configPath = if ($env:BLACKWOOD_CONFIG) { $env:BLACKWOOD_CONFIG } else { Join-Path $PSScriptRoot 'blackwood.config.local.json' }
$examplePath = Join-Path $PSScriptRoot 'blackwood.config.example.json'
if (!(Test-Path -LiteralPath $configPath -PathType Leaf)) {
    if ($env:BLACKWOOD_CONFIG) { throw "CONFIG_MISSING: $configPath" }
    $configPath = $examplePath
}
$configPath = (Resolve-Path -LiteralPath $configPath).Path
$config = Get-Content -LiteralPath $configPath -Raw -Encoding utf8 | ConvertFrom-Json
$python = $config.python
if (!$python -or ![IO.Path]::IsPathFullyQualified($python) -or
    [IO.Path]::GetExtension($python) -ine '.exe' -or !(Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "PYTHON_MISSING: set python to a verified Windows executable in $configPath"
}
& $python -B -X utf8 (Join-Path $PSScriptRoot 'blackwood.py') --config $configPath @args
exit $LASTEXITCODE
