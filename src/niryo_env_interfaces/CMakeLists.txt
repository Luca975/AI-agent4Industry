cmake_minimum_required(VERSION 3.8)
project(niryo_env_interfaces)

find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(std_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)

# EnvObject must come before EnvScene: EnvScene embeds it.
rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/EnvObject.msg"
  "msg/EnvScene.msg"
  "msg/ToolStatus.msg"
  DEPENDENCIES std_msgs geometry_msgs
)

ament_export_dependencies(rosidl_default_runtime)

ament_package()