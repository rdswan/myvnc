# myvnc
This is a GUI application to manage a users VNCs. It runs on MacOS, Windows, and Linux. It is launchable via both a graphical icon as well as the CLI

## Features
- Visual listing of active VNC servers, with the ability to open or kill each one
- Section to support the creation of a new VNC server
  - New VNCs can be opened with a variety of options including name, site, resolution, and window manager of choice
  - LSF configuration to define the queue, number of cores, and amount of memory to reserve for submission
- VNC commands are not executed directly, but rather submitted to LSF. Therefore no actual python-vnc-client is required.

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
