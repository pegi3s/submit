This is a useless image unless you are a maintainer of the pegi3s BDIP project.

This image can invoked using:

docker run -v /var/run/docker.sock:/var/run/docker.sock   -v ~/.ssh:/root/.ssh   -v /submit_history:/submit_history -e USERID=$UID   -e USER=$USER   -e DISPLAY=$DISPLAY   -v /tmp/.X11-unix:/tmp/.X11-unix   -v /your/data/path/to/config/.config.ini:/opt/.config.ini   -v $PWD:/data pegi3s/submit
