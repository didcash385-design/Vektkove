# Vektkove for Windows

Vektkove for Windows is a portable terminal compiler and bytecode runner.
Choose the x64 archive for Intel or AMD PCs, or the arm64 archive for Windows on ARM.
Extract the archive and run `vk.exe` from PowerShell or Command Prompt:

```powershell
.\vk.exe --help
.\vk.exe --version
.\vk.exe run examples\hello.vk
.\vk.exe compile examples\hello.vk hello.vkb
.\vk.exe run hello.vkb
```

To run `vk` from any directory, install it with WinGet once the package is published,
or add the directory containing `vk.exe` to your user PATH.

The Windows builds do not include the macOS editor, launcher, UI Maker, or graphical
rendering. UI instructions are validated but cannot display windows. VKLINK chat is
available through `vk chat listen ADDRESS PORT` and `vk chat connect ADDRESS PORT`.
Use only a trusted network and a strong shared passphrase.