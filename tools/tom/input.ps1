# Drive mouse/keyboard in the interactive session. Reads C:\ProgramData\DeLoMIDI\cmd.txt, one command per line:
#   click X Y | dclick X Y | rclick X Y | move X Y | wheel X Y DELTA | key NAME [ctrl] [shift] [alt] | text STRING | sleep MS
# Coordinates are physical pixels of the DPI-aware virtual desktop (same space as shot.png).
Add-Type -TypeDefinition @'
using System; using System.Runtime.InteropServices;
public class KltIn {
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
  [DllImport("user32.dll")] public static extern void mouse_event(uint f, uint dx, uint dy, uint d, UIntPtr e);
  [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte sc, uint f, UIntPtr e);
}
'@
Add-Type -AssemblyName System.Windows.Forms
[KltIn]::SetProcessDPIAware() | Out-Null
$VK = @{ F1=0x70;F2=0x71;F3=0x72;F4=0x73;F5=0x74;F6=0x75;F7=0x76;F8=0x77;F9=0x78;F10=0x79;F11=0x7A;F12=0x7B;
  ESC=0x1B;ENTER=0x0D;TAB=0x09;SPACE=0x20;UP=0x26;DOWN=0x28;LEFT=0x25;RIGHT=0x27;DELETE=0x2E;BACK=0x08;HOME=0x24;END=0x23 }
function Click($x,$y,$down,$up,$n=1){ [KltIn]::SetCursorPos($x,$y)|Out-Null; Start-Sleep -Milliseconds 60
  1..$n | ForEach-Object { [KltIn]::mouse_event($down,0,0,0,[UIntPtr]::Zero); Start-Sleep -Milliseconds 40; [KltIn]::mouse_event($up,0,0,0,[UIntPtr]::Zero); Start-Sleep -Milliseconds 60 } }
$log = @()
foreach ($line in (Get-Content 'C:\ProgramData\DeLoMIDI\cmd.txt')) {
  $line = $line.Trim(); if (-not $line -or $line.StartsWith('#')) { continue }
  $p = $line -split '\s+', 2; $op = $p[0].ToLower(); $a = if ($p.Count -gt 1) { $p[1] } else { '' }; $t = $a -split '\s+'
  switch ($op) {
    'move'   { [KltIn]::SetCursorPos([int]$t[0],[int]$t[1]) | Out-Null }
    'click'  { Click ([int]$t[0]) ([int]$t[1]) 0x2 0x4 }
    'dclick' { Click ([int]$t[0]) ([int]$t[1]) 0x2 0x4 2 }
    'rclick' { Click ([int]$t[0]) ([int]$t[1]) 0x8 0x10 }
    'wheel'  { [KltIn]::SetCursorPos([int]$t[0],[int]$t[1]) | Out-Null; [KltIn]::mouse_event(0x800,0,0,[uint32]([int]$t[2]),[UIntPtr]::Zero) }
    'sleep'  { Start-Sleep -Milliseconds ([int]$t[0]) }
    'text'   { [System.Windows.Forms.SendKeys]::SendWait(($a -replace '([+^%~(){}\[\]])','{$1}')) }
    'key'    {
      $name = $t[0].ToUpper(); $mods = @($t | Select-Object -Skip 1 | ForEach-Object { $_.ToLower() })
      $code = if ($VK.ContainsKey($name)) { $VK[$name] } elseif ($name.Length -eq 1) { [byte][char]$name } else { throw "unknown key $name" }
      if ($mods -contains 'ctrl')  { [KltIn]::keybd_event(0x11,0,0,[UIntPtr]::Zero) }
      if ($mods -contains 'shift') { [KltIn]::keybd_event(0x10,0,0,[UIntPtr]::Zero) }
      if ($mods -contains 'alt')   { [KltIn]::keybd_event(0x12,0,0,[UIntPtr]::Zero) }
      [KltIn]::keybd_event([byte]$code,0,0,[UIntPtr]::Zero); Start-Sleep -Milliseconds 40; [KltIn]::keybd_event([byte]$code,0,2,[UIntPtr]::Zero)
      if ($mods -contains 'alt')   { [KltIn]::keybd_event(0x12,0,2,[UIntPtr]::Zero) }
      if ($mods -contains 'shift') { [KltIn]::keybd_event(0x10,0,2,[UIntPtr]::Zero) }
      if ($mods -contains 'ctrl')  { [KltIn]::keybd_event(0x11,0,2,[UIntPtr]::Zero) }
    }
    default  { throw "unknown op $op" }
  }
  $log += $line
}
$log | Set-Content 'C:\ProgramData\DeLoMIDI\input.log'
