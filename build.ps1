param(
 [ValidateSet('x64','x86')][string]$Platform = 'x86',
 [string]$OutputDirectory = ''
)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$compiler = Join-Path $env:WINDIR 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
$framework = Split-Path $compiler
$metadata = Join-Path $env:WINDIR 'System32/WinMetadata'
$out = if ($OutputDirectory) { $OutputDirectory } else { Join-Path $root 'dist' }
New-Item -ItemType Directory -Path $out -Force | Out-Null
$references = @(
 'System.dll','System.Core.dll','System.Drawing.dll','System.Windows.Forms.dll',
 'System.Runtime.Serialization.dll','Microsoft.CSharp.dll',
 (Join-Path $framework 'System.Runtime.WindowsRuntime.dll'),
 (Join-Path $framework 'System.Runtime.dll'),
 (Join-Path $framework 'System.Runtime.InteropServices.WindowsRuntime.dll'),
 (Join-Path $metadata 'Windows.Foundation.winmd'),
 (Join-Path $metadata 'Windows.Devices.winmd')
)
$arguments = @('/nologo','/target:winexe',('/platform:' + $Platform),'/optimize+','/debug-',
 ('/out:' + (Join-Path $out 'Chargeview.Native.exe')),
 ('/win32icon:' + (Join-Path $root 'packaging/Chargeview.ico')))
$arguments += $references | ForEach-Object { '/reference:' + $_ }
$arguments += (Get-ChildItem -LiteralPath (Join-Path $root 'src') -Filter '*.cs').FullName
& $compiler @arguments
if ($LASTEXITCODE -ne 0) { throw 'Compilation failed' }
Get-Item -LiteralPath (Join-Path $out 'Chargeview.Native.exe') | Select-Object Name,Length

