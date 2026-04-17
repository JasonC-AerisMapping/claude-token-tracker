[Setup]
AppName=Prompt Ledger
AppVersion=2.1.0
AppPublisher=Prompt Ledger
AppPublisherURL=https://github.com/JasonC-AerisMapping/claude-token-tracker
DefaultDirName={autopf}\Prompt Ledger
DefaultGroupName=Prompt Ledger
UninstallDisplayIcon={app}\PromptLedger.exe
OutputDir=installer_output
OutputBaseFilename=PromptLedger_Setup
SetupIconFile=
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "dist\PromptLedger.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Prompt Ledger"; Filename: "{app}\PromptLedger.exe"
Name: "{group}\Uninstall Prompt Ledger"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Prompt Ledger"; Filename: "{app}\PromptLedger.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Run]
Filename: "{app}\PromptLedger.exe"; Description: "Launch Prompt Ledger"; Flags: nowait postinstall skipifsilent
