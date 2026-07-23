#pragma once

#include <string>

#include "rclcpp/rclcpp.hpp"
#include "rclcpp_action/rclcpp_action.hpp"
#include "plansys2_executor/ActionExecutorClient.hpp"
#include "niryo_world_interfaces/srv/get_zone.hpp"
#include "niryo_ned_ros2_interfaces/action/robot_move.hpp"

using namespace rclcpp;
using namespace rclcpp_action;
using namespace plansys2;
using namespace std;

using GetZone=niryo_world_interfaces::srv::GetZone;
using RobotMove=niryo_ned_ros2_interfaces::action::RobotMove;

class moveAction : public ActionExecutorClient{
    public:
        moveAction();
    private:
        void do_work();
        void send_move_command(GetZone::Response::SharedPtr response);

        rclcpp::Client<GetZone>::SharedPtr zone_client_;
        rclcpp_action::Client<RobotMove>::SharedPtr move_client_;

        bool command_sent_;

}; 