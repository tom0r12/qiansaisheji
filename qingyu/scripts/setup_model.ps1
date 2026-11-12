param(
    [switch]$SkipSmoke,
    [switch]$DownloadDataset,
    [switch]$PrepareReference
)

# Windows model reproduction. The newer TF 2.14 runtime is deliberately
# isolated from the original upstream TF 2.4.0rc1 environment.
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$modelEnvironment = Join-Path $projectRoot '.venv-model'
$python = Join-Path $modelEnvironment 'Scripts/python.exe'
$lock = Join-Path $projectRoot 'model/requirements-model-win-py311.resolved.lock.txt'
$repo = Join-Path $projectRoot 'vendor/keyword-transformer'
$pinnedCommit = '237e4097afd4f6851e0b82f0a8d65c2dfe8eae30'
$pythonVersion = '3.11.15'
$uv = (Get-Command uv -ErrorAction SilentlyContinue).Source
if (-not $uv) { $uv = Join-Path $env:USERPROFILE '.local/bin/uv.exe' }
if (-not (Test-Path -LiteralPath $uv)) {
    throw 'uv is required. Install uv from its official distribution and rerun this script.'
}
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw 'git is required.' }

function Invoke-Checked {
    param([string]$Executable, [string[]]$ArgumentList)
    & $Executable @ArgumentList
    if ($LASTEXITCODE -ne 0) { throw "$Executable exited with code $LASTEXITCODE" }
}

