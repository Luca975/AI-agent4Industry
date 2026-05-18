cmake_minimum_required(VERSION 3.8)
project(niryo_plansys2_interfaces)

find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(niryo_ned_ros2_interfaces REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "srv/GetZone.srv"
  DEPENDENCIES geometry_msgs niryo_ned_ros2_interfaces
)

ament_package()