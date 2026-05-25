$filePath = "api/webui/src/pages/ResearchModulePages.tsx"
$lines = [System.IO.File]::ReadAllLines($filePath)
$top = $lines[0..3799]
$bot = $lines[3896..($lines.Length-1)]
$result = $top + @('') + $bot
[System.IO.File]::WriteAllLines($filePath, $result)
Write-Host "Done. Removed lines 3801-3897. New total: $($result.Length)"
