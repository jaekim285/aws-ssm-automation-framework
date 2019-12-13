Import-Module AWSPowerShell
# ---- VARIABLES ----
$Binaries = '{{ Binaries }}'

# ---- FUNCTIONS -----
function Install-Dynatrace
{
    [CmdletBinding(SupportsShouldProcess = $true)]
    param
    (
        [Parameter(Mandatory = $true)]
        [ValidateNotNullOrEmpty()]
        [String]$Bucket,

        [Parameter(Mandatory = $false)]
        [ValidateNotNullOrEmpty()]
        [String]$TempDirectory = $env:TEMP,

        [Parameter(Mandatory = $false)]
        [ValidateNotNullOrEmpty()]
        [String]$DynatraceFile = 'Dynatrace-OneAgent-Windows-1.169.172.exe'
    )

    if ($PSCmdlet.ShouldProcess('Self', 'Install of Dynatrace'))
    {
        $DynatraceInstalled = Get-Service -Name 'Dynatrace OneAgent'

        if (-not ($DynatraceInstalled))
        {
            Write-Verbose -Message "Downloading Dynatrace from S3:$Bucket to $TempDirectory"
            Copy-S3Object -BucketName $Bucket -KeyPrefix Dynatrace -LocalFolder $TempDirectory

            Write-Verbose -Message 'Starting Dynatrace installation'
            Invoke-Expression -Command "$env:TEMP\install.bat"

            Write-Verbose -Message 'Installation Complete'
        }
        else
        {
            Write-Output 'Dynatrace is already installed. Skipping installation.'
        }
    }
}

# ---- MAIN -----
try
{
    Install-Dynatrace -Bucket $Binaries -Verbose
    exit 0
}
catch
{
    throw $_.Exception
    exit 1
}