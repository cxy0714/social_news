# 每日 digest 计划任务 wrapper。
# 由 setup_task.ps1 注册的 Windows 计划任务调用；也可手动 `pwsh scripts/run_daily.ps1`。
# 负责：定位仓库根 → 选 python → 跑 generate_digest.py --commit → 写日志。
#
# 用法（手动）:
#   powershell -ExecutionPolicy Bypass -File scripts\run_daily.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\run_daily.ps1 -Hours 48 -NoCommit

param(
    [int]$Hours = 24,
    [int]$MaxItems = 120,
    [switch]$NoCommit
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot   # scripts/ 的上一级
Set-Location $RepoRoot

# 选 python：优先仓库内 .venv，其次 PATH 上的 python。
$Py = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) { $Py = "python" }

# 日志目录（gitignore）。
$LogDir = Join-Path $RepoRoot "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Stamp = Get-Date -Format "yyyy-MM-dd"
$Log = Join-Path $LogDir "digest-$Stamp.log"

$Args = @("scripts/generate_digest.py", "--hours", $Hours, "--max-items", $MaxItems)
if (-not $NoCommit) { $Args += "--commit" }

"===== $(Get-Date -Format 'u') 开始生成 digest =====" | Tee-Object -FilePath $Log -Append
& $Py @Args 2>&1 | Tee-Object -FilePath $Log -Append
$code = $LASTEXITCODE
"===== 结束，退出码 $code =====" | Tee-Object -FilePath $Log -Append
exit $code
