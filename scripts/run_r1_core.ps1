$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $RepoRoot
$ReceiptRoot = Join-Path $RepoRoot 'results\r1-action'
$WorkRoot = Join-Path $RepoRoot '.r1'
New-Item -ItemType Directory -Force -Path $ReceiptRoot, $WorkRoot | Out-Null

$RunStatus = 'failed'
$RunError = $null

function Invoke-Checked {
    param([scriptblock]$Command, [string]$Message)
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "$Message (exit $LASTEXITCODE)" }
}

function Write-Receipt {
    param([string]$Name, [hashtable]$Value)
    $Value | ConvertTo-Json -Depth 12 | Set-Content (Join-Path $ReceiptRoot $Name) -Encoding utf8
}

try {
    # --- CPython 3.12.13 source identity ---
    $PythonUrl = 'https://www.python.org/ftp/python/3.12.13/Python-3.12.13.tgz'
    $PythonArchive = Join-Path $env:RUNNER_TEMP 'Python-3.12.13.tgz'
    Invoke-Checked { curl.exe -L --fail --retry 5 --retry-delay 2 -o $PythonArchive $PythonUrl } 'CPython source download failed'
    $ExpectedPythonSha = '0816c4761c97ecdb3f50a3924de0a93fd78cb63ee8e6c04201ddfaedca500b0b'
    $PythonSha = (Get-FileHash $PythonArchive -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($PythonSha -ne $ExpectedPythonSha) { throw "CPython source hash mismatch: $PythonSha" }
    Write-Receipt 'python-source.json' @{
        schema='ascom-00323-python-source/v1'; version='3.12.13'; source_url=$PythonUrl;
        sha256=$PythonSha; expected_sha256=$ExpectedPythonSha; status='verified'
    }

    $PythonSrc = Join-Path $env:RUNNER_TEMP 'Python-3.12.13'
    if (Test-Path $PythonSrc) { Remove-Item $PythonSrc -Recurse -Force }
    Invoke-Checked { tar.exe -xf $PythonArchive -C $env:RUNNER_TEMP } 'CPython source extraction failed'

    # Python 3.12.13 predates Visual Studio 18. Use PCbuild's documented response-file
    # path to select the current VS18/VS2026 v145 toolset without modifying CPython source.
    Set-Content (Join-Path $PythonSrc 'PCbuild\msbuild.rsp') '/p:PlatformToolset=v145' -Encoding ascii
    Push-Location $PythonSrc
    try {
        Invoke-Checked { & .\PCbuild\build.bat -p x64 -c Release } 'CPython 3.12.13 build failed'
    } finally { Pop-Location }

    $R1Python = Join-Path $PythonSrc 'PCbuild\amd64\python.exe'
    if (-not (Test-Path $R1Python)) { throw "built Python missing: $R1Python" }
    $PythonVersion = (& $R1Python -c "import platform; print(platform.python_version())").Trim()
    if ($LASTEXITCODE -ne 0 -or $PythonVersion -ne '3.12.13') { throw "expected Python 3.12.13, got $PythonVersion" }
    Write-Receipt 'python-build.json' @{
        schema='ascom-00323-python-build/v1'; version=$PythonVersion; platform_toolset='v145';
        source='official CPython 3.12.13 source tarball'; status='verified'
    }

    # --- Exact public dependencies ---
    Invoke-Checked { & $R1Python -m ensurepip --upgrade } 'ensurepip failed'
    Invoke-Checked { & $R1Python -m pip install --upgrade pip setuptools wheel } 'pip bootstrap failed'
    Invoke-Checked { & $R1Python -m pip install pytest==9.0.3 numpy==2.4.4 scipy==1.17.1 PyYAML==6.0.3 } 'core dependency install failed'
    Invoke-Checked { & $R1Python -m pip install cobaya==3.6.2 mpi4py==4.1.2 sacc==2.1.2 getdist==1.7.7 astropy==7.2.0 } 'scientific dependency install failed'

    # --- CAMB public release identity + historical lineage ---
    # The frozen 4e38... SHA belongs to the source wheel recorded by the 2026-08-02
    # Linux/CPython-3.13 platform port. It is provenance lineage, not an expected byte
    # identity for today's public Windows PyPI wheel. R1 therefore preserves that hash
    # while validating the public Windows artifact by version, upstream release commit,
    # importability and numerical replay.
    $HistoricalSourceWheelSha = '4e38c3771329b2d4f5c185f8d8d7a0f183178d5b07957f18f9008f90e7d4b79d'
    $CambCommitExpected = '3ef0272d6f7ba1231128872e56e6d4c12af8267b'

    $CambSource = Join-Path $WorkRoot 'CAMB-source'
    if (Test-Path $CambSource) { Remove-Item $CambSource -Recurse -Force }
    Invoke-Checked { git clone --filter=blob:none https://github.com/cmbant/CAMB.git $CambSource } 'CAMB clone failed'
    Invoke-Checked { git -C $CambSource checkout --detach $CambCommitExpected } 'CAMB frozen source checkout failed'
    $CambHead = (git -C $CambSource rev-parse HEAD).Trim()
    if ($CambHead -ne $CambCommitExpected) { throw "CAMB source mismatch: $CambHead" }
    Write-Receipt 'camb-source.json' @{
        schema='ascom-00323-camb-source-provenance/v2'; version='1.6.6';
        repository='https://github.com/cmbant/CAMB.git'; commit=$CambHead;
        expected_commit=$CambCommitExpected; status='verified'
    }

    $Wheelhouse = Join-Path $WorkRoot 'wheelhouse'
    New-Item -ItemType Directory -Force -Path $Wheelhouse | Out-Null
    Invoke-Checked { & $R1Python -m pip download camb==1.6.6 --only-binary=:all: --no-deps -d $Wheelhouse } 'CAMB public wheel download failed'
    $Wheel = Get-ChildItem $Wheelhouse -Filter 'camb*.whl' | Select-Object -First 1
    if (-not $Wheel) { throw 'CAMB public Windows wheel not found' }
    $PublicWheelSha = (Get-FileHash $Wheel.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    Write-Receipt 'camb-wheel.json' @{
        schema='ascom-00323-camb-wheel/v2'; version='1.6.6'; file=$Wheel.Name;
        public_windows_pypi_sha256=$PublicWheelSha;
        historical_source_wheel_sha256=$HistoricalSourceWheelSha;
        historical_source_wheel_lineage='PEER_CAMB_PLATFORM_PORT_20260802 Linux x86_64 / CPython 3.13 source artifact';
        relation='historical source-wheel byte identity is not expected to equal the public Windows PyPI wheel';
        status='recorded'
    }
    Invoke-Checked { & $R1Python -m pip install $Wheel.FullName } 'CAMB public wheel install failed'
    $CambInstalledVersion = (& $R1Python -c "import camb; print(camb.__version__)").Trim()
    if ($LASTEXITCODE -ne 0 -or $CambInstalledVersion -ne '1.6.6') { throw "CAMB expected 1.6.6, got $CambInstalledVersion" }
    Write-Receipt 'camb-installed.json' @{
        schema='ascom-00323-camb-installed/v1'; version=$CambInstalledVersion;
        wheel_sha256=$PublicWheelSha; upstream_release_commit=$CambHead; status='verified'
    }

    # --- Exact host / harness ---
    Invoke-Checked { & $R1Python scripts\doctor.py --strict --output (Join-Path $ReceiptRoot 'doctor.json') } 'strict environment doctor failed'
    Invoke-Checked { & $R1Python -m pytest -q } 'public harness pytest failed'
    Invoke-Checked { & $R1Python scripts\verify_artifact.py } 'artifact verification failed'
    Invoke-Checked { & $R1Python scripts\r1_core_probe.py --receipt (Join-Path $ReceiptRoot 'camb-repeatability.json') } 'CAMB repeatability probe failed'

    # --- ACT public reconstruction ---
    $ActUrl = 'https://lambda.gsfc.nasa.gov/data/act/pspipe/sacc_files/dr6_data_cmbonly.tar.gz'
    $ActArchive = Join-Path $env:RUNNER_TEMP 'dr6_data_cmbonly.tar.gz'
    Invoke-Checked { curl.exe -L --fail --retry 5 --retry-delay 2 -o $ActArchive $ActUrl } 'ACT public download failed'
    $ActDest = Join-Path $env:RUNNER_TEMP 'act-public-r1'
    if (Test-Path $ActDest) { Remove-Item $ActDest -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $ActDest | Out-Null
    Invoke-Checked { tar.exe -xf $ActArchive -C $ActDest } 'ACT archive extraction failed'
    $ActFits = Get-ChildItem $ActDest -Recurse -Filter 'dr6_data_cmbonly.fits' | Select-Object -First 1
    if (-not $ActFits) { throw 'ACT FITS not found after extraction' }
    Invoke-Checked {
        & $R1Python scripts\act_public_payload.py $ActFits.FullName --output (Join-Path $WorkRoot 'act_dr6_cmbonly.bin') --receipt (Join-Path $ReceiptRoot 'act-public-reconstruction.json')
    } 'ACT public reconstruction mismatch'

    # --- DESI public identity ---
    $BaoData = Join-Path $WorkRoot 'bao_data'
    if (Test-Path $BaoData) { Remove-Item $BaoData -Recurse -Force }
    Invoke-Checked { git clone https://github.com/CobayaSampler/bao_data.git $BaoData } 'DESI public repo clone failed'
    Invoke-Checked { git -C $BaoData checkout --detach b7b8a36e9bccb063081f811f323cada21ab5fbdd } 'DESI frozen commit checkout failed'
    Invoke-Checked {
        & $R1Python scripts\desi_public_identity.py $BaoData --receipt (Join-Path $ReceiptRoot 'desi-public-identity.json')
    } 'DESI public identity mismatch'

    # --- Relocation ---
    $Relocated = Join-Path $env:RUNNER_TEMP ("ascom00323-relocated-$env:GITHUB_RUN_ID")
    if (Test-Path $Relocated) { Remove-Item $Relocated -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $Relocated | Out-Null
    Get-ChildItem -Force | Where-Object { $_.Name -notin @('.git','.r1') } | ForEach-Object {
        Copy-Item $_.FullName -Destination $Relocated -Recurse -Force
    }
    Push-Location $Relocated
    try {
        Invoke-Checked { & $R1Python -m pytest -q } 'relocated pytest failed'
        Invoke-Checked { & $R1Python scripts\verify_artifact.py } 'relocated artifact verification failed'
    } finally { Pop-Location }
    Write-Receipt 'relocation.json' @{
        schema='ascom-00323-relocation-smoke/v1'; relocated_path='${RUNNER_TEMP}/ascom00323-relocated-${GITHUB_RUN_ID}'; status='verified'
    }

    $RunStatus = 'verified'
}
catch {
    $RunError = $_.Exception.Message
    Write-Host "R1 CORE BLOCKER: $RunError"
    throw
}
finally {
    Write-Receipt 'run-summary.json' @{
        schema='ascom-00323-r1-core-battery/v2'; run_id=$env:GITHUB_RUN_ID; commit=$env:GITHUB_SHA;
        runner_os=$env:RUNNER_OS; status=$RunStatus; blocker=$RunError;
        evidence_policy='Only receipts produced in this clean-room run may be promoted.'
    }
    Get-ChildItem $ReceiptRoot -ErrorAction SilentlyContinue | Format-Table Name,Length
}
