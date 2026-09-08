cmake_minimum_required(VERSION 3.8)
project(niryo_safety)
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(plansys2_msgs REQUIRED)
find_package(niryo_world_interfaces REQUIRED)

add_executable(safe_monitor_node src/safe_monitor.cpp)
target_include_directories(safe_monitor_node PRIVATE include)
ament_target_dependencies(safe_monitor_node
  rclcpp
  plansys2_msgs
  niryo_world_interfaces
)

install(DIRECTORY launch
  DESTINATION share/${PROJECT_NAME}
)

install(TARGETS safe_monitor_node DESTINATION lib/${PROJECT_NAME})

ament_package()