FROM docker:27-cli

RUN apk add --no-cache bash

COPY scripts/docker_build_and_run.sh /usr/local/bin/docker_build_and_run.sh
RUN chmod +x /usr/local/bin/docker_build_and_run.sh

ENTRYPOINT ["/usr/local/bin/docker_build_and_run.sh", "launch"]
