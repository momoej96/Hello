# ينشئ أيقونة «عيادة الأسنان» (شكل سن) على سطح المكتب وفي قائمة ابدأ.
# الأيقونة تشغّل البرنامج بوضع الشبكة بدون نافذة سوداء وتفتح نافذته مباشرة.
$ErrorActionPreference = 'Stop'
$app = Split-Path -Parent $MyInvocation.MyCommand.Path
$name = 'عيادة الأسنان'
$port = 8765
$ws = New-Object -ComObject WScript.Shell

$places = @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))
foreach ($dir in $places) {
    if (-not $dir -or -not (Test-Path $dir)) { continue }
    $final = Join-Path $dir "$name.lnk"
    # WScript.Shell cannot always save non-ANSI file names: save with an ASCII name, then rename
    $tmp = Join-Path $dir 'DentalClinic_tmp.lnk'
    $lnk = $ws.CreateShortcut($tmp)
    $lnk.TargetPath = Join-Path $env:WINDIR 'System32\wscript.exe'
    $lnk.Arguments = '"' + (Join-Path $app 'start_hidden.vbs') + '"'
    $lnk.WorkingDirectory = $app
    $lnk.IconLocation = (Join-Path $app 'tooth.ico') + ',0'
    $lnk.Description = 'Dental Clinic'
    $lnk.Save()
    Move-Item -LiteralPath $tmp -Destination $final -Force
    Write-Host "OK: $final"
}

# السماح لأجهزة شبكة العيادة بالوصول (مرة واحدة، يطلب صلاحية المدير)
$rule = "Dental Clinic (TCP $port)"
if (-not (Get-NetFirewallRule -DisplayName $rule -ErrorAction SilentlyContinue)) {
    $cmd = "New-NetFirewallRule -DisplayName '$rule' -Direction Inbound -Protocol TCP -LocalPort $port -Action Allow -Profile Private,Domain"
    $enc = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($cmd))
    try {
        Start-Process powershell -Verb RunAs -Wait -WindowStyle Hidden -ArgumentList "-NoProfile -EncodedCommand $enc"
        Write-Host "OK: firewall rule '$rule'"
    } catch {
        Write-Host "Firewall rule skipped. If Windows asks later, choose Allow (Private networks)."
    }
}
