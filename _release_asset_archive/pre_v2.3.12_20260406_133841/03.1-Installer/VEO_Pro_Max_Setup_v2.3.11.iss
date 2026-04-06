#define MyAppId "veostudio.veopromax"
#define MyAppName "VEO Pro Max"
#define MyAppVersion "2.3.11"
#define MyAppPublisher "VEO Studio"
#define MyAppURL "https://github.com/lynkvproerror/vadveopromax"
#define MyAppExeName "VEO_Pro_Max.exe"
#define MyDefaultSubdir "VEO Pro Max"
#define MySourceDir "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist"
#define MyOutputDir "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03.1-Installer"
#define MyOutputBaseName "VEO_Pro_Max_Setup_v2.3.11"

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
SetupIconFile=D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\02 - CLIENT - VEO PRO MAX\assets\icon.ico
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
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\VEO_Pro_Max.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\_asyncio.pyd"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\_brotli.pyd"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\_bz2.pyd"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\_cffi_backend.pyd"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\_ctypes.pyd"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\_decimal.pyd"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\_elementtree.pyd"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\_hashlib.pyd"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\_lzma.pyd"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\_multiprocessing.pyd"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\_overlapped.pyd"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\_queue.pyd"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\_socket.pyd"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\_sqlite3.pyd"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\_ssl.pyd"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\_uuid.pyd"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\_win32sysloader.pyd"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\_winxptheme.pyd"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\_wmi.pyd"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\avcodec-61.dll"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\avformat-61.dll"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\avutil-59.dll"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\dde.pyd"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\libcrypto-3.dll"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\libffi-8.dll"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\libssl-3.dll"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\mfc140u.dll"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\mmapfile.pyd"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\msvcp140.dll"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\msvcp140_1.dll"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\msvcp140_2.dll"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\odbc.pyd"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\perfmon.pyd"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\pyexpat.pyd"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\pyside6.abi3.dll"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\python3.dll"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\python313.dll"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\pythoncom313.dll"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\pywintypes313.dll"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\qt63dcore.dll"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\qt6concurrent.dll"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\qt6core.dll"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\qt6gui.dll"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\qt6multimedia.dll"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\qt6multimediawidgets.dll"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\qt6network.dll"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\qt6pdf.dll"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\qt6svg.dll"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\qt6widgets.dll"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\select.pyd"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\servicemanager.pyd"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\shiboken6.abi3.dll"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\sqlite3.dll"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\swresample-5.dll"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\swscale-8.dll"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\timer.pyd"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\unicodedata.pyd"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\vcruntime140.dll"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\vcruntime140_1.dll"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\win32api.pyd"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\win32clipboard.pyd"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\win32console.pyd"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\win32cred.pyd"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\win32crypt.pyd"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\win32event.pyd"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\win32evtlog.pyd"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\win32file.pyd"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\win32gui.pyd"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\win32help.pyd"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\win32inet.pyd"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\win32job.pyd"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\win32lz.pyd"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\win32net.pyd"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\win32pdh.pyd"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\win32pipe.pyd"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\win32print.pyd"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\win32process.pyd"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\win32profile.pyd"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\win32ras.pyd"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\win32security.pyd"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\win32service.pyd"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\win32trace.pyd"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\win32transaction.pyd"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\win32ts.pyd"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\win32ui.pyd"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\win32uiole.pyd"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\win32wnet.pyd"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\PIL\_imaging.pyd"; DestDir: "{app}\PIL"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\PIL\_imagingcms.pyd"; DestDir: "{app}\PIL"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\PIL\_imagingmath.pyd"; DestDir: "{app}\PIL"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\PIL\_imagingtk.pyd"; DestDir: "{app}\PIL"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\PIL\_webp.pyd"; DestDir: "{app}\PIL"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\PySide6\Qt3DCore.pyd"; DestDir: "{app}\PySide6"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\PySide6\QtCore.pyd"; DestDir: "{app}\PySide6"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\PySide6\QtGui.pyd"; DestDir: "{app}\PySide6"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\PySide6\QtMultimedia.pyd"; DestDir: "{app}\PySide6"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\PySide6\QtMultimediaWidgets.pyd"; DestDir: "{app}\PySide6"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\PySide6\QtNetwork.pyd"; DestDir: "{app}\PySide6"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\PySide6\QtWidgets.pyd"; DestDir: "{app}\PySide6"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\PySide6\qt-plugins\iconengines\qsvgicon.dll"; DestDir: "{app}\PySide6\qt-plugins\iconengines"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\PySide6\qt-plugins\imageformats\qgif.dll"; DestDir: "{app}\PySide6\qt-plugins\imageformats"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\PySide6\qt-plugins\imageformats\qicns.dll"; DestDir: "{app}\PySide6\qt-plugins\imageformats"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\PySide6\qt-plugins\imageformats\qico.dll"; DestDir: "{app}\PySide6\qt-plugins\imageformats"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\PySide6\qt-plugins\imageformats\qjpeg.dll"; DestDir: "{app}\PySide6\qt-plugins\imageformats"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\PySide6\qt-plugins\imageformats\qpdf.dll"; DestDir: "{app}\PySide6\qt-plugins\imageformats"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\PySide6\qt-plugins\imageformats\qsvg.dll"; DestDir: "{app}\PySide6\qt-plugins\imageformats"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\PySide6\qt-plugins\imageformats\qtga.dll"; DestDir: "{app}\PySide6\qt-plugins\imageformats"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\PySide6\qt-plugins\imageformats\qtiff.dll"; DestDir: "{app}\PySide6\qt-plugins\imageformats"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\PySide6\qt-plugins\imageformats\qwbmp.dll"; DestDir: "{app}\PySide6\qt-plugins\imageformats"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\PySide6\qt-plugins\imageformats\qwebp.dll"; DestDir: "{app}\PySide6\qt-plugins\imageformats"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\PySide6\qt-plugins\multimedia\ffmpegmediaplugin.dll"; DestDir: "{app}\PySide6\qt-plugins\multimedia"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\PySide6\qt-plugins\multimedia\windowsmediaplugin.dll"; DestDir: "{app}\PySide6\qt-plugins\multimedia"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\PySide6\qt-plugins\platforms\qdirect2d.dll"; DestDir: "{app}\PySide6\qt-plugins\platforms"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\PySide6\qt-plugins\platforms\qminimal.dll"; DestDir: "{app}\PySide6\qt-plugins\platforms"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\PySide6\qt-plugins\platforms\qoffscreen.dll"; DestDir: "{app}\PySide6\qt-plugins\platforms"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\PySide6\qt-plugins\platforms\qwindows.dll"; DestDir: "{app}\PySide6\qt-plugins\platforms"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\PySide6\qt-plugins\styles\qmodernwindowsstyle.dll"; DestDir: "{app}\PySide6\qt-plugins\styles"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\PySide6\qt-plugins\tls\qcertonlybackend.dll"; DestDir: "{app}\PySide6\qt-plugins\tls"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\PySide6\qt-plugins\tls\qopensslbackend.dll"; DestDir: "{app}\PySide6\qt-plugins\tls"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\PySide6\qt-plugins\tls\qschannelbackend.dll"; DestDir: "{app}\PySide6\qt-plugins\tls"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\aiohttp\_http_parser.pyd"; DestDir: "{app}\aiohttp"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\aiohttp\_http_writer.pyd"; DestDir: "{app}\aiohttp"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\aiohttp\_websocket\mask.pyd"; DestDir: "{app}\aiohttp\_websocket"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\aiohttp\_websocket\reader_c.pyd"; DestDir: "{app}\aiohttp\_websocket"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\assets\icon.ico"; DestDir: "{app}\assets"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\assets\splash_banner.png"; DestDir: "{app}\assets"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\assets\sounds\alert.wav"; DestDir: "{app}\assets\sounds"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\assets\sounds\bell.wav"; DestDir: "{app}\assets\sounds"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\assets\sounds\chime.wav"; DestDir: "{app}\assets\sounds"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\assets\sounds\complete.wav"; DestDir: "{app}\assets\sounds"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\assets\sounds\crystal.wav"; DestDir: "{app}\assets\sounds"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\assets\sounds\default.wav"; DestDir: "{app}\assets\sounds"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\assets\sounds\ding.wav"; DestDir: "{app}\assets\sounds"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\assets\sounds\gentle.wav"; DestDir: "{app}\assets\sounds"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\assets\sounds\notify.wav"; DestDir: "{app}\assets\sounds"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\assets\sounds\piano.wav"; DestDir: "{app}\assets\sounds"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\assets\sounds\soft.wav"; DestDir: "{app}\assets\sounds"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\assets\sounds\success.wav"; DestDir: "{app}\assets\sounds"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\assets\sounds\tada.wav"; DestDir: "{app}\assets\sounds"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\assets\themes\dark_theme.json"; DestDir: "{app}\assets\themes"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\certifi\cacert.pem"; DestDir: "{app}\certifi"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\charset_normalizer\md.pyd"; DestDir: "{app}\charset_normalizer"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\charset_normalizer\md__mypyc.pyd"; DestDir: "{app}\charset_normalizer"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\config\locales\en.json"; DestDir: "{app}\config\locales"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\config\locales\vi.json"; DestDir: "{app}\config\locales"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\cryptography\hazmat\bindings\_rust.pyd"; DestDir: "{app}\cryptography\hazmat\bindings"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\data\policy_fix_rules.json"; DestDir: "{app}\data"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\data\workflows\00_README.enc"; DestDir: "{app}\data\workflows"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\data\workflows\content-video.enc"; DestDir: "{app}\data\workflows"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\data\workflows\01_Research\01_Trending_Keywords_2026.enc"; DestDir: "{app}\data\workflows\01_Research"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\data\workflows\01_Research\02_Title_Bank_Tet_2026.enc"; DestDir: "{app}\data\workflows\01_Research"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\data\workflows\01_Research\03_SEO_Bank_Tet_2026.enc"; DestDir: "{app}\data\workflows\01_Research"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\data\workflows\01_Research\Sensitive_Words.txt"; DestDir: "{app}\data\workflows\01_Research"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\data\workflows\02_Universal\00_Core_Principles.enc"; DestDir: "{app}\data\workflows\02_Universal"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\data\workflows\02_Universal\00_Production_Checklist.enc"; DestDir: "{app}\data\workflows\02_Universal"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\data\workflows\02_Universal\01_Technical_Rules.enc"; DestDir: "{app}\data\workflows\02_Universal"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\data\workflows\02_Universal\02_File_Formats.enc"; DestDir: "{app}\data\workflows\02_Universal"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\data\workflows\02_Universal\03_Quality_Checklist.enc"; DestDir: "{app}\data\workflows\02_Universal"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\data\workflows\02_Universal\04_Master_Format.enc"; DestDir: "{app}\data\workflows\02_Universal"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\data\workflows\02_Universal\05_Prompts_Format.enc"; DestDir: "{app}\data\workflows\02_Universal"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\data\workflows\02_Universal\06_Dubbing_Format.enc"; DestDir: "{app}\data\workflows\02_Universal"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\data\workflows\02_Universal\07_SEO_Format.enc"; DestDir: "{app}\data\workflows\02_Universal"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\data\workflows\02_Universal\Templates\Anthropomorphic_Tips.enc"; DestDir: "{app}\data\workflows\02_Universal\Templates"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\data\workflows\02_Universal\Templates\Cooking_Tips.enc"; DestDir: "{app}\data\workflows\02_Universal\Templates"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\data\workflows\02_Universal\Templates\Entertainment_3Act.enc"; DestDir: "{app}\data\workflows\02_Universal\Templates"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\data\workflows\02_Universal\Templates\Family_Drama.enc"; DestDir: "{app}\data\workflows\02_Universal\Templates"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\data\workflows\02_Universal\Templates\Fashion_Review_Silent.enc"; DestDir: "{app}\data\workflows\02_Universal\Templates"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\data\workflows\02_Universal\Templates\Finance_Tips.enc"; DestDir: "{app}\data\workflows\02_Universal\Templates"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\data\workflows\02_Universal\Templates\Health_PMCS.enc"; DestDir: "{app}\data\workflows\02_Universal\Templates"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\data\workflows\02_Universal\Templates\History_Storytelling.enc"; DestDir: "{app}\data\workflows\02_Universal\Templates"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\data\workflows\02_Universal\Templates\Life_Wisdom.enc"; DestDir: "{app}\data\workflows\02_Universal\Templates"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\data\workflows\02_Universal\Templates\POV_MultiOutfit_Styling.enc"; DestDir: "{app}\data\workflows\02_Universal\Templates"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\data\workflows\02_Universal\Templates\Religion_Buddhist.enc"; DestDir: "{app}\data\workflows\02_Universal\Templates"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\data\workflows\02_Universal\Templates\Social_Tips_Sister.enc"; DestDir: "{app}\data\workflows\02_Universal\Templates"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\data\workflows\02_Universal\Templates\Treadmill_Catwalk.enc"; DestDir: "{app}\data\workflows\02_Universal\Templates"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\data\workflows\02_Universal\Templates\_Hybrid_Guide.enc"; DestDir: "{app}\data\workflows\02_Universal\Templates"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\data\workflows\02_Universal\Templates\_Template_Builder.enc"; DestDir: "{app}\data\workflows\02_Universal\Templates"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\data\workflows\03_Advanced\01_Camera_Complete.enc"; DestDir: "{app}\data\workflows\03_Advanced"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\data\workflows\03_Advanced\02_Negative_Prompts.enc"; DestDir: "{app}\data\workflows\03_Advanced"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\data\workflows\03_Advanced\03_Audio_Workflow_Cost.enc"; DestDir: "{app}\data\workflows\03_Advanced"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\data\workflows\03_Advanced\03_Dialogue_Scene.enc"; DestDir: "{app}\data\workflows\03_Advanced"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\data\workflows\03_Advanced\04_Director_Personas.enc"; DestDir: "{app}\data\workflows\03_Advanced"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\data\workflows\03_Advanced\05_Prompt_Adherence.enc"; DestDir: "{app}\data\workflows\03_Advanced"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\data\workflows\03_Advanced\06_LipSync.enc"; DestDir: "{app}\data\workflows\03_Advanced"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\data\workflows\03_Advanced\07_Golden_Phrases.enc"; DestDir: "{app}\data\workflows\03_Advanced"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\data\workflows\03_Advanced\08_Character_Scale.enc"; DestDir: "{app}\data\workflows\03_Advanced"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\data\workflows\03_Advanced\Global_Bible_Library.enc"; DestDir: "{app}\data\workflows\03_Advanced"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\data\workflows\03_Advanced\Quick_Reference_Card.enc"; DestDir: "{app}\data\workflows\03_Advanced"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\docx\templates\default-comments.xml"; DestDir: "{app}\docx\templates"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\docx\templates\default-footer.xml"; DestDir: "{app}\docx\templates"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\docx\templates\default-header.xml"; DestDir: "{app}\docx\templates"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\docx\templates\default-settings.xml"; DestDir: "{app}\docx\templates"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\docx\templates\default-styles.xml"; DestDir: "{app}\docx\templates"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\docx\templates\default.docx"; DestDir: "{app}\docx\templates"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\docx\templates\default-docx-template\[Content_Types].xml"; DestDir: "{app}\docx\templates\default-docx-template"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\docx\templates\default-docx-template\_rels\.rels"; DestDir: "{app}\docx\templates\default-docx-template\_rels"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\docx\templates\default-docx-template\customXml\item1.xml"; DestDir: "{app}\docx\templates\default-docx-template\customXml"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\docx\templates\default-docx-template\customXml\itemProps1.xml"; DestDir: "{app}\docx\templates\default-docx-template\customXml"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\docx\templates\default-docx-template\customXml\_rels\item1.xml.rels"; DestDir: "{app}\docx\templates\default-docx-template\customXml\_rels"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\docx\templates\default-docx-template\docProps\app.xml"; DestDir: "{app}\docx\templates\default-docx-template\docProps"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\docx\templates\default-docx-template\docProps\core.xml"; DestDir: "{app}\docx\templates\default-docx-template\docProps"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\docx\templates\default-docx-template\docProps\thumbnail.jpeg"; DestDir: "{app}\docx\templates\default-docx-template\docProps"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\docx\templates\default-docx-template\word\document.xml"; DestDir: "{app}\docx\templates\default-docx-template\word"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\docx\templates\default-docx-template\word\fontTable.xml"; DestDir: "{app}\docx\templates\default-docx-template\word"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\docx\templates\default-docx-template\word\numbering.xml"; DestDir: "{app}\docx\templates\default-docx-template\word"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\docx\templates\default-docx-template\word\settings.xml"; DestDir: "{app}\docx\templates\default-docx-template\word"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\docx\templates\default-docx-template\word\styles.xml"; DestDir: "{app}\docx\templates\default-docx-template\word"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\docx\templates\default-docx-template\word\stylesWithEffects.xml"; DestDir: "{app}\docx\templates\default-docx-template\word"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\docx\templates\default-docx-template\word\webSettings.xml"; DestDir: "{app}\docx\templates\default-docx-template\word"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\docx\templates\default-docx-template\word\_rels\document.xml.rels"; DestDir: "{app}\docx\templates\default-docx-template\word\_rels"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\docx\templates\default-docx-template\word\theme\theme1.xml"; DestDir: "{app}\docx\templates\default-docx-template\word\theme"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\extension\background.js"; DestDir: "{app}\extension"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\extension\content.js"; DestDir: "{app}\extension"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\extension\icon128.png"; DestDir: "{app}\extension"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\extension\icon48.png"; DestDir: "{app}\extension"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\extension\manifest.json"; DestDir: "{app}\extension"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\extension\offscreen.html"; DestDir: "{app}\extension"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\extension\offscreen.js"; DestDir: "{app}\extension"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\extension\popup.html"; DestDir: "{app}\extension"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\extension\popup.js"; DestDir: "{app}\extension"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\extension\stealth.js"; DestDir: "{app}\extension"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\frozenlist\_frozenlist.pyd"; DestDir: "{app}\frozenlist"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\greenlet\_greenlet.pyd"; DestDir: "{app}\greenlet"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\lxml\_elementpath.pyd"; DestDir: "{app}\lxml"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\lxml\builder.pyd"; DestDir: "{app}\lxml"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\lxml\etree.pyd"; DestDir: "{app}\lxml"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\lxml\objectify.pyd"; DestDir: "{app}\lxml"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\lxml\sax.pyd"; DestDir: "{app}\lxml"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\multidict\_multidict.pyd"; DestDir: "{app}\multidict"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\node.exe"; DestDir: "{app}\playwright\driver"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\api.json"; DestDir: "{app}\playwright\driver\package"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\browsers.json"; DestDir: "{app}\playwright\driver\package"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\cli.js"; DestDir: "{app}\playwright\driver\package"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\index.d.ts"; DestDir: "{app}\playwright\driver\package"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\index.js"; DestDir: "{app}\playwright\driver\package"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\package.json"; DestDir: "{app}\playwright\driver\package"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\androidServerImpl.js"; DestDir: "{app}\playwright\driver\package\lib"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\browserServerImpl.js"; DestDir: "{app}\playwright\driver\package\lib"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\inProcessFactory.js"; DestDir: "{app}\playwright\driver\package\lib"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\inprocess.js"; DestDir: "{app}\playwright\driver\package\lib"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\outofprocess.js"; DestDir: "{app}\playwright\driver\package\lib"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\utils.js"; DestDir: "{app}\playwright\driver\package\lib"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\utilsBundle.js"; DestDir: "{app}\playwright\driver\package\lib"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\zipBundle.js"; DestDir: "{app}\playwright\driver\package\lib"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\zipBundleImpl.js"; DestDir: "{app}\playwright\driver\package\lib"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\cli\driver.js"; DestDir: "{app}\playwright\driver\package\lib\cli"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\cli\program.js"; DestDir: "{app}\playwright\driver\package\lib\cli"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\cli\programWithTestStub.js"; DestDir: "{app}\playwright\driver\package\lib\cli"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\client\android.js"; DestDir: "{app}\playwright\driver\package\lib\client"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\client\api.js"; DestDir: "{app}\playwright\driver\package\lib\client"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\client\artifact.js"; DestDir: "{app}\playwright\driver\package\lib\client"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\client\browser.js"; DestDir: "{app}\playwright\driver\package\lib\client"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\client\browserContext.js"; DestDir: "{app}\playwright\driver\package\lib\client"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\client\browserType.js"; DestDir: "{app}\playwright\driver\package\lib\client"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\client\cdpSession.js"; DestDir: "{app}\playwright\driver\package\lib\client"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\client\channelOwner.js"; DestDir: "{app}\playwright\driver\package\lib\client"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\client\clientHelper.js"; DestDir: "{app}\playwright\driver\package\lib\client"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\client\clientInstrumentation.js"; DestDir: "{app}\playwright\driver\package\lib\client"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\client\clientStackTrace.js"; DestDir: "{app}\playwright\driver\package\lib\client"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\client\clock.js"; DestDir: "{app}\playwright\driver\package\lib\client"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\client\connection.js"; DestDir: "{app}\playwright\driver\package\lib\client"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\client\consoleMessage.js"; DestDir: "{app}\playwright\driver\package\lib\client"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\client\coverage.js"; DestDir: "{app}\playwright\driver\package\lib\client"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\client\dialog.js"; DestDir: "{app}\playwright\driver\package\lib\client"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\client\download.js"; DestDir: "{app}\playwright\driver\package\lib\client"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\client\electron.js"; DestDir: "{app}\playwright\driver\package\lib\client"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\client\elementHandle.js"; DestDir: "{app}\playwright\driver\package\lib\client"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\client\errors.js"; DestDir: "{app}\playwright\driver\package\lib\client"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\client\eventEmitter.js"; DestDir: "{app}\playwright\driver\package\lib\client"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\client\events.js"; DestDir: "{app}\playwright\driver\package\lib\client"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\client\fetch.js"; DestDir: "{app}\playwright\driver\package\lib\client"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\client\fileChooser.js"; DestDir: "{app}\playwright\driver\package\lib\client"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\client\fileUtils.js"; DestDir: "{app}\playwright\driver\package\lib\client"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\client\frame.js"; DestDir: "{app}\playwright\driver\package\lib\client"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\client\harRouter.js"; DestDir: "{app}\playwright\driver\package\lib\client"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\client\input.js"; DestDir: "{app}\playwright\driver\package\lib\client"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\client\jsHandle.js"; DestDir: "{app}\playwright\driver\package\lib\client"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\client\jsonPipe.js"; DestDir: "{app}\playwright\driver\package\lib\client"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\client\localUtils.js"; DestDir: "{app}\playwright\driver\package\lib\client"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\client\locator.js"; DestDir: "{app}\playwright\driver\package\lib\client"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\client\network.js"; DestDir: "{app}\playwright\driver\package\lib\client"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\client\page.js"; DestDir: "{app}\playwright\driver\package\lib\client"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\client\platform.js"; DestDir: "{app}\playwright\driver\package\lib\client"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\client\playwright.js"; DestDir: "{app}\playwright\driver\package\lib\client"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\client\selectors.js"; DestDir: "{app}\playwright\driver\package\lib\client"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\client\stream.js"; DestDir: "{app}\playwright\driver\package\lib\client"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\client\timeoutSettings.js"; DestDir: "{app}\playwright\driver\package\lib\client"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\client\tracing.js"; DestDir: "{app}\playwright\driver\package\lib\client"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\client\types.js"; DestDir: "{app}\playwright\driver\package\lib\client"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\client\video.js"; DestDir: "{app}\playwright\driver\package\lib\client"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\client\waiter.js"; DestDir: "{app}\playwright\driver\package\lib\client"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\client\webError.js"; DestDir: "{app}\playwright\driver\package\lib\client"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\client\webSocket.js"; DestDir: "{app}\playwright\driver\package\lib\client"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\client\worker.js"; DestDir: "{app}\playwright\driver\package\lib\client"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\client\writableStream.js"; DestDir: "{app}\playwright\driver\package\lib\client"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\generated\bindingsControllerSource.js"; DestDir: "{app}\playwright\driver\package\lib\generated"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\generated\clockSource.js"; DestDir: "{app}\playwright\driver\package\lib\generated"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\generated\injectedScriptSource.js"; DestDir: "{app}\playwright\driver\package\lib\generated"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\generated\pollingRecorderSource.js"; DestDir: "{app}\playwright\driver\package\lib\generated"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\generated\storageScriptSource.js"; DestDir: "{app}\playwright\driver\package\lib\generated"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\generated\utilityScriptSource.js"; DestDir: "{app}\playwright\driver\package\lib\generated"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\generated\webSocketMockSource.js"; DestDir: "{app}\playwright\driver\package\lib\generated"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\protocol\serializers.js"; DestDir: "{app}\playwright\driver\package\lib\protocol"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\protocol\validator.js"; DestDir: "{app}\playwright\driver\package\lib\protocol"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\protocol\validatorPrimitives.js"; DestDir: "{app}\playwright\driver\package\lib\protocol"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\remote\playwrightConnection.js"; DestDir: "{app}\playwright\driver\package\lib\remote"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\remote\playwrightServer.js"; DestDir: "{app}\playwright\driver\package\lib\remote"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\artifact.js"; DestDir: "{app}\playwright\driver\package\lib\server"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\browser.js"; DestDir: "{app}\playwright\driver\package\lib\server"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\browserContext.js"; DestDir: "{app}\playwright\driver\package\lib\server"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\browserType.js"; DestDir: "{app}\playwright\driver\package\lib\server"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\callLog.js"; DestDir: "{app}\playwright\driver\package\lib\server"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\clock.js"; DestDir: "{app}\playwright\driver\package\lib\server"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\console.js"; DestDir: "{app}\playwright\driver\package\lib\server"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\cookieStore.js"; DestDir: "{app}\playwright\driver\package\lib\server"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\debugController.js"; DestDir: "{app}\playwright\driver\package\lib\server"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\debugger.js"; DestDir: "{app}\playwright\driver\package\lib\server"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\deviceDescriptors.js"; DestDir: "{app}\playwright\driver\package\lib\server"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\deviceDescriptorsSource.json"; DestDir: "{app}\playwright\driver\package\lib\server"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\dialog.js"; DestDir: "{app}\playwright\driver\package\lib\server"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\dom.js"; DestDir: "{app}\playwright\driver\package\lib\server"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\download.js"; DestDir: "{app}\playwright\driver\package\lib\server"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\errors.js"; DestDir: "{app}\playwright\driver\package\lib\server"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\fetch.js"; DestDir: "{app}\playwright\driver\package\lib\server"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\fileChooser.js"; DestDir: "{app}\playwright\driver\package\lib\server"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\fileUploadUtils.js"; DestDir: "{app}\playwright\driver\package\lib\server"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\formData.js"; DestDir: "{app}\playwright\driver\package\lib\server"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\frameSelectors.js"; DestDir: "{app}\playwright\driver\package\lib\server"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\frames.js"; DestDir: "{app}\playwright\driver\package\lib\server"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\harBackend.js"; DestDir: "{app}\playwright\driver\package\lib\server"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\helper.js"; DestDir: "{app}\playwright\driver\package\lib\server"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\index.js"; DestDir: "{app}\playwright\driver\package\lib\server"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\input.js"; DestDir: "{app}\playwright\driver\package\lib\server"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\instrumentation.js"; DestDir: "{app}\playwright\driver\package\lib\server"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\javascript.js"; DestDir: "{app}\playwright\driver\package\lib\server"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\launchApp.js"; DestDir: "{app}\playwright\driver\package\lib\server"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\localUtils.js"; DestDir: "{app}\playwright\driver\package\lib\server"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\macEditingCommands.js"; DestDir: "{app}\playwright\driver\package\lib\server"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\network.js"; DestDir: "{app}\playwright\driver\package\lib\server"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\page.js"; DestDir: "{app}\playwright\driver\package\lib\server"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\pipeTransport.js"; DestDir: "{app}\playwright\driver\package\lib\server"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\playwright.js"; DestDir: "{app}\playwright\driver\package\lib\server"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\progress.js"; DestDir: "{app}\playwright\driver\package\lib\server"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\protocolError.js"; DestDir: "{app}\playwright\driver\package\lib\server"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\recorder.js"; DestDir: "{app}\playwright\driver\package\lib\server"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\screenshotter.js"; DestDir: "{app}\playwright\driver\package\lib\server"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\selectors.js"; DestDir: "{app}\playwright\driver\package\lib\server"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\socksClientCertificatesInterceptor.js"; DestDir: "{app}\playwright\driver\package\lib\server"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\socksInterceptor.js"; DestDir: "{app}\playwright\driver\package\lib\server"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\transport.js"; DestDir: "{app}\playwright\driver\package\lib\server"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\types.js"; DestDir: "{app}\playwright\driver\package\lib\server"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\usKeyboardLayout.js"; DestDir: "{app}\playwright\driver\package\lib\server"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\android\android.js"; DestDir: "{app}\playwright\driver\package\lib\server\android"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\android\backendAdb.js"; DestDir: "{app}\playwright\driver\package\lib\server\android"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\bidi\bidiBrowser.js"; DestDir: "{app}\playwright\driver\package\lib\server\bidi"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\bidi\bidiChromium.js"; DestDir: "{app}\playwright\driver\package\lib\server\bidi"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\bidi\bidiConnection.js"; DestDir: "{app}\playwright\driver\package\lib\server\bidi"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\bidi\bidiExecutionContext.js"; DestDir: "{app}\playwright\driver\package\lib\server\bidi"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\bidi\bidiFirefox.js"; DestDir: "{app}\playwright\driver\package\lib\server\bidi"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\bidi\bidiInput.js"; DestDir: "{app}\playwright\driver\package\lib\server\bidi"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\bidi\bidiNetworkManager.js"; DestDir: "{app}\playwright\driver\package\lib\server\bidi"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\bidi\bidiOverCdp.js"; DestDir: "{app}\playwright\driver\package\lib\server\bidi"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\bidi\bidiPage.js"; DestDir: "{app}\playwright\driver\package\lib\server\bidi"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\bidi\bidiPdf.js"; DestDir: "{app}\playwright\driver\package\lib\server\bidi"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\bidi\third_party\bidiCommands.d.js"; DestDir: "{app}\playwright\driver\package\lib\server\bidi\third_party"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\bidi\third_party\bidiDeserializer.js"; DestDir: "{app}\playwright\driver\package\lib\server\bidi\third_party"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\bidi\third_party\bidiKeyboard.js"; DestDir: "{app}\playwright\driver\package\lib\server\bidi\third_party"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\bidi\third_party\bidiProtocol.js"; DestDir: "{app}\playwright\driver\package\lib\server\bidi\third_party"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\bidi\third_party\bidiProtocolCore.js"; DestDir: "{app}\playwright\driver\package\lib\server\bidi\third_party"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\bidi\third_party\bidiProtocolPermissions.js"; DestDir: "{app}\playwright\driver\package\lib\server\bidi\third_party"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\bidi\third_party\bidiSerializer.js"; DestDir: "{app}\playwright\driver\package\lib\server\bidi\third_party"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\bidi\third_party\firefoxPrefs.js"; DestDir: "{app}\playwright\driver\package\lib\server\bidi\third_party"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\chromium\chromium.js"; DestDir: "{app}\playwright\driver\package\lib\server\chromium"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\chromium\chromiumSwitches.js"; DestDir: "{app}\playwright\driver\package\lib\server\chromium"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\chromium\crBrowser.js"; DestDir: "{app}\playwright\driver\package\lib\server\chromium"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\chromium\crConnection.js"; DestDir: "{app}\playwright\driver\package\lib\server\chromium"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\chromium\crCoverage.js"; DestDir: "{app}\playwright\driver\package\lib\server\chromium"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\chromium\crDevTools.js"; DestDir: "{app}\playwright\driver\package\lib\server\chromium"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\chromium\crDragDrop.js"; DestDir: "{app}\playwright\driver\package\lib\server\chromium"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\chromium\crExecutionContext.js"; DestDir: "{app}\playwright\driver\package\lib\server\chromium"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\chromium\crInput.js"; DestDir: "{app}\playwright\driver\package\lib\server\chromium"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\chromium\crNetworkManager.js"; DestDir: "{app}\playwright\driver\package\lib\server\chromium"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\chromium\crPage.js"; DestDir: "{app}\playwright\driver\package\lib\server\chromium"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\chromium\crPdf.js"; DestDir: "{app}\playwright\driver\package\lib\server\chromium"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\chromium\crProtocolHelper.js"; DestDir: "{app}\playwright\driver\package\lib\server\chromium"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\chromium\crServiceWorker.js"; DestDir: "{app}\playwright\driver\package\lib\server\chromium"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\chromium\defaultFontFamilies.js"; DestDir: "{app}\playwright\driver\package\lib\server\chromium"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\chromium\protocol.d.js"; DestDir: "{app}\playwright\driver\package\lib\server\chromium"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\chromium\videoRecorder.js"; DestDir: "{app}\playwright\driver\package\lib\server\chromium"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\codegen\csharp.js"; DestDir: "{app}\playwright\driver\package\lib\server\codegen"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\codegen\java.js"; DestDir: "{app}\playwright\driver\package\lib\server\codegen"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\codegen\javascript.js"; DestDir: "{app}\playwright\driver\package\lib\server\codegen"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\codegen\jsonl.js"; DestDir: "{app}\playwright\driver\package\lib\server\codegen"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\codegen\language.js"; DestDir: "{app}\playwright\driver\package\lib\server\codegen"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\codegen\languages.js"; DestDir: "{app}\playwright\driver\package\lib\server\codegen"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\codegen\python.js"; DestDir: "{app}\playwright\driver\package\lib\server\codegen"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\codegen\types.js"; DestDir: "{app}\playwright\driver\package\lib\server\codegen"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\dispatchers\androidDispatcher.js"; DestDir: "{app}\playwright\driver\package\lib\server\dispatchers"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\dispatchers\artifactDispatcher.js"; DestDir: "{app}\playwright\driver\package\lib\server\dispatchers"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\dispatchers\browserContextDispatcher.js"; DestDir: "{app}\playwright\driver\package\lib\server\dispatchers"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\dispatchers\browserDispatcher.js"; DestDir: "{app}\playwright\driver\package\lib\server\dispatchers"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\dispatchers\browserTypeDispatcher.js"; DestDir: "{app}\playwright\driver\package\lib\server\dispatchers"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\dispatchers\cdpSessionDispatcher.js"; DestDir: "{app}\playwright\driver\package\lib\server\dispatchers"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\dispatchers\debugControllerDispatcher.js"; DestDir: "{app}\playwright\driver\package\lib\server\dispatchers"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\dispatchers\dialogDispatcher.js"; DestDir: "{app}\playwright\driver\package\lib\server\dispatchers"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\dispatchers\dispatcher.js"; DestDir: "{app}\playwright\driver\package\lib\server\dispatchers"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\dispatchers\electronDispatcher.js"; DestDir: "{app}\playwright\driver\package\lib\server\dispatchers"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\dispatchers\elementHandlerDispatcher.js"; DestDir: "{app}\playwright\driver\package\lib\server\dispatchers"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\dispatchers\frameDispatcher.js"; DestDir: "{app}\playwright\driver\package\lib\server\dispatchers"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\dispatchers\jsHandleDispatcher.js"; DestDir: "{app}\playwright\driver\package\lib\server\dispatchers"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\dispatchers\jsonPipeDispatcher.js"; DestDir: "{app}\playwright\driver\package\lib\server\dispatchers"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\dispatchers\localUtilsDispatcher.js"; DestDir: "{app}\playwright\driver\package\lib\server\dispatchers"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\dispatchers\networkDispatchers.js"; DestDir: "{app}\playwright\driver\package\lib\server\dispatchers"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\dispatchers\pageDispatcher.js"; DestDir: "{app}\playwright\driver\package\lib\server\dispatchers"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\dispatchers\playwrightDispatcher.js"; DestDir: "{app}\playwright\driver\package\lib\server\dispatchers"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\dispatchers\streamDispatcher.js"; DestDir: "{app}\playwright\driver\package\lib\server\dispatchers"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\dispatchers\tracingDispatcher.js"; DestDir: "{app}\playwright\driver\package\lib\server\dispatchers"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\dispatchers\webSocketRouteDispatcher.js"; DestDir: "{app}\playwright\driver\package\lib\server\dispatchers"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\dispatchers\writableStreamDispatcher.js"; DestDir: "{app}\playwright\driver\package\lib\server\dispatchers"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\electron\electron.js"; DestDir: "{app}\playwright\driver\package\lib\server\electron"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\electron\loader.js"; DestDir: "{app}\playwright\driver\package\lib\server\electron"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\firefox\ffBrowser.js"; DestDir: "{app}\playwright\driver\package\lib\server\firefox"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\firefox\ffConnection.js"; DestDir: "{app}\playwright\driver\package\lib\server\firefox"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\firefox\ffExecutionContext.js"; DestDir: "{app}\playwright\driver\package\lib\server\firefox"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\firefox\ffInput.js"; DestDir: "{app}\playwright\driver\package\lib\server\firefox"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\firefox\ffNetworkManager.js"; DestDir: "{app}\playwright\driver\package\lib\server\firefox"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\firefox\ffPage.js"; DestDir: "{app}\playwright\driver\package\lib\server\firefox"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\firefox\firefox.js"; DestDir: "{app}\playwright\driver\package\lib\server\firefox"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\firefox\protocol.d.js"; DestDir: "{app}\playwright\driver\package\lib\server\firefox"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\har\harRecorder.js"; DestDir: "{app}\playwright\driver\package\lib\server\har"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\har\harTracer.js"; DestDir: "{app}\playwright\driver\package\lib\server\har"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\recorder\chat.js"; DestDir: "{app}\playwright\driver\package\lib\server\recorder"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\recorder\recorderApp.js"; DestDir: "{app}\playwright\driver\package\lib\server\recorder"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\recorder\recorderRunner.js"; DestDir: "{app}\playwright\driver\package\lib\server\recorder"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\recorder\recorderSignalProcessor.js"; DestDir: "{app}\playwright\driver\package\lib\server\recorder"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\recorder\recorderUtils.js"; DestDir: "{app}\playwright\driver\package\lib\server\recorder"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\recorder\throttledFile.js"; DestDir: "{app}\playwright\driver\package\lib\server\recorder"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\registry\browserFetcher.js"; DestDir: "{app}\playwright\driver\package\lib\server\registry"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\registry\dependencies.js"; DestDir: "{app}\playwright\driver\package\lib\server\registry"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\registry\index.js"; DestDir: "{app}\playwright\driver\package\lib\server\registry"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\registry\nativeDeps.js"; DestDir: "{app}\playwright\driver\package\lib\server\registry"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\registry\oopDownloadBrowserMain.js"; DestDir: "{app}\playwright\driver\package\lib\server\registry"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\trace\recorder\snapshotter.js"; DestDir: "{app}\playwright\driver\package\lib\server\trace\recorder"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\trace\recorder\snapshotterInjected.js"; DestDir: "{app}\playwright\driver\package\lib\server\trace\recorder"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\trace\recorder\tracing.js"; DestDir: "{app}\playwright\driver\package\lib\server\trace\recorder"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\trace\test\inMemorySnapshotter.js"; DestDir: "{app}\playwright\driver\package\lib\server\trace\test"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\trace\viewer\traceViewer.js"; DestDir: "{app}\playwright\driver\package\lib\server\trace\viewer"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\utils\ascii.js"; DestDir: "{app}\playwright\driver\package\lib\server\utils"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\utils\comparators.js"; DestDir: "{app}\playwright\driver\package\lib\server\utils"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\utils\crypto.js"; DestDir: "{app}\playwright\driver\package\lib\server\utils"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\utils\debug.js"; DestDir: "{app}\playwright\driver\package\lib\server\utils"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\utils\debugLogger.js"; DestDir: "{app}\playwright\driver\package\lib\server\utils"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\utils\env.js"; DestDir: "{app}\playwright\driver\package\lib\server\utils"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\utils\eventsHelper.js"; DestDir: "{app}\playwright\driver\package\lib\server\utils"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\utils\expectUtils.js"; DestDir: "{app}\playwright\driver\package\lib\server\utils"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\utils\fileUtils.js"; DestDir: "{app}\playwright\driver\package\lib\server\utils"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\utils\happyEyeballs.js"; DestDir: "{app}\playwright\driver\package\lib\server\utils"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\utils\hostPlatform.js"; DestDir: "{app}\playwright\driver\package\lib\server\utils"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\utils\httpServer.js"; DestDir: "{app}\playwright\driver\package\lib\server\utils"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\utils\imageUtils.js"; DestDir: "{app}\playwright\driver\package\lib\server\utils"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\utils\linuxUtils.js"; DestDir: "{app}\playwright\driver\package\lib\server\utils"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\utils\network.js"; DestDir: "{app}\playwright\driver\package\lib\server\utils"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\utils\nodePlatform.js"; DestDir: "{app}\playwright\driver\package\lib\server\utils"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\utils\pipeTransport.js"; DestDir: "{app}\playwright\driver\package\lib\server\utils"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\utils\processLauncher.js"; DestDir: "{app}\playwright\driver\package\lib\server\utils"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\utils\profiler.js"; DestDir: "{app}\playwright\driver\package\lib\server\utils"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\utils\socksProxy.js"; DestDir: "{app}\playwright\driver\package\lib\server\utils"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\utils\spawnAsync.js"; DestDir: "{app}\playwright\driver\package\lib\server\utils"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\utils\task.js"; DestDir: "{app}\playwright\driver\package\lib\server\utils"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\utils\userAgent.js"; DestDir: "{app}\playwright\driver\package\lib\server\utils"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\utils\wsServer.js"; DestDir: "{app}\playwright\driver\package\lib\server\utils"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\utils\zipFile.js"; DestDir: "{app}\playwright\driver\package\lib\server\utils"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\utils\zones.js"; DestDir: "{app}\playwright\driver\package\lib\server\utils"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\utils\image_tools\colorUtils.js"; DestDir: "{app}\playwright\driver\package\lib\server\utils\image_tools"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\utils\image_tools\compare.js"; DestDir: "{app}\playwright\driver\package\lib\server\utils\image_tools"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\utils\image_tools\imageChannel.js"; DestDir: "{app}\playwright\driver\package\lib\server\utils\image_tools"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\utils\image_tools\stats.js"; DestDir: "{app}\playwright\driver\package\lib\server\utils\image_tools"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\webkit\protocol.d.js"; DestDir: "{app}\playwright\driver\package\lib\server\webkit"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\webkit\webkit.js"; DestDir: "{app}\playwright\driver\package\lib\server\webkit"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\webkit\wkBrowser.js"; DestDir: "{app}\playwright\driver\package\lib\server\webkit"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\webkit\wkConnection.js"; DestDir: "{app}\playwright\driver\package\lib\server\webkit"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\webkit\wkExecutionContext.js"; DestDir: "{app}\playwright\driver\package\lib\server\webkit"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\webkit\wkInput.js"; DestDir: "{app}\playwright\driver\package\lib\server\webkit"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\webkit\wkInterceptableRequest.js"; DestDir: "{app}\playwright\driver\package\lib\server\webkit"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\webkit\wkPage.js"; DestDir: "{app}\playwright\driver\package\lib\server\webkit"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\webkit\wkProvisionalPage.js"; DestDir: "{app}\playwright\driver\package\lib\server\webkit"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\server\webkit\wkWorkers.js"; DestDir: "{app}\playwright\driver\package\lib\server\webkit"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\third_party\pixelmatch.js"; DestDir: "{app}\playwright\driver\package\lib\third_party"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\utils\isomorphic\ariaSnapshot.js"; DestDir: "{app}\playwright\driver\package\lib\utils\isomorphic"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\utils\isomorphic\assert.js"; DestDir: "{app}\playwright\driver\package\lib\utils\isomorphic"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\utils\isomorphic\colors.js"; DestDir: "{app}\playwright\driver\package\lib\utils\isomorphic"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\utils\isomorphic\cssParser.js"; DestDir: "{app}\playwright\driver\package\lib\utils\isomorphic"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\utils\isomorphic\cssTokenizer.js"; DestDir: "{app}\playwright\driver\package\lib\utils\isomorphic"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\utils\isomorphic\headers.js"; DestDir: "{app}\playwright\driver\package\lib\utils\isomorphic"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\utils\isomorphic\locatorGenerators.js"; DestDir: "{app}\playwright\driver\package\lib\utils\isomorphic"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\utils\isomorphic\locatorParser.js"; DestDir: "{app}\playwright\driver\package\lib\utils\isomorphic"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\utils\isomorphic\locatorUtils.js"; DestDir: "{app}\playwright\driver\package\lib\utils\isomorphic"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\utils\isomorphic\manualPromise.js"; DestDir: "{app}\playwright\driver\package\lib\utils\isomorphic"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\utils\isomorphic\mimeType.js"; DestDir: "{app}\playwright\driver\package\lib\utils\isomorphic"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\utils\isomorphic\multimap.js"; DestDir: "{app}\playwright\driver\package\lib\utils\isomorphic"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\utils\isomorphic\protocolFormatter.js"; DestDir: "{app}\playwright\driver\package\lib\utils\isomorphic"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\utils\isomorphic\protocolMetainfo.js"; DestDir: "{app}\playwright\driver\package\lib\utils\isomorphic"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\utils\isomorphic\rtti.js"; DestDir: "{app}\playwright\driver\package\lib\utils\isomorphic"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\utils\isomorphic\selectorParser.js"; DestDir: "{app}\playwright\driver\package\lib\utils\isomorphic"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\utils\isomorphic\semaphore.js"; DestDir: "{app}\playwright\driver\package\lib\utils\isomorphic"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\utils\isomorphic\stackTrace.js"; DestDir: "{app}\playwright\driver\package\lib\utils\isomorphic"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\utils\isomorphic\stringUtils.js"; DestDir: "{app}\playwright\driver\package\lib\utils\isomorphic"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\utils\isomorphic\time.js"; DestDir: "{app}\playwright\driver\package\lib\utils\isomorphic"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\utils\isomorphic\timeoutRunner.js"; DestDir: "{app}\playwright\driver\package\lib\utils\isomorphic"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\utils\isomorphic\traceUtils.js"; DestDir: "{app}\playwright\driver\package\lib\utils\isomorphic"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\utils\isomorphic\types.js"; DestDir: "{app}\playwright\driver\package\lib\utils\isomorphic"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\utils\isomorphic\urlMatch.js"; DestDir: "{app}\playwright\driver\package\lib\utils\isomorphic"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\utils\isomorphic\utilityScriptSerializers.js"; DestDir: "{app}\playwright\driver\package\lib\utils\isomorphic"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\utilsBundleImpl\index.js"; DestDir: "{app}\playwright\driver\package\lib\utilsBundleImpl"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\vite\htmlReport\index.html"; DestDir: "{app}\playwright\driver\package\lib\vite\htmlReport"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\vite\recorder\index.html"; DestDir: "{app}\playwright\driver\package\lib\vite\recorder"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\vite\recorder\playwright-logo.svg"; DestDir: "{app}\playwright\driver\package\lib\vite\recorder"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\vite\recorder\assets\codeMirrorModule-BoWUGj0J.js"; DestDir: "{app}\playwright\driver\package\lib\vite\recorder\assets"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\vite\recorder\assets\codeMirrorModule-C3UTv-Ge.css"; DestDir: "{app}\playwright\driver\package\lib\vite\recorder\assets"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\vite\recorder\assets\index-DJqDAOZp.js"; DestDir: "{app}\playwright\driver\package\lib\vite\recorder\assets"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\vite\recorder\assets\index-Ri0uHF7I.css"; DestDir: "{app}\playwright\driver\package\lib\vite\recorder\assets"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\vite\traceViewer\codeMirrorModule.C3UTv-Ge.css"; DestDir: "{app}\playwright\driver\package\lib\vite\traceViewer"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\vite\traceViewer\defaultSettingsView.ConWv5KN.css"; DestDir: "{app}\playwright\driver\package\lib\vite\traceViewer"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\vite\traceViewer\index.BxQ34UMZ.js"; DestDir: "{app}\playwright\driver\package\lib\vite\traceViewer"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\vite\traceViewer\index.C4Y3Aw8n.css"; DestDir: "{app}\playwright\driver\package\lib\vite\traceViewer"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\vite\traceViewer\index.html"; DestDir: "{app}\playwright\driver\package\lib\vite\traceViewer"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\vite\traceViewer\playwright-logo.svg"; DestDir: "{app}\playwright\driver\package\lib\vite\traceViewer"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\vite\traceViewer\snapshot.html"; DestDir: "{app}\playwright\driver\package\lib\vite\traceViewer"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\vite\traceViewer\sw.bundle.js"; DestDir: "{app}\playwright\driver\package\lib\vite\traceViewer"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\vite\traceViewer\uiMode.BWTwXl41.js"; DestDir: "{app}\playwright\driver\package\lib\vite\traceViewer"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\vite\traceViewer\uiMode.Btcz36p_.css"; DestDir: "{app}\playwright\driver\package\lib\vite\traceViewer"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\vite\traceViewer\uiMode.html"; DestDir: "{app}\playwright\driver\package\lib\vite\traceViewer"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\vite\traceViewer\xtermModule.DYP7pi_n.css"; DestDir: "{app}\playwright\driver\package\lib\vite\traceViewer"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\vite\traceViewer\assets\codeMirrorModule-Bucv2d7q.js"; DestDir: "{app}\playwright\driver\package\lib\vite\traceViewer\assets"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\vite\traceViewer\assets\defaultSettingsView-BEpdCv1S.js"; DestDir: "{app}\playwright\driver\package\lib\vite\traceViewer\assets"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\lib\vite\traceViewer\assets\xtermModule-CsJ4vdCR.js"; DestDir: "{app}\playwright\driver\package\lib\vite\traceViewer\assets"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\types\protocol.d.ts"; DestDir: "{app}\playwright\driver\package\types"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\types\structs.d.ts"; DestDir: "{app}\playwright\driver\package\types"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\playwright\driver\package\types\types.d.ts"; DestDir: "{app}\playwright\driver\package\types"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\propcache\_helpers_c.pyd"; DestDir: "{app}\propcache"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\psutil\_psutil_windows.pyd"; DestDir: "{app}\psutil"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\shiboken6\Shiboken.pyd"; DestDir: "{app}\shiboken6"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\shiboken6\msvcp140.dll"; DestDir: "{app}\shiboken6"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\shiboken6\msvcp140_1.dll"; DestDir: "{app}\shiboken6"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\shiboken6\msvcp140_2.dll"; DestDir: "{app}\shiboken6"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\shiboken6\msvcp140_codecvt_ids.dll"; DestDir: "{app}\shiboken6"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\ui\img\LOGO 3.png"; DestDir: "{app}\ui\img"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\ui\img\LOGO 4.png"; DestDir: "{app}\ui\img"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\ui\img\LOGO VAD 2.png"; DestDir: "{app}\ui\img"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\ui\img\LOGO VAD.png"; DestDir: "{app}\ui\img"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\ui\img\Logo-Zalo5.png"; DestDir: "{app}\ui\img"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\websockets\speedups.pyd"; DestDir: "{app}\websockets"; Flags: ignoreversion
Source: "D:\Music\Ruby\Produce for Customer\##Tools\VEO Tool\#NEW VEO API\03 - Final App Client\main.dist\yarl\_quoting_c.pyd"; DestDir: "{app}\yarl"; Flags: ignoreversion

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
