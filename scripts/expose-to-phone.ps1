# Lets phones on your Wi-Fi reach rosbridge running inside WSL2.
# WSL2 (NAT mode) only forwards ports to Windows' own localhost, so we add a port proxy
# from the LAN to the WSL VM and open the firewall. Run in an *Administrator* PowerShell:
#   powershell -ExecutionPolicy Bypass -File scripts\expose-to-phone.ps1
# Re-run after a reboot (the WSL IP changes). Remove with: -Remove
param([int]$Port = 9090, [string]$Distro = 'Ubuntu-24.04', [switch]$Remove)

$ErrorActionPreference = 'Stop'
$ruleName = "ROS rosbridge $Port"

if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this from an Administrator PowerShell.'
}

netsh interface portproxy delete v4tov4 listenport=$Port listenaddress=0.0.0.0 2>$null | Out-Null
if ($Remove) {
    Remove-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
    Write-Host "Removed port proxy and firewall rule for $Port."
    return
}

$wslIp = (wsl -d $Distro -- hostname -I).Trim().Split(' ')[0]
if (-not $wslIp) { throw "Could not get the IP of WSL distro $Distro (is it installed?)." }

netsh interface portproxy add v4tov4 listenport=$Port listenaddress=0.0.0.0 connectport=$Port connectaddress=$wslIp | Out-Null
if (-not (Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Protocol TCP -LocalPort $Port -Action Allow -Profile Private | Out-Null
}

$lan = Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.PrefixOrigin -in 'Dhcp', 'Manual' -and $_.IPAddress -notlike '169.*' -and $_.InterfaceAlias -notmatch 'vEthernet|WSL|Loopback' } |
    Select-Object -ExpandProperty IPAddress
Write-Host "Forwarding 0.0.0.0:$Port -> WSL $wslIp`:$Port"
Write-Host "In the app on your phone, connect to: $($lan -join ' or ')  port $Port"
Write-Host 'Note: the firewall rule is for Private networks - make sure your Wi-Fi is set to Private.'
