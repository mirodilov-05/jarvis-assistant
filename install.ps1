# Jarvis: полный анализ ноутбука, установка недостающего и первый запуск.
# Обычный путь: двойной щелчок по INSTALL.bat.
#   install.ps1              анализ, затем вопрос, затем установка
#   install.ps1 -Yes         без вопроса
#   install.ps1 -CheckOnly   только анализ, ничего не меняет
#   install.ps1 -NoShortcuts -NoStart   для проверки установщика
param([switch]$Yes, [switch]$CheckOnly, [switch]$NoShortcuts, [switch]$NoStart)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}
Set-Location -LiteralPath $PSScriptRoot
$root = $PSScriptRoot
$log = Join-Path $root 'install.log'
"=== $(Get-Date -Format s) ===" | Out-File $log -Append -Encoding utf8

function Say($text, $color = 'Gray') { Write-Host $text -ForegroundColor $color; $text | Out-File $log -Append -Encoding utf8 }
function Row($ok, $name, $detail) {
    $mark = @{ ok = '[ есть ]'; no = '[ нет  ]'; warn = '[внимание]'; opt = '[по желанию]' }[$ok]
    $col = @{ ok = 'Green'; no = 'Red'; warn = 'Yellow'; opt = 'DarkGray' }[$ok]
    Say ("{0,-13} {1}{2}" -f $mark, $name, $(if ($detail) { ": $detail" } else { '' })) $col
}
function Find-Uv {
    $c = Get-Command uv -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    $p = Join-Path $env:USERPROFILE '.local\bin\uv.exe'
    if (Test-Path -LiteralPath $p) { return $p }
    return $null
}
function Get-File($url, $out) {
    for ($i = 1; $i -le 3; $i++) {
        try {
            Invoke-WebRequest $url -OutFile "$out.part" -UseBasicParsing -TimeoutSec 600
            Move-Item -LiteralPath "$out.part" -Destination $out -Force
            return
        } catch { if ($i -eq 3) { throw }; Start-Sleep -Seconds (3 * $i) }
    }
}

# ------------------------------------------------------------------ 1. анализ
Say ''
Say '  JARVIS: анализ ноутбука' Cyan
Say ''
$os = Get-CimInstance Win32_OperatingSystem
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
$ram = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)
$gpu = @(Get-CimInstance Win32_VideoController | ForEach-Object { $_.Name })
$drive = Get-PSDrive -Name ($root.Substring(0, 1)) -ErrorAction SilentlyContinue
$free = if ($drive) { [math]::Round($drive.Free / 1GB) } else { 0 }
$nvidia = [bool](Get-Command nvidia-smi -ErrorAction SilentlyContinue)
Say ("  {0}, сборка {1}" -f $os.Caption, $os.BuildNumber)
Say ("  {0}, потоков {1}" -f $cpu.Name.Trim(), $cpu.NumberOfLogicalProcessors)
Say ("  Память {0} ГБ, видео: {1}" -f $ram, ($gpu -join ', '))
Say ''

