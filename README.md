This is a useless image unless you are a maintainer of the pegi3s BDIP project.

This image can invoked using:

path_to_config_folder=/path/to/config/folder && docker run -v /var/run/docker.sock:/var/run/docker.sock -v ~/.ssh:/root/.ssh -v /submit_history:/submit_history -e USERID=$UID -e USER=$USER -e DISPLAY=$DISPLAY -v /tmp/.X11-unix:/tmp/.X11-unix -v $path_to_config_folder/.config.ini:/opt/.config.ini -v $path_to_config_folder/.config.ini:/home/bdip-user/.config/bdip-tools/config.ini -v $PWD:/data pegi3s/submit

where /path/to/config/folder is the path to the location of the config folder that should look like the one in this repository.
