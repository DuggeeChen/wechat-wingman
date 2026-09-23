' WeChat Wingman — silent launcher
' 双击不弹控制台窗口；只有出错时才弹提示框。
Option Explicit

Dim shell, fso, folder, bat, cmd, rc
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

folder = fso.GetParentFolderName(WScript.ScriptFullName)
bat = fso.BuildPath(folder, "launch.bat")

If Not fso.FileExists(bat) Then
    MsgBox "launch.bat was not found next to this script.", vbCritical, "WeChat Wingman"
    WScript.Quit 1
End If

cmd = "cmd /c " & Chr(34) & bat & Chr(34) & " /quiet"
rc = shell.Run(cmd, 0, True)

If rc <> 0 Then
    MsgBox "WeChat Wingman could not start (exit code " & rc & ")." & vbCrLf & vbCrLf & _
           "Double-click launch.bat directly to see the error message.", _
           vbCritical, "WeChat Wingman"
End If
