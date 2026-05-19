cmake_minimum_required(VERSION 3.8)
project(niryo_plansys2_actions)

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rclcpp_action REQUIRED)
find_package(plansys2_executor REQUIRED)
find_package(niryo_ned_ros2_interfaces REQUIRED)
find_package(niryo_plansys2_interfaces REQUIRED)
find_package(lifecycle_msgs REQUIRED)

add_executable(move_action_node src/move_action-node.cpp)
target_include_directories(move_action_node PRIVATE include)
ament_target_dependencies(move_action_node
  rclcpp
  rclcpp_action
  plansys2_executor
  niryo_ned_ros2_interfaces
  niryo_plansys2_interfaces
  lifecycle_msgs
)

add_executable(pick_action_node src/pick_action-node.cpp)
ament_target_dependencies(pick_action_node
  rclcpp
  plansys2_executor
  lifecycle_msgs
)

add_executable(place_action_node src/place_action-node.cpp)
ament_target_dependencies(place_action_node
  rclcpp
  plansys2_executor
  lifecycle_msgs
)

add_executable(zone_map_server_node src/zone_map-server.cpp)
target_include_directories(zone_map_server_node PRIVATE include)
ament_target_dependencies(zone_map_server_node
  rclcpp
  niryo_plansys2_interfaces
)

install(TARGETS
  move_action_node
  pick_action_node
  place_action_node
  zone_map_server_node
  DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY config launch
  DESTINATION share/${PROJECT_NAME}
)

ament_package()