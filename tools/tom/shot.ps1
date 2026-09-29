# Capture the whole virtual desktop (DPI-aware) to C:\ProgramData\DeLoMIDI\shot.png. Must run in the interactive session.
Add-Type -AssemblyName System.Windows.Forms, System.Drawing
Add-Type -TypeDefinition 'using System.Runtime.InteropServices; public class KltDpi { [DllImport("user32.dll")] public static extern bool SetProcessDPIAware(); }'
[KltDpi]::SetProcessDPIAware() | Out-Null
$b = [System.Windows.Forms.SystemInformation]::VirtualScreen
$bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($b.Left, $b.Top, 0, 0, $bmp.Size)
$bmp.Save('C:\ProgramData\DeLoMIDI\shot.png', [System.Drawing.Imaging.ImageFormat]::Png)
"$($b.Left),$($b.Top) $($b.Width)x$($b.Height)" | Set-Content 'C:\ProgramData\DeLoMIDI\shot.txt'
