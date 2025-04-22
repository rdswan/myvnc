# myvnc
This is a web based application to manage a users VNCs.
There is a lightweight backend web server that supports this application via python CGI code.
There is also an included python command line wrapper script which makes curl calls to perform all operations available via the web interface.
It uses a minimal amount of packages to keep dependency requirements small.
In order to reduce the amount of required packages, all calls to LSF are made by the command line rather than the LSF API
It is fully Open Source via the Apache License 2.0

## Features
- There is a tab with a visual listing of active VNC servers, with the ability to open or kill each one
  - Each VNC submitted to LSF by the user is listed based on its name and site
- There is a tab to support the creation of a new VNC server
  - New VNCs can be opened with a variety of options including name, site, resolution, and window manager of choice.
    - There are default values for these VNC settings, but the user is able to change them via the GUI
    - Default VNC settings are defined in an included json file called vnc_config.json
- VNC commands are not executed directly, but rather submitted to LSF via the command line. Therefore neither python-vnc-client nor lsf-python-api packages are required.
  - LSF configuration to define the queue, number of cores, and amount of memory to reserve for submission. There are default values for these 3 LSF definitions, but the user is able to change them via the GUI
  - This script uses the python LSF API to make calls to an LSF cluster.
  - Default LSF settings are defined in an included json file called lsf_config.json

## Installation

### Prerequisites
- Python 3.8 or higher
- LSF (Load Sharing Facility) installed and configured on your system
- VNC server installed on the LSF compute nodes

### Installing from source
1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/myvnc.git
   cd myvnc
   python3 main.py
   ```

2. Edit the config/server_config.json file with your webserver details
   ```bash
   vim config/server_config.json
   ```

2. Start the server:
   ```bash
   python3 main.py
   ```

   Alternately you can start the server on a different host than specified in the server_config.json file
   ```bash
   python3 main.py rv-l-07.aus2.tenstorrent.com 9123
   ```

## Usage

### GUI Application
To launch the graphical user interface, navigate your webpage to the url
```url
http://rv-l-07.aus2.tenstorrent.com:9123/
```

### Command Line Interface
The application also provides a command-line interface for managing VNC sessions:

1. List all active VNC sessions:
   ```bash
   myvnc-cli list
   ```

2. Create a new VNC session:
   ```bash
   myvnc-cli create --name my_session --resolution 1920x1080 --wm gnome --queue vnc_queue --cores 2 --memory 4096
   ```

3. Kill a VNC session:
   ```bash
   myvnc-cli kill <job_id>
   ```

## Contributing
We welcome contributions! To contribute:
1. Fork the repository.
2. Create a new branch for your feature or bugfix:
   ```bash
   git checkout -b feature-name
   ```
3. Commit your changes and push the branch:
   ```bash
   git commit -m "Description of changes"
   git push origin feature-name
   ```
4. Open a pull request.

## License
This project is licensed under the Apache License 2.0. See the [LICENSE](LICENSE) file for details.
