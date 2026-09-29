# tools/tom — driving the Windows FL Studio box ("tom") from big-chungus

`tomctl` gives an agent hands on tom: PowerShell over SSH (admin, session 0) plus screenshots and mouse/keyboard in the
logged-in user's interactive desktop (session 1).

## How the GUI half works
SSH sessions cannot touch the desktop. `runi.ps1` registers a throwaway scheduled task whose principal is the
logged-on user with an **Interactive** logon type (no password), runs `shot.ps1` / `input.ps1` in that session, and
deletes the task. `shot.ps1` writes `C:\ProgramData\DeLoMIDI\shot.png`; `input.ps1` executes the commands in
`C:\ProgramData\DeLoMIDI\cmd.txt`. Coordinates are physical pixels of the DPI-aware desktop (tom is 3840x2160).

## Setup
1. On tom: OpenSSH Server running, your key in `C:\ProgramData\ssh\administrators_authorized_keys`.
2. On the controller box: an `ssh tom` alias in `~/.ssh/config` (HostName, User, IdentityFile). No host details live in this repo.
3. `tomctl put tools/tom/*.ps1 C:/ProgramData/DeLoMIDI/` (create the folder first; grant `Users` modify on it so the desktop user can write screenshots).

## Safety rules (learned the hard way, see `docs/incidents/`)
- The desktop is a person's live session. Get consent before any action that can lose work, and check for unsaved
  projects first. Attaching a controller script in FL Studio 26.1.6's MIDI settings crashed FL on 2026-09-29.
- Prefer read-only checks (registry, files, screenshots) over clicking.
- Cleanup: `Remove-Item -Recurse C:\ProgramData\DeLoMIDI` on tom removes every helper and log.
