#ifndef AppVersion
  #define AppVersion "1.1.0"
#endif
#ifndef BundleDir
  #define BundleDir "..\artifacts\desktop\Agentboard"
#endif
#ifndef ReleaseDir
  #define ReleaseDir "..\artifacts\releases"
#endif

[Setup]
AppId={{8318E71F-BB35-4E0E-A18E-D7B4395C596D}
AppName=DashAI
AppVersion={#AppVersion}
AppPublisher=DashAI
DefaultDirName={localappdata}\Programs\Agentboard
DefaultGroupName=DashAI
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
DisableProgramGroupPage=yes
DisableDirPage=yes
UsePreviousAppDir=yes
UninstallDisplayIcon={app}\Agentboard.exe
OutputDir={#ReleaseDir}
OutputBaseFilename=Agentboard-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
AppMutex=Local\AgentboardDesktop-{%USERNAME},Local\AgentboardMCP-{%USERNAME}
CloseApplications=no
RestartApplications=no
SetupMutex=Local\AgentboardSetup-{%USERNAME}

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "autostart"; Description: "Запускать DashAI при входе в Windows"; GroupDescription: "Дополнительные настройки:"; Flags: unchecked

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Agentboard"; ValueData: """{app}\Agentboard.exe"""; Tasks: autostart; Check: ShouldConfigureStartup

[Files]
Source: "{#BundleDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\DashAI"; Filename: "{app}\Agentboard.exe"
Name: "{autodesktop}\DashAI"; Filename: "{app}\Agentboard.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Agentboard.exe"; WorkingDir: "{app}"; Flags: nowait runasoriginaluser; Check: ShouldOpen

[Code]
function InitializeSetup: Boolean;
var
  InstalledText: String;
  InstalledVersion, NewVersion: Int64;
begin
  Result := True;
  if RegQueryStringValue(HKCU64,
    'Software\Microsoft\Windows\CurrentVersion\Uninstall\{8318E71F-BB35-4E0E-A18E-D7B4395C596D}_is1',
    'DisplayVersion', InstalledText) then
  begin
    if not StrToVersion(InstalledText, InstalledVersion) then
    begin
      SuppressibleMsgBox('Не удалось прочитать установленную версию DashAI. Установка остановлена.', mbError, MB_OK, IDOK);
      Result := False;
    end
    else if StrToVersion('{#AppVersion}', NewVersion) and
      (ComparePackedVersion(InstalledVersion, NewVersion) > 0) then
    begin
      SuppressibleMsgBox('Уже установлена более новая версия DashAI. Понижение версии запрещено.', mbError, MB_OK, IDOK);
      Result := False;
    end;
  end;
end;

function ShouldOpen: Boolean;
begin
  Result := ExpandConstant('{param:NOOPEN|0}') <> '1';
end;

function ShouldConfigureStartup: Boolean;
begin
  Result := ExpandConstant('{param:UPDATE|0}') <> '1';
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  StartupValue, Executable: String;
begin
  if CurUninstallStep = usUninstall then
  begin
    Executable := ExpandConstant('{app}\Agentboard.exe');
    if RegQueryStringValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run',
      'Agentboard', StartupValue) and
      ((CompareText(StartupValue, Executable) = 0) or
       (CompareText(StartupValue, '"' + Executable + '"') = 0)) then
      RegDeleteValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'Agentboard');
  end;
end;
