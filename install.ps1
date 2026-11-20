# Jarvis — one-time setup on a new Windows PC.
#   powershell -ExecutionPolicy Bypass -File install.ps1
# Needs: Python 3.12, Node.js 18+, Ollama (https://ollama.com), an NVIDIA GPU is optional.
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

Write-Host "1/5 uv (Python package manager)" -ForegroundColor Cyan
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}

Write-Host "2/5 Python dependencies" -ForegroundColor Cyan
uv sync --python 3.12

Write-Host "3/5 WhatsApp bridge (Node)" -ForegroundColor Cyan
Push-Location whatsapp-bridge
npm install --no-fund --no-audit
Pop-Location

Write-Host "4/5 Voices (Piper, Russian)" -ForegroundColor Cyan
New-Item -ItemType Directory -Force voices | Out-Null
foreach ($v in 'dmitri', 'denis', 'irina', 'ruslan') {
    foreach ($ext in 'onnx', 'onnx.json') {
        $out = "voices\ru_RU-$v-medium.$ext"
        if (-not (Test-Path $out)) {
            Invoke-WebRequest "https://huggingface.co/rhasspy/piper-voices/resolve/main/ru/ru_RU/$v/medium/ru_RU-$v-medium.$ext" -OutFile $out -UseBasicParsing
        }
    }
}

# Semantic memory model (finds notes by meaning, runs on the CPU)
New-Item -ItemType Directory -Force models\minilm\onnx | Out-Null
foreach ($f in 'onnx/model_quantized.onnx', 'tokenizer.json') {
    $out = "models\minilm\$($f -replace '/', '\')"
    if (-not (Test-Path $out)) {
        Invoke-WebRequest "https://huggingface.co/Xenova/paraphrase-multilingual-MiniLM-L12-v2/resolve/main/$f" -OutFile $out -UseBasicParsing
    }
}

# Voice ID model (tells your voice from others, runs on the CPU)
New-Item -ItemType Directory -Force models\speaker | Out-Null
if (-not (Test-Path models\speaker\voxceleb_resnet34_LM.onnx)) {
    Invoke-WebRequest "https://huggingface.co/Wespeaker/wespeaker-voxceleb-resnet34-LM/resolve/main/voxceleb_resnet34_LM.onnx" -OutFile models\speaker\voxceleb_resnet34_LM.onnx -UseBasicParsing
}

Write-Host "5/5 Language model + shortcuts" -ForegroundColor Cyan
if (Get-Command ollama -ErrorAction SilentlyContinue) { ollama pull qwen3.5:2b }
$ws = New-Object -ComObject WScript.Shell
$ps = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$start = Join-Path $PSScriptRoot 'start-hidden.ps1'
function MakeLnk($path, $extra) {
    $s = $ws.CreateShortcut($path); $s.TargetPath = $ps
    $s.Arguments = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$start`" $extra"
    $s.WorkingDirectory = $PSScriptRoot; $s.WindowStyle = 7; $s.Save()
}
MakeLnk "$([Environment]::GetFolderPath('Startup'))\Jarvis assistant.lnk" ''
MakeLnk "$([Environment]::GetFolderPath('Desktop'))\Jarvis.lnk" '-App'
MakeLnk "$([Environment]::GetFolderPath('Programs'))\Jarvis.lnk" '-App'
Write-Host "Done. Start Jarvis with the 'Jarvis' desktop shortcut." -ForegroundColor Green
