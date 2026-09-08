cmake_minimum_required(VERSION 3.8)
project(niryo_world_model)
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(niryo_world_interfaces REQUIRED)
find_package(niryo_env_interfaces REQUIRED)
find_package(niryo_ned_ros2_interfaces REQUIRED)

add_executable(world_model_server_node src/world_model_server.cpp)
target_include_directories(world_model_server_node PRIVATE include)
ament_target_dependencies(world_model_server_node
  rclcpp
  niryo_world_interfaces
  niryo_env_interfaces
  niryo_ned_ros2_interfaces
)

install(TARGETS world_model_server_node DESTINATION lib/${PROJECT_NAME})
install(DIRECTORY config launch DESTINATION share/${PROJECT_NAME})

ament_package()