$previousNativeTls = $env:UV_NATIVE_TLS
$env:UV_NATIVE_TLS = 'true' # Use the Windows trust store; certificate validation remains enabled.
Push-Location $projectRoot
try {
    if (-not (Test-Path -LiteralPath $python)) {
        Invoke-Checked $uv @('venv', '--python', $pythonVersion, $modelEnvironment)
    } else {
        $actualPython = (& $python -c 'import platform; print(platform.python_version())').Trim()
        if ($LASTEXITCODE -ne 0 -or $actualPython -ne $pythonVersion) {
            throw "Existing $modelEnvironment uses $actualPython; expected $pythonVersion. Existing environment preserved."
        }
    }
    Invoke-Checked $uv @('pip', 'sync', '--python', $python, $lock)
    if (-not (Test-Path -LiteralPath (Join-Path $repo '.git'))) {
        Invoke-Checked 'git' @('clone', 'https://github.com/ARM-software/keyword-transformer.git', $repo)
    }
    $changes = & git -C $repo status --porcelain --untracked-files=no
    if ($LASTEXITCODE -ne 0 -or $changes) { throw 'Model checkout has tracked changes; preserve them before selecting the pinned commit.' }
    $head = (& git -C $repo rev-parse HEAD).Trim()
    if ($head -ne $pinnedCommit) {
        Invoke-Checked 'git' @('-C', $repo, 'checkout', '--detach', $pinnedCommit)
    }
    Invoke-Checked $python @('-c', 'import tensorflow as tf, tensorflow_addons as tfa, numpy as np; print({"tensorflow":tf.__version__, "addons":tfa.__version__, "numpy":np.__version__})')

    $build = Join-Path $projectRoot 'build'
    New-Item -ItemType Directory -Force -Path $build | Out-Null
    $smokeDirectory = $null
    if (-not $SkipSmoke) {
        $smokeDirectory = Join-Path $build ('model_smoke_' + (Get-Date -Format 'yyyyMMdd_HHmmss_fff'))
        Invoke-Checked $python @('-u', 'model/extract_kwt1.py', '--repo', $repo, '--silence-smoke', '--output', $smokeDirectory)
    }
    $record = [ordered]@{
        python = $pythonVersion
        interpreter = $python
        source_commit = $pinnedCommit
        lock_file = $lock
        lock_sha256 = (Get-FileHash -LiteralPath $lock -Algorithm SHA256).Hash.ToLowerInvariant()
        checkpoint_smoke = $smokeDirectory
        official_accuracy_evaluation = $false
        runtime_note = 'Python 3.11 / TF 2.14 reproduction; original upstream runtime used TF 2.4.0rc1.'
        timestamp_utc = (Get-Date).ToUniversalTime().ToString('o')
    }
    $record | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $build 'model_environment.json') -Encoding utf8
    if ($DownloadDataset -or $PrepareReference) {
        $downloadArguments = @('-u', 'model/download_speech_commands_v2.py', '--output',
            'data/downloads/speech_commands_v0.02.tar.gz')
        $extractionMarker = Join-Path $projectRoot 'data/speech_commands_v0.02/.qingyu_extraction.json'
        $alreadyExtracted = $false
        if (Test-Path -LiteralPath $extractionMarker) {
            $extraction = Get-Content -LiteralPath $extractionMarker -Raw | ConvertFrom-Json
            $alreadyExtracted = $extraction.state -eq 'extracted' -and $extraction.source_md5 -eq '6b74f3901214cb2c2934e98196829835'
        }
        if (-not $alreadyExtracted) { $downloadArguments += @('--extract-to', 'data/speech_commands_v0.02') }
        Invoke-Checked $python $downloadArguments
    }
    if ($PrepareReference) {
        $dataForModel = Join-Path $projectRoot 'data/speech_commands_v0.02'
        if ($dataForModel -match '[^\x00-\x7F]') {
            # TensorFlow 2.14 Win32 Glob cannot enumerate Unicode ancestors.
            # A same-volume ASCII junction preserves all official loader code.
            $hasher = [System.Security.Cryptography.SHA256]::Create()
            try {
                $pathHash = [BitConverter]::ToString($hasher.ComputeHash([Text.Encoding]::UTF8.GetBytes($dataForModel))).Replace('-', '').Substring(0, 12)
            } finally { $hasher.Dispose() }
            $aliasPath = Join-Path ([IO.Path]::GetPathRoot($dataForModel)) ('QingyuData_' + $pathHash)
            if (Test-Path -LiteralPath $aliasPath) {
                $aliasItem = Get-Item -LiteralPath $aliasPath -Force
                $targets = @($aliasItem.Target)
                if ($aliasItem.LinkType -ne 'Junction' -or $targets.Count -ne 1 -or $targets[0] -ne $dataForModel) {
                    throw "Existing $aliasPath is not the expected dataset junction; preserved."
                }
            } else {
                New-Item -ItemType Junction -Path $aliasPath -Target $dataForModel | Out-Null
            }
            $dataForModel = $aliasPath
        }
        $referenceDirectory = Join-Path $build ('model_reference_' + (Get-Date -Format 'yyyyMMdd_HHmmss_fff'))
        Invoke-Checked $python @('-u', 'model/run_reference_pipeline.py', '--repo', $repo,
            '--data-dir', $dataForModel, '--work', $referenceDirectory,
            '--training-count', '256', '--validation-count', '256')
        $out16 = Join-Path $referenceDirectory 'validation_vectors_out16'
        Invoke-Checked $python @('-u', 'model/validate_extracted.py', '--training',
            (Join-Path $referenceDirectory 'float_training'), '--validation',
            (Join-Path $referenceDirectory 'float_validation'), '--output', $out16,
            '--choose-by-layer-label', '--output-bits', '16', '--lanes', '16', '--scope',
            'Pinned official V2 training-only calibration and disjoint local 256-sample validation; not organizer 600')
        Invoke-Checked $python @('-u', 'model/export_soc_task_images.py', '--vectors', $out16,
            '--output', (Join-Path $referenceDirectory 'soc_images_out16'), '--expect-output-bits', '16')
        $record.reference_pipeline = $referenceDirectory
        $record.model_data_path = $dataForModel
        $record.timestamp_utc = (Get-Date).ToUniversalTime().ToString('o')
        $record | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $build 'model_environment.json') -Encoding utf8
    }
    Write-Output 'Model environment ready. Smoke outputs are synthetic and must not be used for calibration.'
} finally {
    Pop-Location
    $env:UV_NATIVE_TLS = $previousNativeTls
}