$stop = @()
if ([int]$os.BuildNumber -lt 17763 -or -not [Environment]::Is64BitOperatingSystem) { Row 'no' 'Windows 10/11 64-бит' 'эта Windows не подходит'; $stop += 'Windows' } else { Row 'ok' 'Windows 10/11 64-бит' }
if ($ram -lt 4) { Row 'no' 'Память' "$ram ГБ, нужно 4 ГБ"; $stop += 'память' } elseif ($ram -lt 8) { Row 'warn' 'Память' "$ram ГБ, лучше 8 ГБ. Настрою лёгкий режим" } else { Row 'ok' 'Память' "$ram ГБ" }
$need = if ($nvidia) { 8 } else { 5 }
if ($free -lt $need) { Row 'no' 'Место на диске' "свободно $free ГБ, нужно $need ГБ"; $stop += 'место на диске' } else { Row 'ok' 'Место на диске' "свободно $free ГБ" }
$net = $false
try { $net = (Invoke-WebRequest 'https://pypi.org/simple/pip/' -Method Head -UseBasicParsing -TimeoutSec 15).StatusCode -eq 200 } catch {}
if ($net) { Row 'ok' 'Интернет' } else { Row 'no' 'Интернет' 'нет связи с pypi.org'; $stop += 'интернет' }
if ($root -match '[^\x00-\x7F]') { Row 'warn' 'Папка' 'в пути есть русские буквы. Надёжнее C:\Jarvis' }
if ($root -match 'OneDrive') { Row 'warn' 'Папка' 'лежит в OneDrive: он будет постоянно загружать файлы. Надёжнее C:\Jarvis' }
$sac = try { (Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\CI\Policy' -ErrorAction Stop).VerifiedAndReputablePolicyState } catch { 0 }
if ($sac -eq 1) { Row 'warn' 'Smart App Control' 'включён и может блокировать библиотеки. Решаете вы, установщик его не трогает' }

$todo = [ordered]@{}
$uv = Find-Uv
if ($uv) { Row 'ok' 'uv (ставит Python и библиотеки)' } else { Row 'no' 'uv (ставит Python и библиотеки)' 'около 20 МБ'; $todo['uv'] = 1 }
if (Test-Path "$env:SystemRoot\System32\msvcp140.dll") { Row 'ok' 'Microsoft Visual C++' } else { Row 'no' 'Microsoft Visual C++' 'около 25 МБ, Windows спросит разрешение'; $todo['vc'] = 1 }
if (Test-Path '.venv\Scripts\pythonw.exe') { Row 'ok' 'Python и библиотеки' 'обновлю, если изменились' } else { Row 'no' 'Python 3.12 и библиотеки' 'около 600 МБ' }
$todo['deps'] = 1
if ($nvidia) { Row 'ok' 'Видеокарта NVIDIA' 'поставлю её библиотеки, около 1 ГБ' } else { Row 'opt' 'Видеокарта NVIDIA' 'нет, речь пойдёт через облако или процессор' }
$voices = 'dmitri', 'denis', 'irina', 'ruslan'
$vmiss = @($voices | Where-Object { -not (Test-Path "voices\ru_RU-$_-medium.onnx") })
if ($vmiss.Count) { Row 'no' 'Русские голоса' 'около 250 МБ'; $todo['voices'] = 1 } else { Row 'ok' 'Русские голоса' }
$models = [ordered]@{
    'models\minilm\onnx\model_quantized.onnx'    = 'https://huggingface.co/Xenova/paraphrase-multilingual-MiniLM-L12-v2/resolve/main/onnx/model_quantized.onnx'
    'models\minilm\tokenizer.json'               = 'https://huggingface.co/Xenova/paraphrase-multilingual-MiniLM-L12-v2/resolve/main/tokenizer.json'
    'models\speaker\voxceleb_resnet34_LM.onnx'   = 'https://huggingface.co/Wespeaker/wespeaker-voxceleb-resnet34-LM/resolve/main/voxceleb_resnet34_LM.onnx'
}
$mmiss = @($models.Keys | Where-Object { -not (Test-Path $_) })
if ($mmiss.Count) { Row 'no' 'Модели памяти и голоса' 'около 150 МБ'; $todo['models'] = 1 } else { Row 'ok' 'Модели памяти и голоса' }
$npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
if ($npm) { Row 'ok' 'Node.js (только для WhatsApp)'; if (-not (Test-Path 'whatsapp-bridge\node_modules')) { $todo['npm'] = 1 } } else { Row 'opt' 'Node.js (только для WhatsApp)' 'можно поставить потом' }
$mic = @(Get-CimInstance Win32_SoundDevice).Count -gt 0
if ($mic) { Row 'ok' 'Звуковое устройство' } else { Row 'warn' 'Звуковое устройство' 'не найдено, подключите гарнитуру' }
Say ''

if ($stop.Count) { Say ("Установка невозможна, мешает: " + ($stop -join ', ')) Red; exit 1 }
if ($CheckOnly) { Say 'Это была только проверка, ничего не изменено.' Cyan; exit 0 }
if (-not $Yes) {
    $a = Read-Host 'Установить недостающее? (д/н)'
    if ($a -notmatch '^(д|да|y|yes)$') { Say 'Отменено, ничего не изменено.' Yellow; exit 0 }
}

# ------------------------------------------------------------------ 2. установка
$failed = @()
function Step($name, [scriptblock]$do, [switch]$Required) {
    Say ''; Say "> $name" Cyan
    try { & $do; Say '  готово' Green }
    catch {
        Say ("  не получилось: " + $_.Exception.Message) Red
        $script:failed += $name
        if ($Required) { Say "Без этого Джарвис не запустится. Подробности: $log" Red; exit 1 }
    }
}
function Native([string]$exe, [string[]]$arguments) {
    # native tools write progress to stderr: only the exit code says whether they failed
    $old = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    & $exe @arguments 2>&1 | ForEach-Object { "$_" | Out-File $log -Append -Encoding utf8; Write-Host "    $_" -ForegroundColor DarkGray }
    $code = $LASTEXITCODE; $ErrorActionPreference = $old
    if ($code -ne 0) { throw "$exe завершился с кодом $code" }
}

if ($todo.Contains('uv')) {
    Step 'Менеджер uv' -Required { Invoke-RestMethod https://astral.sh/uv/install.ps1 -TimeoutSec 120 | Invoke-Expression; if (-not (Find-Uv)) { throw 'uv не найден после установки' } }
}
if ($todo.Contains('vc')) {
    Step 'Microsoft Visual C++' { Native 'winget' @('install', '-e', '--id', 'Microsoft.VCRedist.2015+.x64', '--silent', '--accept-package-agreements', '--accept-source-agreements') }
}
Step 'Python 3.12 и библиотеки (самый долгий шаг)' -Required {
    $sync = @('sync', '--frozen', '--python', '3.12')
    if ($nvidia) { $sync += @('--extra', 'gpu') }
    Native (Find-Uv) $sync
}
if ($todo.Contains('voices')) {
    Step 'Русские голоса' {
        New-Item -ItemType Directory -Force voices | Out-Null
        foreach ($v in $voices) {
            foreach ($ext in 'onnx.json', 'onnx') {
                $out = "voices\ru_RU-$v-medium.$ext"
                if (-not (Test-Path $out)) { Get-File "https://huggingface.co/rhasspy/piper-voices/resolve/main/ru/ru_RU/$v/medium/ru_RU-$v-medium.$ext" $out }
            }
        }
    }
}
if ($todo.Contains('models')) {
    Step 'Модели памяти и голоса' {
        foreach ($m in $mmiss) { New-Item -ItemType Directory -Force (Split-Path $m) | Out-Null; Get-File $models[$m] $m }
    }
}
if ($todo.Contains('npm')) {
    Step 'Мост WhatsApp' { Push-Location whatsapp-bridge; try { Native $npm.Source @('install', '--no-fund', '--no-audit') } finally { Pop-Location } }
}
if (-not $NoShortcuts) {
    Step 'Ярлыки и автозапуск' {
        $ws = New-Object -ComObject WScript.Shell
        $ps = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
        $start = Join-Path $root 'start-hidden.ps1'
        $places = @(@([Environment]::GetFolderPath('Startup'), 'Jarvis assistant.lnk', ''), @([Environment]::GetFolderPath('Desktop'), 'Jarvis.lnk', '-App'), @([Environment]::GetFolderPath('Programs'), 'Jarvis.lnk', '-App'))
        foreach ($p in $places) {
            $s = $ws.CreateShortcut((Join-Path $p[0] $p[1])); $s.TargetPath = $ps
            $s.Arguments = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$start`" $($p[2])"
            $s.WorkingDirectory = $root; $s.WindowStyle = 7
            $ico = Join-Path $root 'web\jarvis.ico'; if (Test-Path -LiteralPath $ico) { $s.IconLocation = $ico }
            $s.Save()
        }
    }
}

# ------------------------------------------------------------------ 3. проверка и анализ
Say ''; Say '> Проверка после установки' Cyan
$py = Join-Path $root '.venv\Scripts\python.exe'
$ErrorActionPreference = 'Continue'
& $py -X utf8 setup_doctor.py 2>&1 | ForEach-Object { Say "  $_" }
Say ''; Say '> Полный анализ и план оптимизации' Cyan
& $py -X utf8 optimizer.py 2>&1 | ForEach-Object { Say "  $_" }
Say ''
if ($failed.Count) { Say ('Не получилось: ' + ($failed -join ', ') + '. Запустите INSTALL.bat ещё раз, он продолжит с этого места.') Yellow }
if ($NoStart) { exit 0 }
Say 'Запускаю Джарвиса. Откроется окно «Анализ ноутбука»: отметьте нужное и нажмите «Сделать отмеченное».' Green
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root 'start-hidden.ps1') -App
