#pragma once

#include <string>

#include "rclcpp/rclcpp.hpp"
#include "rclcpp_action/rclcpp_action.hpp"
#include "plansys2_executor/ActionExecutorClient.hpp"
#include "niryo_world_interfaces/srv/get_zone.hpp"
#include "niryo_world_interfaces/msg/safety_alert.hpp"
#include "niryo_ned_ros2_interfaces/action/robot_move.hpp"

using namespace rclcpp;
using namespace rclcpp_action;
using namespace plansys2;
using namespace std;

using GetZone = niryo_world_interfaces::srv::GetZone;
using SafetyAlert = niryo_world_interfaces::msg::SafetyAlert;
using RobotMove = niryo_ned_ros2_interfaces::action::RobotMove;
using GoalHandleRobotMove = rclcpp_action::ClientGoalHandle<RobotMove>;

class moveAction : public ActionExecutorClient{
    public:
        moveAction();
    private:

        /*
            IDLE -> nothing dispatched yet
            MOVING -> travelling toward ?to
            WAITING -> arm stopped after an alert, counting down the micro-wait
            RETURNING -> travelling back to ?from before failing the action
        */
        enum class State {IDLE, MOVING, WAITING, RETURNING};

        void do_work();
        void send_move_command(GetZone::Response::SharedPtr response);
        void dispatch_move(const string& zone);
        void on_alert(const SafetyAlert::SharedPtr msg);



        rclcpp::Client<GetZone>::SharedPtr zone_client_;
        rclcpp_action::Client<RobotMove>::SharedPtr move_client_;
        Subscription<SafetyAlert>::SharedPtr alert_sub_;

        GoalHandleRobotMove::SharedPtr goal_handle_;

        State state_;
        string from_;
        string to_;
        string target_;
        Time wait_start_;
        double wait_timeout_;
        uint64_t goal_seq_;

}; 