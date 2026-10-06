param(
    [string]$OutputRoot = "",
    [string]$PythonExe = "python",
    [string]$Version = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $Version) { $Version = (Get-Content -LiteralPath (Join-Path $ProjectRoot 'VERSION') -Raw).Trim() }
if ($Version -notmatch '^\d+\.\d+\.\d+$') { throw 'Version must be major.minor.patch' }
if (-not $OutputRoot) {
    $OutputRoot = Join-Path $ProjectRoot "portable-output"
}
$OutputRoot = [System.IO.Path]::GetFullPath($OutputRoot)
$BuildRoot = Join-Path $ProjectRoot "build"
$DistRoot = Join-Path $ProjectRoot "dist"
$PackageTarget = Join-Path $OutputRoot "WeChatStrategist"
$ZipPath = Join-Path $OutputRoot ("DeskBuddy-" + $Version + "-Windows.zip")
# Never recursively remove a user-selected output path or overwrite a package.
if ((Test-Path -LiteralPath $PackageTarget) -or (Test-Path -LiteralPath $ZipPath)) {
    throw 'Package output already exists. Select another output directory.'
}

& $PythonExe -m PyInstaller --version | Out-Null
if ($LASTEXITCODE -ne 0) { throw "PyInstaller is not installed for the active Python" }
Push-Location -LiteralPath $ProjectRoot
try {
    # Build the maintained relative-path spec; do not regenerate a spec containing
    # the developer's absolute source paths or modify tracked files during builds.
    & $PythonExe -m PyInstaller --noconfirm --clean `
        --workpath $BuildRoot --distpath $DistRoot `
        (Join-Path $ProjectRoot 'WeChatStrategist.spec')
} finally {
    Pop-Location
}
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }

$PackageSource = Join-Path $DistRoot "WeChatStrategist"
if (-not (Test-Path -LiteralPath $PackageSource -PathType Container)) {
    throw "Built package directory not found"
}
New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null
Copy-Item -LiteralPath $PackageSource -Destination $PackageTarget -Recurse
Copy-Item -LiteralPath (Join-Path $ProjectRoot '首次使用说明.txt') -Destination $PackageTarget
Copy-Item -LiteralPath (Join-Path $ProjectRoot "LICENSE") -Destination $PackageTarget
Copy-Item -LiteralPath (Join-Path $ProjectRoot "README.zh-CN.md") -Destination $PackageTarget
foreach ($DocName in @('README.md', 'CHANGELOG.md', 'VERSION', 'SECURITY.md')) {
    Copy-Item -LiteralPath (Join-Path $ProjectRoot $DocName) -Destination $PackageTarget
}
New-Item -ItemType Directory -Path (Join-Path $PackageTarget 'docs') | Out-Null
foreach ($DocName in @('ARCHITECTURE.md', 'PRIVACY.md', 'FAQ.md')) {
    Copy-Item -LiteralPath (Join-Path $ProjectRoot ('docs\' + $DocName)) -Destination (Join-Path $PackageTarget 'docs')
}
Copy-Item -LiteralPath (Join-Path $ProjectRoot '重新配置.bat') -Destination $PackageTarget

$PrivateNames = @('config.json', '.env', 'ui_state.json', 'debug_last.png', 'profiles', '.upgrades')
Get-ChildItem -LiteralPath $PackageTarget -Recurse -File -Force | ForEach-Object {
    $Relative = $_.FullName.Substring($PackageTarget.Length + 1)
    foreach ($Part in ($Relative -split '[\\/]')) {
        if ($Part -in $PrivateNames -or $Part -like '.env.*' -or $Part -like '*.log' -or $Part -like '*.log.1') {
            throw "Private runtime artifact in portable package: $Relative"
        }
    }
}
Compress-Archive -LiteralPath $PackageTarget -DestinationPath $ZipPath -CompressionLevel Optimal
Write-Output $ZipPath
