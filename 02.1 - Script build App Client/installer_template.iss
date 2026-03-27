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
Source: "{#MySourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "logs\*,sessions\*,browser_profiles\*,config\browser_profiles\*,*.log,*.tmp,*.lock"

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[Code]
var
  InstallLocationPage: TWizardPage;
  InstallDirEdit: TNewEdit;
  InstallDirHint: TNewStaticText;
  DefaultDirButton: TNewButton;
  CurrentDirButton: TNewButton;
  BrowseDirButton: TNewButton;
  ExistingInstallDir: string;

function IsExistingAppDir(const Dir: string): Boolean;
begin
  Result :=
    FileExists(AddBackslash(Dir) + '{#MyAppExeName}') or
    FileExists(AddBackslash(Dir) + 'build_info.json') or
    (DirExists(AddBackslash(Dir) + 'config') and DirExists(AddBackslash(Dir) + 'extension'));
end;

function NormalizeTargetDir(const Dir: string): string;
begin
  Result := RemoveBackslashUnlessRoot(Trim(Dir));
  if Result = '' then
    Result := ExpandConstant('{localappdata}\Programs\{#MyDefaultSubdir}')
  else if (CompareText(ExtractFileName(Result), '{#MyDefaultSubdir}') <> 0) and (not IsExistingAppDir(Result)) then
    Result := AddBackslash(Result) + '{#MyDefaultSubdir}';
end;

function GetDefaultInstallDir(Param: string): string;
begin
  Result := NormalizeTargetDir(ExpandConstant('{localappdata}\Programs\{#MyDefaultSubdir}'));
end;

function GetPreferredInstallDir(): string;
begin
  if ExistingInstallDir <> '' then
    Result := NormalizeTargetDir(ExistingInstallDir)
  else
    Result := NormalizeTargetDir(ExpandConstant('{localappdata}\Programs\{#MyDefaultSubdir}'));
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
  InstallDirEdit.Text := NormalizeTargetDir(ExpandConstant('{localappdata}\Programs\{#MyDefaultSubdir}'));
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
  ExistingInstallDir := NormalizeTargetDir(WizardForm.DirEdit.Text);

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
  InstallDirHint.Caption :=
    'Recommended: use the default folder. You can also paste a full path directly, ' +
    'or browse only if needed.';

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
