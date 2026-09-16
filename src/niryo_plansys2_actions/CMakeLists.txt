cmake_minimum_required(VERSION 3.8)
project(niryo_plansys2_actions)

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rclcpp_action REQUIRED)
find_package(plansys2_executor REQUIRED)
find_package(plansys2_msgs REQUIRED)
find_package(niryo_ned_ros2_interfaces REQUIRED)
find_package(niryo_world_interfaces REQUIRED)
find_package(lifecycle_msgs REQUIRED)
find_package(niryo_env_interfaces REQUIRED)

add_executable(move_action_node src/move_action-node.cpp)
target_include_directories(move_action_node PRIVATE include)
ament_target_dependencies(move_action_node
  rclcpp
  rclcpp_action
  plansys2_executor
  niryo_ned_ros2_interfaces
  niryo_world_interfaces
  lifecycle_msgs
)

add_executable(pick_action_node src/pick_action-node.cpp)
target_include_directories(pick_action_node PRIVATE include)
ament_target_dependencies(pick_action_node
  rclcpp
  rclcpp_action
  plansys2_executor
  lifecycle_msgs
  niryo_env_interfaces
  niryo_world_interfaces
  niryo_ned_ros2_interfaces
)

add_executable(place_action_node src/place_action-node.cpp)
target_include_directories(place_action_node PRIVATE include)
ament_target_dependencies(place_action_node
  rclcpp
  rclcpp_action
  plansys2_executor
  lifecycle_msgs
  niryo_env_interfaces
  niryo_world_interfaces
  niryo_ned_ros2_interfaces
)


install(TARGETS
  move_action_node
  pick_action_node
  place_action_node
  DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY launch
  DESTINATION share/${PROJECT_NAME}
)

ament_package()