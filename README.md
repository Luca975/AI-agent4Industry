# AI-Agent for Industry
The aim is controlling two Niryo Ned2 arms.

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
 
---

## 2. PlanSys2 and the custom packages
 
### Install PlanSys2
 
Install the PlanSys2 binaries following the official guide. **POPF** is the planner plugin used
by this project.
 
> **Official installation guide:** <https://plansys2.github.io/getting_started/index.html#installation>
 
### Build the custom packages
 
These are the packages built for this project — all steps below.
 
Repository layout (the repo root **is** the colcon workspace):
 
```
AI-AGENT4INDUSTRY/                       # repo = colcon workspace
├── pddl/                                # PDDL domain + problem files
├── agent/                               # LangGraph ReAct agent
│   ├── agent_state.py                   # AgentState, PlanStep
│   ├── agent_context.py                 # context_schema
│   ├── agent_graph.py                   # StateGraph definition
│   ├── agent_nodes.py                    # graph node implementations
│   ├── agent_tools.py                    # ReAct tools
│   ├── agent_types.py                     # shared type definitions
│   ├── plansys2_lib/                     # ROS2 client nodes 
│   └── main.py                           # entry point
└── src/
    ├── niryo_plansys2_interfaces/       # custom GetZone.srv, ObserveScene.srv, SceneObject.msg
    └── niryo_plansys2_actions/          # MoveAction, PickAction, PlaceAction, ZoneMapServer
```
 
`niryo_plansys2_actions` depends on the service definition in `niryo_plansys2_interfaces`;
`colcon` resolves the build order automatically from the `package.xml` dependencies.
 
```bash
# Clone the repo (replace with your remote)
git clone <your-repo-url>
cd AI-AGENT4INDUSTRY
 
# Build the C++ packages
source /opt/ros/jazzy/setup.bash
rosdep install --from-paths src --ignore-src -r -y
colcon build --symlink-install
 
# Source the workspace overlay
source install/setup.bash
```
 
After building, the zone service is available at `/get_zone` (served by `ZoneMapServer`,
which reads zone coordinates from the configured CSV).
 
---

## 3. LangGraph agent (Python virtual environment)
 
### Create the venv
 
```bash
# From the repo root, with ROS 2 and the workspace sourced
source /opt/ros/jazzy/setup.bash
source install/setup.bash
 
# Create the venv with access to system (ROS 2) packages
python3 -m venv --system-site-packages agent-env
source agent-env/bin/activate
```
 
### Install dependencies
 
 
```bash
pip install -U --ignore-installed langgraph
```

### Verify the environment
 
```bash
python -c "import rclpy, langgraph; print('ok')"
```
 
---

## 4. Running the system
 
The system requires **three terminals**, run in this order from the host:
 
### Terminal 1 — Niryo ROS 2 driver
 
```bash
cd ~/ros2_drivers_ws
source /opt/ros/jazzy/setup.bash
source install/setup.bash
source venv/bin/activate
ros2 launch niryo_ned_ros2_driver driver.launch.py drivers_list_file:=./src/ned-ros2-driver/niryo_ned_ros2_driver/config/drivers_list.yaml
```
 
### Terminal 2 — PlanSys2 stack
 
```bash
cd ~/AI-agent4Industry
source /opt/ros/jazzy/setup.bash
source /home/luca/ros2_drivers_ws/install/setup.bash
source install/setup.bash
ros2 launch niryo_plansys2_actions niryo_plansys2_launch.py
```
 
### Terminal 3 — LangGraph agent
 
```bash
cd ~/AI-agent4Industry
source /opt/ros/jazzy/setup.bash
source /home/luca/ros2_drivers_ws/install/setup.bash
source install/setup.bash
source agent-env/bin/activate
python3 agent/main.py
```
 
---