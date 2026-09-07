# AI-Agent for Industry
An **AI-agent** for industrial robotic manipulation on Niryo Ned2 arm(s).

## Prerequisites
 
| Component | Version |
|-----------|---------|
| OS        | Ubuntu 24.04 LTS (Noble) |
| ROS 2     | Jazzy Jalisco |
| Python    | 3.12 (system default on 24.04) |
 
A working ROS 2 Jazzy installation is assumed. If not installed, follow the official guide: <https://docs.ros.org/en/jazzy/Installation/Ubuntu-Install-Debs.html>

---
 
## 1. Install the Niryo ROS 2 driver
 
Install it following the official guide:
 
> **Official installation guide:** <https://github.com/NiryoRobotics/ned-ros2-driver#building-from-source>

The driver lives in its own colcon workspace with its own venv, kept separated from this repo.
---

## 2. PlanSys2 and the custom packages
 
### Install PlanSys2
 
Install the PlanSys2 binaries following the official guide. **POPF** is the planner plugin used
by this project.
 
> **Official installation guide:** <https://plansys2.github.io/getting_started/index.html#installation>

### Repository layout

The repo root is the colcon workspace:
'''
AI-agent4Industry/                     # repo = colcon workspace
├── pddl/                              # PDDL domain + problem template
├── scenes/
│   └── scene.json                     # live scene description (edited outside packages)
├── agent/                             # LangGraph ReAct agent
│   ├── agent_state.py                 
│   ├── agent_context.py               
│   ├── agent_graph.py                 
│   ├── agent_nodes.py                 
│   ├── agent_tools.py                 
│   ├── agent_types.py                 
│   ├── plansys2_lib/                  # ROS 2 client nodes
│   └── main.py                        # agent entry point
├── test_script.py
├── bringup.launch.py                  # ROS2 stack launcher script
└── src/
    ├── niryo_env_interfaces/          
    ├── niryo_env_perception/          
    ├── niryo_world_interfaces/        
    ├── niryo_world_model/             
    ├── niryo_safety/                  
    └── niryo_plansys2_actions/        
'''

### Build the custom packages
 
These are the packages built for this project — all steps below.
 
```bash
git clone https://github.com/Luca975/AI-agent4Industry
cd AI-AGENT4INDUSTRY
 
# Build the C++ packages
source /opt/ros/jazzy/setup.bash
rosdep install --from-paths src --ignore-src -r -y
colcon build --symlink-install
 
# Source the workspace overlay
source install/setup.bash
``` 
---

## 3. LangGraph agent (Python virtual environment)
 
### Create the venv
 
```bash

source /opt/ros/jazzy/setup.bash
source install/setup.bash
 
# Create the venv with access to system (ROS 2) packages
python3 -m venv --system-site-packages agent-env
source agent-env/bin/activate
```
 
### Install dependencies
 
 
```bash
pip install -U --ignore-installed langgraph langchain-anthropic
# TODO: confirm the exact Claude/LLM client package(s) used by the agent
```

### Verify the environment
 
```bash
python -c "import rclpy, langgraph; print('ok')"
```
---

## 4. Running the system
 
The system requires **two terminals**, run in this order from the host:
 
### Terminal 1 — ROS2 stack
 
```bash
cd ~/AI-agent4Industry
source /opt/ros/jazzy/setup.bash
source /home/luca/ros2_drivers_ws/install/setup.bash
source install/setup.bash
ros2 launch bringup.launch.py
``` 

### Terminal 2 — LangGraph agent
 
```bash
cd ~/AI-agent4Industry
source /opt/ros/jazzy/setup.bash
source /home/luca/ros2_drivers_ws/install/setup.bash
source install/setup.bash
source agent-env/bin/activate
python3 agent/main.py
```
 
---