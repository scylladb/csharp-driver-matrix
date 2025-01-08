#!/usr/bin/env bash
set -e

help_text="
Script to run csharp driver matrix from within docker container

    Optional values can be set via environment variables
    CSHARP_MATRIX_DIR, CSHARP_DRIVER_DIR, CCM_DIR

    ./scripts/run_test.sh python3 main.py ../datastax-csharp-driver --tests integration --versions 3.22.0 --scylla-version release:6.2
"

here="$(realpath $(dirname "$0"))"
DOCKER_IMAGE="$(<"$here/image")"

export CSHARP_MATRIX_DIR=${CSHARP_MATRIX_DIR:-`pwd`}
export CSHARP_DRIVER_DIR=${CSHARP_DRIVER_DIR:-`pwd`/../datastax-csharp-driver}
export CCM_DIR=${CCM_DIR:-`pwd`/../scylla-ccm}

if [[ ! -d ${CSHARP_MATRIX_DIR} ]]; then
    echo -e "\e[31m\$CSHARP_MATRIX_DIR = $CSHARP_MATRIX_DIR doesn't exist\e[0m"
    echo "${help_text}"
    exit 1
fi
if [[ ! -d ${CCM_DIR} ]]; then
    echo -e "\e[31m\$CCM_DIR = $CCM_DIR doesn't exist\e[0m"
    echo "${help_text}"
    exit 1
fi

mkdir -p ${HOME}/.ccm
mkdir -p ${HOME}/.local/lib
mkdir -p ${HOME}/.docker

# export all BUILD_* env vars into the docker run
BUILD_OPTIONS=$(env | sed -n 's/^\(BUILD_[^=]\+\)=.*/--env \1/p')
# export all JOB_* env vars into the docker run
JOB_OPTIONS=$(env | sed -n 's/^\(JOB_[^=]\+\)=.*/--env \1/p')
# export all AWS_* env vars into the docker run
AWS_OPTIONS=$(env | sed -n 's/^\(AWS_[^=]\+\)=.*/--env \1/p')

# if in jenkins also mount the workspace into docker
if [[ -d ${WORKSPACE} ]]; then
WORKSPACE_MNT="-v ${WORKSPACE}:${WORKSPACE}"
else
WORKSPACE_MNT=""
fi

DOCKER_CONFIG_MNT="-v $(eval echo ~${USER})/.docker:${HOME}/.docker"

# export all SCYLLA_* env vars into the docker run
SCYLLA_OPTIONS=$(env | sed -n 's/^\(SCYLLA_[^=]\+\)=.*/--env \1/p')

group_args=()
for gid in $(id -G); do
    group_args+=(--group-add "$gid")
done

docker_cmd="docker run --detach=true \
    ${WORKSPACE_MNT} \
    ${SCYLLA_OPTIONS} \
    ${DOCKER_CONFIG_MNT} \
    -v ${CSHARP_MATRIX_DIR}:/csharp-driver-matrix \
    -v ${CSHARP_DRIVER_DIR}:/datastax-csharp-driver \
    -v ${CCM_DIR}:/scylla-ccm \
    -e HOME \
    -e SCYLLA_EXT_OPTS \
    -e LC_ALL=C.UTF-8 \
    -e DEV_MODE \
    -e WORKSPACE \
    ${BUILD_OPTIONS} \
    ${JOB_OPTIONS} \
    ${AWS_OPTIONS} \
    -w /csharp-driver-matrix \
    -v /var/run/docker.sock:/var/run/docker.sock \
    -v /sys/fs/cgroup:/sys/fs/cgroup:ro \
    -v /etc/passwd:/etc/passwd:ro \
    -v /etc/group:/etc/group:ro \
    -u $(id -u ${USER}):$(id -g ${USER}) \
    ${group_args[@]} \
    --tmpfs ${HOME}/.cache \
    --tmpfs ${HOME}/.config \
    --tmpfs ${HOME}/.cassandra \
    -v ${HOME}/.local:${HOME}/.local \
    -v ${HOME}/.ccm:${HOME}/.ccm \
    --network=host --privileged \
    ${DOCKER_IMAGE} bash -c 'pip install -e /scylla-ccm ; export PATH=\$PATH:\${HOME}/.local/bin ; ln -s /scylla-ccm/ccm /usr/local/bin/ccm; $*'"

echo "Running Docker: $docker_cmd"
container=$(eval $docker_cmd)


kill_it() {
    if [[ -n "$container" ]]; then
        docker rm -f "$container" > /dev/null
        container=
    fi
}

trap kill_it SIGTERM SIGINT SIGHUP EXIT

docker logs "$container" -f

if [[ -n "$container" ]]; then
    exitcode="$(docker wait "$container")"
else
    exitcode=99
fi

echo "Docker exitcode: $exitcode"

kill_it

trap - SIGTERM SIGINT SIGHUP EXIT

# after "docker kill", docker wait will not print anything
[[ -z "$exitcode" ]] && exitcode=1

exit "$exitcode"