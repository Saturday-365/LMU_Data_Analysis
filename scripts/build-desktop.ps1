param(
    [string]$Python,
    [string]$Dist = 'dist',
    [string]$Build = 'build'
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $Python) {
    $Python = Join-Path $projectRoot '.venv/Scripts/python.exe'
}
$Python = (Resolve-Path -LiteralPath $Python).Path

Push-Location -LiteralPath $projectRoot
try {
    $webDir = (Resolve-Path -LiteralPath 'web').Path
    $buildDir = New-Item -ItemType Directory -Path $Build -Force
    $distDir = New-Item -ItemType Directory -Path $Dist -Force
    $name = 'LMU-Data-Analysis-v0.4'
    # 目录版保留 DLL 和 WebView2 资源，用户可直接解压运行。
    & $Python -B -m PyInstaller --noconfirm --onedir --windowed `
        --name $name --paths 'src' --add-data "${webDir}:web" `
        --specpath $buildDir.FullName --workpath $buildDir.FullName --distpath $distDir.FullName `
        'scripts/desktop_app.py'
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
    Copy-Item -LiteralPath 'docs/desktop-v0.4.md' -Destination (Join-Path $distDir.FullName "$name/README.md")
}
finally {
    Pop-Location
}
