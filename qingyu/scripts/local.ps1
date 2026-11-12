#requires -Version 5.1
<#
.SYNOPSIS
Run project checks in WSL without modifying global PATH.
.EXAMPLE
./scripts/local.ps1 model-tests
.EXAMPLE
./scripts/local.ps1 candidate-checks --cases 12 --candidate experiments/h1500v/opt14_ybank2/rtl
.EXAMPLE
./scripts/local.ps1 candidate-fast --cases 12
.EXAMPLE
./scripts/local.ps1 soc --candidate opt25_fused4 --layers 12
.EXAMPLE
./scripts/local.ps1 soc-queue --candidate opt30_fusedpipe4 --layers 12
#>
[CmdletBinding(PositionalBinding=$false)]
param(
    [Parameter(Position=0)]
    [ValidateSet('model-tests','candidate-checks','candidate-fast','soc','soc-queue','soc-legacy','fio-faults','queue-faults','fused-wait','fused-pipe')]
    [string]$Command = 'model-tests',
    [string]$Distribution,
    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$CommandArgs = @()
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$ConfigPath = Join-Path $ProjectRoot 'tool-config.local.json'
if (-not $Distribution -and (Test-Path -LiteralPath $ConfigPath)) {
    $Config = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
    $Distribution = $Config.wsl.distribution
}
if (-not $Distribution) { $Distribution = 'Ubuntu' }
if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
    throw 'WSL is unavailable. Run scripts/setup_local.ps1 after initializing Ubuntu.'
}
# Windows PowerShell 5 treats native stderr as an ErrorRecord even when the
# process succeeds. A WSL startup proxy warning must not terminate path lookup.
$SavedErrorActionPreference = $ErrorActionPreference
try {
    $ErrorActionPreference = 'Continue'
    $Paths = & wsl.exe --distribution $Distribution --exec wslpath -a -u $ProjectRoot 2>$null
    $PathExitCode = $LASTEXITCODE
} finally {
    $ErrorActionPreference = $SavedErrorActionPreference
}
if ($PathExitCode -ne 0) { throw "Cannot access WSL distribution $Distribution." }
$LinuxRoot = @($Paths | Where-Object { ([string]$_).StartsWith('/') }) | Select-Object -Last 1
if (-not $LinuxRoot) { throw 'WSL did not return the project path.' }

switch ($Command) {
    'model-tests'     { $PythonArgs = @('-m','unittest','discover','-s','model','-p','test_*.py','-v') }
    'candidate-checks'{ $PythonArgs = @('scripts/run_candidate_checks.py') }
    'candidate-fast'  { $PythonArgs = @('scripts/run_candidate_checks.py','--fast-consumer') }
    'soc'             { $PythonArgs = @('scripts/run_bus_candidate_soc.py') }
    'soc-queue'       { $PythonArgs = @('scripts/run_bus_queue_candidate_soc.py') }
    'soc-legacy'      { $PythonArgs = @('scripts/run_candidate_soc.py') }
    'fio-faults'      { $PythonArgs = @('scripts/run_fio_fault_checks.py') }
    'queue-faults'    { $PythonArgs = @('scripts/run_fio_queue_fault_checks.py') }
    'fused-wait'      { $PythonArgs = @('scripts/run_fused_wait_checks.py') }
    'fused-pipe'      { $PythonArgs = @('scripts/run_fused_pipe_checks.py') }
}
$PythonArgs += $CommandArgs
Write-Host "[$Distribution] python3 $($PythonArgs -join ' ')"
try {
    $ErrorActionPreference = 'Continue'
    & wsl.exe --distribution $Distribution --cd ([string]$LinuxRoot).Trim() --exec python3 @PythonArgs
    $RunExitCode = $LASTEXITCODE
} finally {
    $ErrorActionPreference = $SavedErrorActionPreference
}
exit $RunExitCode
