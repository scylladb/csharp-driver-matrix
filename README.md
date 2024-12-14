# [WIP] C# Driver Matrix

## Prerequisites
Ensure the following are installed before proceeding:
* Python3.12
* pip
* git
* docker

## Installing dependencies

* Install .NET 8 SDK (version 7 and below are no longer supported)
```bash
sudo apt update && sudo apt install -y dotnet-sdk-8.0
```

* Repository dependencies  
Ensure all repositories are cloned into **the same base folder**
```bash
git clone git@github.com:datastax/csharp-driver.git datastax-csharp-driver &
git clone git@github.com:scylladb/scylla-ccm.git scylla-ccm &
git clone git@github.com:dimakr/csharp-driver-matrix.git csharp-driver-matrix  # TODO: change to scylladb org, when the repo is landed there  
wait
```

* Install scylla-ccm and python dependencies in the dedicated virtual environment (e.g. managed with pyenv)
```bash
cd csaharp-driver-matrix
pyenv activate scylla-ccm
pip install ../scylla-ccm
pip install -r scripts/requirements.txt
```

## Run test locally

**NOTE:** The `/usr/local/bin/ccm` path to the `ccm` binary is hardcoded in the driver tests. So if the ccm binary is located
elsewhere in the system (e.g. in a Python virtual environment), create a symlink to the expected location:
```bash
sudo ln -s "$(which ccm)" /usr/local/bin/ccm
```
Verify that `ccm` is accessible:
```bash
/usr/local/bin/ccm help
```
#### Run Datastax driver integration tests
```bash
python3 main.py ../datastax-csharp-driver --tests integration --versions 3.22.0 --scylla-version release:6.2
```

