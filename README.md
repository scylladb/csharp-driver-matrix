# C# Driver Matrix

## Pre-release integration gate

The reusable workflow `.github/workflows/driver-integration-matrix.yml` runs the
same five lanes as this repository's PR CI: DataStax C# driver against Scylla
`LATEST`, plus Scylla C# driver against `LATEST`, `PRIOR`, `LTS-LATEST`, and
`LTS-PRIOR`. Set `run_datastax` or `run_scylla` to `false` to disable that driver
group. A Scylla release caller can pass an untagged commit and its intended
version so the runner selects the matching patch and ignore files.

For example, add this job to `scylladb/csharp-driver`'s publish wrapper workflow
and make its existing `release` job depend on it:

```yaml
jobs:
  pre-release-integration:
    uses: scylladb/csharp-driver-matrix/.github/workflows/driver-integration-matrix.yml@master
    with:
      driver_ref: ${{ inputs.target_commit }}
      driver_version: ${{ inputs.version }}

  release:
    needs: pre-release-integration
    # Existing release job configuration follows.
```

The release call checks out matrix `master` for the runner and patches. The
`driver_ref` should match the driver commit the release workflow checks out.
SDK and integration test targets are selected from the Scylla driver version,
not the branch or the presence of `global.json`:

| Driver version | SDK | Integration test target |
| --- | --- | --- |
| `3.22.x` | `9.0.318` | `net9` |
| `4.x` | `10.0.401` | `net10.0` |

Pass `driver_version` whenever `driver_ref` is an untagged commit. A version
outside these supported lines fails before the matrix starts. DataStax tests
continue to use `net8` and the SDK in the published matrix image.

For a re-release, use the predecessor of the existing tag if that is the
release workflow's checkout target.

For a candidate version without a tag, add its `versions/scylla/<version>`
patch and ignore files. To validate that candidate in this repository's PR CI,
add a `checkout-ref` file in that directory containing the driver branch or
commit to test; the candidate then runs against all four Scylla targets.

## Prerequisites
Ensure the following are installed before proceeding:
* Python3.12
* pip
* git
* docker

## Installing dependencies

* Install the SDK for the driver version you intend to test. DataStax tests
  use .NET 8; Scylla 3.22.x uses 9.0.318 and 4.x uses 10.0.401. CI installs
  the Scylla SDK automatically.
```bash
sudo apt update && sudo apt install -y dotnet-sdk-8.0
```

* Repository dependencies
Ensure all repositories are cloned into **the same base folder**
```bash
# Clone DataStax driver (for testing DataStax version)
git clone git@github.com:datastax/csharp-driver.git datastax-csharp-driver &
# Clone ScyllaDB driver fork (for testing ScyllaDB version)
git clone git@github.com:scylladb/csharp-driver.git scylladb-csharp-driver &
git clone git@github.com:scylladb/scylla-ccm.git scylla-ccm &
git clone git@github.com:scylladb/csharp-driver-matrix.git csharp-driver-matrix
wait
```

* Install scylla-ccm and python dependencies in the dedicated virtual environment (e.g. managed with pyenv)
```bash
cd csaharp-driver-matrix
pyenv activate scylla-ccm
pip install ../scylla-ccm
pip install -r scripts/requirements.txt
```

## Run tests locally

### Run tests using main.py wrapper

**NOTE:** The `/usr/local/bin/ccm` path to the `ccm` binary is hardcoded in the driver tests. So if the ccm binary is located
elsewhere in the system (e.g. in a Python virtual environment), create a symlink to the expected location:
```bash
sudo ln -s "$(which ccm)" /usr/local/bin/ccm
```
Verify that `ccm` is accessible:
```bash
/usr/local/bin/ccm help
```
Run driver integration tests for DataStax driver:
```bash
python3 main.py ../datastax-csharp-driver --tests integration --versions 3.22.0 --scylla-version release:6.2
```
Run driver integration tests for ScyllaDB driver fork:
```bash
python3 main.py ../scylladb-csharp-driver --tests integration --versions v3.22.0.2 --scylla-version release:6.2
```

### Run tests with docker image
For DataStax driver:
```bash
export CSHARP_DRIVER_DIR=`pwd`/../datastax-csharp-driver
./scripts/run_test.sh python3 main.py ../datastax-csharp-driver --tests integration --versions 3.22.0 --scylla-version release:6.2
```
For ScyllaDB driver fork:
```bash
export CSHARP_DRIVER_DIR=`pwd`/../scylladb-csharp-driver
export DOTNET_INSTALL_DIR="$HOME/.dotnet" # Directory containing the matching SDK and dotnet executable
./scripts/run_test.sh python3 main.py ../scylladb-csharp-driver --tests integration --versions 3.22.0 --scylla-version release:6.2
```

#### Uploading docker images
When making changes to `requirements.txt` or modifying the Docker image, it can be build and pushed to Docker Hub using
the following steps:
```bash
export MATRIX_DOCKER_IMAGE=scylladb/csharp-driver-matrix:python3.12-$(date +'%Y%m%d')
docker build ./scripts -t ${MATRIX_DOCKER_IMAGE}
docker push ${MATRIX_DOCKER_IMAGE}
echo "${MATRIX_DOCKER_IMAGE}" > scripts/image
```
**Note:** you'll need to have appropriate permissions to upload the image to the `scylladb` organization on Docker Hub
