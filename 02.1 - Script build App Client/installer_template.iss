#define MyAppId "$APP_ID"
#define MyAppName "$APP_NAME"
#define MyAppVersion "$APP_VERSION"
#define MyAppPublisher "$APP_PUBLISHER"
#define MyAppURL "$APP_URL"
#define MyAppExeName "$APP_EXE_NAME"
#define MyDefaultSubdir "$DEFAULT_SUBDIR"
#define MySourceDir "$SOURCE_DIR"
#define MyOutputDir "$OUTPUT_DIR"
#define MyOutputBaseName "$OUTPUT_BASENAME"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={code:GetDefaultInstallDir}
UsePreviousAppDir=yes
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
AllowNoIcons=yes
Compression=lzma2/max
SolidCompression=yes
LZMANumBlockThreads=4
WizardStyle=modern
$SETUP_ICON_LINE
UninstallDisplayIcon={app}\{#MyAppExeName}
OutputDir={#MyOutputDir}
OutputBaseFilename={#MyOutputBaseName}
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DirExistsWarning=no
CloseApplications=yes
CloseApplicationsFilter={#MyAppExeName}
RestartApplications=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
VersionInfoVersion={#MyAppVersion}
VersionInfoProductName={#MyAppName}
VersionInfoDescription=Installer for {#MyAppName}
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[InstallDelete]
Type: filesandordirs; Name: "{app}\*"

[Files]
$FILES_SECTION

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[Code]
var
  InstallLocationPage: TWizardPage;
  InstallDirEdit: TNewEdit;
  InstallDirHint: TNewStaticText;
  DefaultDirButton: TNewButton;
  CurrentDirButton: TNewButton;
  BrowseDirButton: TNewButton;
  ExistingInstallDir: string;

function GetFallbackInstallDir(): string;
begin
  Result := ExpandConstant('{localappdata}\Programs\{#MyDefaultSubdir}');
end;

function CleanDir(const Dir: string): string;
begin
  Result := RemoveBackslashUnlessRoot(Trim(Dir));
end;

function IsExistingAppDir(const Dir: string): Boolean;
begin
  Result :=
    FileExists(AddBackslash(Dir) + '{#MyAppExeName}') or
    FileExists(AddBackslash(Dir) + 'build_info.json') or
    (DirExists(AddBackslash(Dir) + 'config') and DirExists(AddBackslash(Dir) + 'extension'));
end;

function NormalizeTargetDir(const Dir: string): string;
begin
  Result := CleanDir(Dir);
  if Result = '' then
    Result := GetFallbackInstallDir()
  else if (CompareText(ExtractFileName(Result), '{#MyDefaultSubdir}') <> 0) and (not IsExistingAppDir(Result)) then
    Result := AddBackslash(Result) + '{#MyDefaultSubdir}';
end;

function TryUseDetectedDir(const Candidate: string; var InstallDir: string): Boolean;
begin
  InstallDir := CleanDir(Candidate);
  Result := (InstallDir <> '') and DirExists(InstallDir) and IsExistingAppDir(InstallDir);
end;

function ExtractExecutablePath(const CommandValue: string): string;
var
  CommandText: string;
  QuotePos: Integer;
  ExePos: Integer;
begin
  Result := '';
  CommandText := Trim(CommandValue);
  if CommandText = '' then
    Exit;

  if Copy(CommandText, 1, 1) = '"' then
  begin
    Delete(CommandText, 1, 1);
    QuotePos := Pos('"', CommandText);
    if QuotePos > 0 then
      Result := Copy(CommandText, 1, QuotePos - 1);
    Exit;
  end;

  ExePos := Pos('.exe', Lowercase(CommandText));
  if ExePos > 0 then
    Result := Copy(CommandText, 1, ExePos + 3);
end;

function TryGetInstallDirFromCommandValue(
  RootKey: Integer;
  const SubKey: string;
  const ValueName: string;
  var InstallDir: string
): Boolean;
var
  CommandValue: string;
  ExecutablePath: string;
begin
  Result := False;
  if not RegQueryStringValue(RootKey, SubKey, ValueName, CommandValue) then
    Exit;

  ExecutablePath := ExtractExecutablePath(CommandValue);
  if ExecutablePath = '' then
    Exit;

  Result := TryUseDetectedDir(ExtractFileDir(ExecutablePath), InstallDir);
end;

function TryGetInstallDirFromUninstallKey(RootKey: Integer; const SubKey: string; var InstallDir: string): Boolean;
var
  ValueText: string;
begin
  Result := False;

  if RegQueryStringValue(RootKey, SubKey, 'Inno Setup: App Path', ValueText) and
     TryUseDetectedDir(ValueText, InstallDir) then
  begin
    Result := True;
    Exit;
  end;

  if RegQueryStringValue(RootKey, SubKey, 'InstallLocation', ValueText) and
     TryUseDetectedDir(ValueText, InstallDir) then
  begin
    Result := True;
    Exit;
  end;

  if TryGetInstallDirFromCommandValue(RootKey, SubKey, 'QuietUninstallString', InstallDir) then
  begin
    Result := True;
    Exit;
  end;

  Result := TryGetInstallDirFromCommandValue(RootKey, SubKey, 'UninstallString', InstallDir);
end;

function TryGetInstallDirFromRegistry(var InstallDir: string): Boolean;
begin
  Result :=
    TryGetInstallDirFromUninstallKey(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{#MyAppId}_is1', InstallDir) or
    TryGetInstallDirFromUninstallKey(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{#MyAppName}_is1', InstallDir) or
    TryGetInstallDirFromUninstallKey(HKLM, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{#MyAppId}_is1', InstallDir) or
    TryGetInstallDirFromUninstallKey(HKLM, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{#MyAppName}_is1', InstallDir) or
    TryGetInstallDirFromUninstallKey(HKLM, 'Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\{#MyAppId}_is1', InstallDir) or
    TryGetInstallDirFromUninstallKey(HKLM, 'Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\{#MyAppName}_is1', InstallDir);
end;

function TryGetInstallDirFromSetupHint(var InstallDir: string): Boolean;
var
  HintPath: string;
  HintValue: AnsiString;
begin
  Result := False;
  HintPath := ExpandConstant('{srcexe}') + '.appdir';
  if not FileExists(HintPath) then
    Exit;

  if LoadStringFromFile(HintPath, HintValue) then
    Result := TryUseDetectedDir(String(HintValue), InstallDir);
end;

function TryGetKnownInstallDir(var InstallDir: string): Boolean;
begin
  Result :=
    TryUseDetectedDir(ExpandConstant('{localappdata}\Programs\{#MyDefaultSubdir}'), InstallDir) or
    TryUseDetectedDir(ExpandConstant('{autopf}\{#MyDefaultSubdir}'), InstallDir) or
    TryUseDetectedDir(ExpandConstant('{pf}\{#MyDefaultSubdir}'), InstallDir);
end;

function DetectExistingInstallDir(): string;
var
  CandidateDir: string;
begin
  Result := '';

  if TryUseDetectedDir(ExpandConstant('{param:CURRENTAPPDIR|}'), CandidateDir) then
  begin
    Result := CandidateDir;
    Exit;
  end;

  if TryUseDetectedDir(ExpandConstant('{param:APPDIR|}'), CandidateDir) then
  begin
    Result := CandidateDir;
    Exit;
  end;

  if TryGetInstallDirFromSetupHint(CandidateDir) then
  begin
    Result := CandidateDir;
    Exit;
  end;

  if TryGetInstallDirFromRegistry(CandidateDir) then
  begin
    Result := CandidateDir;
    Exit;
  end;

  if TryGetKnownInstallDir(CandidateDir) then
  begin
    Result := CandidateDir;
    Exit;
  end;
end;

function GetDefaultInstallDir(Param: string): string;
var
  DetectedDir: string;
begin
  DetectedDir := DetectExistingInstallDir();
  if DetectedDir <> '' then
    Result := DetectedDir
  else
    Result := NormalizeTargetDir(GetFallbackInstallDir());
end;

function GetPreferredInstallDir(): string;
begin
  if ExistingInstallDir <> '' then
    Result := NormalizeTargetDir(ExistingInstallDir)
  else
    Result := GetDefaultInstallDir('');
end;

procedure SyncInstallDirToWizard();
begin
  InstallDirEdit.Text := NormalizeTargetDir(InstallDirEdit.Text);
  WizardForm.DirEdit.Text := InstallDirEdit.Text;
end;

function IsDriveRoot(const Dir: string): Boolean;
begin
  Result := (Length(Dir) <= 3) and (ExtractFileDrive(Dir) <> '');
end;

function IsUnderBasePath(const TargetDir: string; const BaseDir: string): Boolean;
var
  NormalizedTarget: string;
  NormalizedBase: string;
begin
  NormalizedTarget := Lowercase(AddBackslash(RemoveBackslashUnlessRoot(TargetDir)));
  NormalizedBase := Lowercase(AddBackslash(RemoveBackslashUnlessRoot(BaseDir)));
  Result := Pos(NormalizedBase, NormalizedTarget) = 1;
end;

function ValidateInstallDir(const Dir: string): Boolean;
var
  NormalizedDir: string;
begin
  NormalizedDir := NormalizeTargetDir(Dir);
  Result := False;

  if NormalizedDir = '' then
  begin
    MsgBox('Please choose an install folder.', mbError, MB_OK);
    Exit;
  end;

  if IsDriveRoot(NormalizedDir) then
  begin
    MsgBox('Installing to the root of a drive is blocked. Choose a regular folder instead.', mbError, MB_OK);
    Exit;
  end;

  if IsUnderBasePath(NormalizedDir, ExpandConstant('{win}')) then
  begin
    MsgBox('Installing inside the Windows system folder is not allowed.', mbError, MB_OK);
    Exit;
  end;

  if IsUnderBasePath(NormalizedDir, ExpandConstant('{sys}')) then
  begin
    MsgBox('Installing inside the Windows system folder is not allowed.', mbError, MB_OK);
    Exit;
  end;

  Result := True;
end;

procedure UseDefaultInstallDir(Sender: TObject);
begin
  InstallDirEdit.Text := NormalizeTargetDir(GetFallbackInstallDir());
end;

procedure UseCurrentInstallDir(Sender: TObject);
begin
  if ExistingInstallDir <> '' then
    InstallDirEdit.Text := NormalizeTargetDir(ExistingInstallDir)
  else
    InstallDirEdit.Text := GetPreferredInstallDir();
end;

procedure BrowseInstallDir(Sender: TObject);
var
  ChosenDir: string;
begin
  ChosenDir := InstallDirEdit.Text;
  if BrowseForFolder('Choose where to install {#MyAppName}', ChosenDir, False) then
    InstallDirEdit.Text := NormalizeTargetDir(ChosenDir);
end;

procedure InitializeWizard();
begin
  if not TryUseDetectedDir(WizardForm.DirEdit.Text, ExistingInstallDir) then
    ExistingInstallDir := DetectExistingInstallDir();

  InstallLocationPage :=
    CreateCustomPage(
      wpWelcome,
      'Choose install location',
      'Use the recommended folder or paste a custom path.'
    );

  InstallDirEdit := TNewEdit.Create(WizardForm);
  InstallDirEdit.Parent := InstallLocationPage.Surface;
  InstallDirEdit.Left := 0;
  InstallDirEdit.Top := ScaleY(10);
  InstallDirEdit.Width := InstallLocationPage.SurfaceWidth;
  InstallDirEdit.Text := GetPreferredInstallDir();

  InstallDirHint := TNewStaticText.Create(WizardForm);
  InstallDirHint.Parent := InstallLocationPage.Surface;
  InstallDirHint.Left := 0;
  InstallDirHint.Top := InstallDirEdit.Top + InstallDirEdit.Height + ScaleY(8);
  InstallDirHint.Width := InstallLocationPage.SurfaceWidth;
  InstallDirHint.Height := ScaleY(28);
  InstallDirHint.WordWrap := True;
  if ExistingInstallDir <> '' then
    InstallDirHint.Caption :=
      'Detected current install folder: ' + ExistingInstallDir + #13#10 +
      'You can keep it, paste a different path, or browse if needed.'
  else
    InstallDirHint.Caption :=
      'No current install folder was detected. Recommended: use the default folder, ' +
      'paste a full path, or browse only if needed.';

  DefaultDirButton := TNewButton.Create(WizardForm);
  DefaultDirButton.Parent := InstallLocationPage.Surface;
  DefaultDirButton.Left := 0;
  DefaultDirButton.Top := InstallDirHint.Top + InstallDirHint.Height + ScaleY(12);
  DefaultDirButton.Width := ScaleX(120);
  DefaultDirButton.Height := ScaleY(26);
  DefaultDirButton.Caption := 'Use Default';
  DefaultDirButton.OnClick := @UseDefaultInstallDir;

  CurrentDirButton := TNewButton.Create(WizardForm);
  CurrentDirButton.Parent := InstallLocationPage.Surface;
  CurrentDirButton.Left := DefaultDirButton.Left + DefaultDirButton.Width + ScaleX(8);
  CurrentDirButton.Top := DefaultDirButton.Top;
  CurrentDirButton.Width := ScaleX(140);
  CurrentDirButton.Height := ScaleY(26);
  CurrentDirButton.Caption := 'Use Current Folder';
  CurrentDirButton.OnClick := @UseCurrentInstallDir;
  CurrentDirButton.Enabled := ExistingInstallDir <> '';

  BrowseDirButton := TNewButton.Create(WizardForm);
  BrowseDirButton.Parent := InstallLocationPage.Surface;
  BrowseDirButton.Left := CurrentDirButton.Left + CurrentDirButton.Width + ScaleX(8);
  BrowseDirButton.Top := DefaultDirButton.Top;
  BrowseDirButton.Width := ScaleX(90);
  BrowseDirButton.Height := ScaleY(26);
  BrowseDirButton.Caption := 'Browse...';
  BrowseDirButton.OnClick := @BrowseInstallDir;
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := PageID = wpSelectDir;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = InstallLocationPage.ID then
  begin
    if InstallDirEdit.Text = '' then
      InstallDirEdit.Text := GetPreferredInstallDir();
    SyncInstallDirToWizard();
  end;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = InstallLocationPage.ID then
  begin
    if not ValidateInstallDir(InstallDirEdit.Text) then
    begin
      Result := False;
      Exit;
    end;
    SyncInstallDirToWizard();
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if CurStep = ssInstall then
    Exec(
      ExpandConstant('{cmd}'),
      '/C taskkill /IM {#MyAppExeName} /T /F >nul 2>&1',
      '',
      SW_HIDE,
      ewWaitUntilTerminated,
      ResultCode
    );
end;
