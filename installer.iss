[Setup]
AppName=Claude Token Tracker
AppVersion=1.0.0
AppPublisher=Claude Token Tracker
AppPublisherURL=https://github.com
DefaultDirName={autopf}\Claude Token Tracker
DefaultGroupName=Claude Token Tracker
UninstallDisplayIcon={app}\ClaudeTokenTracker.exe
OutputDir=installer_output
OutputBaseFilename=ClaudeTokenTracker_Setup
SetupIconFile=
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "dist\ClaudeTokenTracker.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Claude Token Tracker"; Filename: "{app}\ClaudeTokenTracker.exe"
Name: "{group}\Uninstall Claude Token Tracker"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Claude Token Tracker"; Filename: "{app}\ClaudeTokenTracker.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Run]
Filename: "{app}\ClaudeTokenTracker.exe"; Description: "Launch Claude Token Tracker"; Flags: nowait postinstall skipifsilent
