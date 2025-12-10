param(
    [string]$Project = "src/TasarimWeb/TasarimWeb.csproj",
    [string]$PublishTemp = "publish-temp",
    [string]$PublishPath = "publish",
    [string]$AppPoolName = "TasarimPool",
    [string]$SiteUrl = "http://localhost/",
    [string]$VerificationFile = "response_after.html"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-Step {
    param(
        [string]$Message,
        [scriptblock]$Action
    )

    Write-Host "[STEP] $Message" -ForegroundColor Cyan
    & $Action
}

Invoke-Step "Cleaning project (Debug)" { dotnet clean $Project -c Debug | Out-Null }
Invoke-Step "Cleaning project (Release)" { dotnet clean $Project -c Release | Out-Null }
Invoke-Step "Publishing Release build" { dotnet publish $Project -c Release -o $PublishTemp | Out-Null }

Import-Module WebAdministration -ErrorAction Stop

Invoke-Step "Stopping app pool $AppPoolName" {
    if (Test-Path IIS:\AppPools\$AppPoolName) {
        Stop-WebAppPool -Name $AppPoolName -ErrorAction Stop
    } else {
        throw "App pool '$AppPoolName' not found"
    }
}

Invoke-Step "Mirroring $PublishTemp to $PublishPath" {
    robocopy $PublishTemp $PublishPath /MIR /NFL /NDL /NJH /NJS /R:2 /W:2 | Out-Host
    $rc = $LASTEXITCODE
    if ($rc -ge 8) {
        throw "Robocopy failed with code $rc"
    }
}

Invoke-Step "Starting app pool $AppPoolName" { Start-WebAppPool -Name $AppPoolName -ErrorAction Stop }

Invoke-Step "Verifying rendered HTML" {
    Invoke-WebRequest -Uri $SiteUrl -OutFile $VerificationFile -UseBasicParsing | Out-Null
    $html = Get-Content $VerificationFile -Raw

    if ($html -notmatch "Benzer Desen Arama") {
        throw "Verification failed: Expected 'Benzer Desen Arama' text not found"
    }

    $deprecatedPatterns = @(
        "Resimden Ara",
        ("Ar{0}ivden Ara" -f ([char]0x015F))
    )

    foreach ($pattern in $deprecatedPatterns) {
        if ($html -match $pattern) {
            throw "Verification failed: Deprecated button text detected ($pattern)"
        }
    }
}

Write-Host "Deployment complete. UI verified." -ForegroundColor Green
