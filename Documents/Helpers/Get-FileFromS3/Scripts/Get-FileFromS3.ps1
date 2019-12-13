Import-Module AWSPowerShell

# ---- VARIABLES ----
$S3Path  = '{{ S3Path }}'
$LocalPath = '{{ LocalPath }}'

# ---- FUNCTIONS -----
function Get-FileFromS3
{
    [CmdletBinding(SupportsShouldProcess = $true)]
    param
    (
        [Parameter(Mandatory = $true)]
        [ValidateNotNullOrEmpty()]
        [String]$Path = 's3://',

        [Parameter(Mandatory = $false)]
        [ValidateNotNullOrEmpty()]
        [String]$LocalPath = 'C:\',

        [Parameter(Mandatory = $false)]
        [ValidateNotNullOrEmpty()]
        [String]$Region = 'us-west-2'
    )

    if ($PSCmdlet.ShouldProcess('Self', 'Install of Dynatrace'))
    {
        $BucketPattern = "s3://(.*?)/"
        $Bucket = [regex]::match($Path, $BucketPattern).Groups[1].Value

        $KeyPattern = "s3://$Bucket/(.*)"
        $Key = [regex]::match($Path, $KeyPattern).Groups[1].value

        $FileName = [System.IO.Path]::GetFileName($Key)

        Copy-S3Object -Region $Region -Bucket $Bucket -Key $Key -LocalFile "$LocalPath\$FileName" -Force
    }
}

# ---- MAIN -----
try
{
    $Region = (Invoke-WebRequest -UseBasicParsing -Uri http://169.254.169.254/latest/dynamic/instance-identity/document | ConvertFrom-Json | Select region).region
    Get-FileFromS3 -Path $S3Path -LocalPath $LocalPath -Region $Region
}
catch
{
    throw $_.Exception.Message
}
