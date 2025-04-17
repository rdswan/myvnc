# myvnc
This is a GUI application to manage a users VNCs. It runs on MacOS, Windows, and Linux. It is launchable via both a graphical icon as well as the CLI

## Features
- There is a tab with a visual listing of active VNC servers, with the ability to open or kill each one
  - Each VNC submitted to LSF by the user is listed based on its name and site
- There is a tab to support the creation of a new VNC server
  - New VNCs can be opened with a variety of options including name, site, resolution, and window manager of choice.
    - There are default values for these VNC settings, but the user is able to change them via the GUI
    - Default VNC settings are defined in an included json file called vnc_config.json
- VNC commands are not executed directly, but rather submitted to LSF. Therefore no actual python-vnc-client is required.
  - LSF configuration to define the queue, number of cores, and amount of memory to reserve for submission. There are default values for these 3 LSF definitions, but the user is able to change them via the GUI
  - This script uses the python LSF API to make calls to an LSF cluster.
  - Default LSF settings are defined in an included json file called lsf_config.json

## Installation

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
