# يُشغَّل مرة واحدة على الحاسبة الثانية (حاسبة جهاز الأشعة الثاني):
# يشارك مجلد صور Woodpecker على الشبكة للقراءة فقط، حتى يستقبل البرنامج (على الحاسبة الرئيسية) صور هذا الجهاز.
$ErrorActionPreference = 'Stop'
$folder = 'C:\ai-dental-images\patients'
if (-not (Test-Path $folder)) {
    Write-Host "Folder not found: $folder"
    $folder = Read-Host 'Enter the Woodpecker "Image Path" folder on this computer'
    if (-not (Test-Path $folder)) { throw "Folder not found: $folder" }
}
$share = 'xray'
# اسم «الجميع» يختلف حسب لغة الويندوز، فنأخذه من رقمه الثابت
$everyone = (New-Object System.Security.Principal.SecurityIdentifier('S-1-1-0')).Translate([System.Security.Principal.NTAccount]).Value
$old = Get-SmbShare -Name $share -ErrorAction SilentlyContinue
if ($old) { Remove-SmbShare -Name $share -Force }
New-SmbShare -Name $share -Path $folder -ReadAccess $everyone | Out-Null
# صلاحية قراءة الملفات نفسها (قراءة فقط)
icacls $folder /grant '*S-1-1-0:(OI)(CI)RX' | Out-Null
# السماح بمشاركة الملفات في جدار الحماية (الشبكة الخاصة)
Get-NetFirewallRule -Group '@FirewallAPI.dll,-28502' | Where-Object { $_.Profile -match 'Private|Domain|Any' } | Enable-NetFirewallRule
Write-Host ''
Write-Host '=============================================================='
Write-Host ' Shared (read only). In the clinic program on the MAIN computer:'
Write-Host ' Settings > Clinic data > "second X-ray device folder" =' -NoNewline
Write-Host ''
Write-Host ("     \\" + $env:COMPUTERNAME + "\" + $share) -ForegroundColor Green
Write-Host '=============================================================='
