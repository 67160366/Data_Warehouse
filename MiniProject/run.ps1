param([Parameter(Mandatory=$true)][ValidateSet("setup","data","etl","test","app","all")][string]$Command)
python .\run.py $Command @args
exit $LASTEXITCODE
