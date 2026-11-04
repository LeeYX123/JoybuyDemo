[CmdletBinding()]
param(
    [ValidateRange(1, 65535)]
    [int]$MySqlPort = 33060,

    [ValidateRange(1, 65535)]
    [int]$RedisPort = 63790,

    [ValidateRange(1, 65535)]
    [int]$MailPort = 1025,

    [ValidateRange(1, 65535)]
    [int]$MailUiPort = 8025
)

$ports = [ordered]@{
    MySQL = $MySqlPort
    Redis = $RedisPort
    MailpitSmtp = $MailPort
    MailpitUi = $MailUiPort
}

$conflicts = foreach ($entry in $ports.GetEnumerator()) {
    $listeners = Get-NetTCPConnection -State Listen -LocalPort $entry.Value -ErrorAction SilentlyContinue
    foreach ($listener in $listeners) {
        $process = Get-Process -Id $listener.OwningProcess -ErrorAction SilentlyContinue
        [pscustomobject]@{
            Service = $entry.Key
            Port = $entry.Value
            Address = $listener.LocalAddress
            Process = if ($process) { $process.ProcessName } else { "PID $($listener.OwningProcess)" }
        }
    }
}

if ($conflicts) {
    $conflicts | Format-Table -AutoSize | Out-String | Write-Error
    throw "One or more Joybuy development ports are already in use. Override the corresponding value in .env before starting Compose."
}

$ports.GetEnumerator() | ForEach-Object {
    "{0,-12} port {1} is available" -f $_.Key, $_.Value
}

